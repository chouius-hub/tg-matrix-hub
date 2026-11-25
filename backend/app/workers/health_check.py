import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    UserDeactivatedBanError,
)

from app.engine.pool import client_pool
from app.engine.proxy_checker import ProxyChecker, build_telethon_proxy
from app.models.account import Account
from app.models.task import TaskLog

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def parse_spambot_reply(reply_text: str) -> tuple[str, str]:
    """解析 @SpamBot 返回文本，返回 (建议账号状态, 摘要文本)。"""
    lowered = reply_text.lower()
    summary = reply_text.strip()[:500]
    if "good news, no limits" in lowered or "no limits are currently applied" in lowered:
        return "active", summary
    if (
        "limited" in lowered
        or "spam" in lowered
        or "cannot send messages" in lowered
        or "blocked" in lowered
    ):
        return "restricted", summary
    return "active", summary


async def run_spambot_health_check(db: AsyncSession, account_id: int) -> Account:
    """使用绑定代理与固化指纹连接账号，向 @SpamBot 发送 /start 完成体检。"""
    lock = client_pool.get_account_lock(account_id)
    async with lock:
        stmt = (
            select(Account)
            .options(
                selectinload(Account.device_profile),
                selectinload(Account.proxy),
            )
            .where(Account.id == account_id)
        )
        account = (await db.execute(stmt)).scalar_one_or_none()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在"
            )

        if account.status in ("invalid", "banned"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"账号当前状态为 {account.status}，无法执行体检",
            )

        # 红线 1：连接前必须先探活代理，严禁直连回退
        probe = await ProxyChecker.verify_proxy_alive(db, account.proxy, commit=True)
        if not probe.alive:
            account.health_score = max(0, account.health_score - 5)
            db.add(
                TaskLog(
                    account_id=account.id,
                    action="health_check",
                    result="proxy_dead",
                    target_ref="@SpamBot",
                    error_detail=probe.error,
                )
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"代理探活失败，已中止体检（严禁直连）: {probe.error}",
            )

        session_path = BACKEND_DIR / account.session_file_path
        if not session_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="本地 Session 文件不存在，请重新导入账号",
            )

        # 红线 3：严格从数据库读取固化设备指纹
        profile = account.device_profile
        proxy_tuple = build_telethon_proxy(account.proxy)
        client = TelegramClient(
            str(session_path),
            profile.api_id,
            profile.api_hash,
            proxy=proxy_tuple,
            device_model=profile.device_model,
            system_version=profile.system_version,
            app_version=profile.app_version,
            lang_code=profile.lang_code,
            system_lang_code=profile.system_lang_code,
            flood_sleep_threshold=0,
        )

        now_utc = datetime.now(timezone.utc)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                account.status = "invalid"
                account.spambot_status = "Session 未授权或已失效"
                account.last_health_check_at = now_utc
                db.add(
                    TaskLog(
                        account_id=account.id,
                        action="health_check",
                        result="auth_invalid",
                        target_ref="@SpamBot",
                        error_detail="is_user_authorized 返回 False",
                    )
                )
                await db.commit()
                await db.refresh(account)
                return account

            await client.send_message("SpamBot", "/start")
            await asyncio.sleep(2.5)
            messages = await client.get_messages("SpamBot", limit=1)
            reply_text = messages[0].message if messages and messages[0].message else "未收到 @SpamBot 回复"

            parsed_status, summary = parse_spambot_reply(reply_text)
            if account.status != "frozen":
                account.status = parsed_status
            account.spambot_status = summary
            account.last_health_check_at = now_utc
            account.last_active_at = now_utc

            db.add(
                TaskLog(
                    account_id=account.id,
                    action="health_check",
                    result="success",
                    target_ref="@SpamBot",
                )
            )
            await db.commit()
            await db.refresh(account)
            return account

        except FloodWaitError as exc:
            wait_sec = int(exc.seconds)
            cooldown_delta = (
                timedelta(hours=24)
                if wait_sec > 1800
                else timedelta(seconds=wait_sec + random.randint(30, 120))
            )
            account.status = "cooldown"
            account.cooldown_until = now_utc + cooldown_delta
            account.health_score = max(0, account.health_score - 15)
            account.last_health_check_at = now_utc
            db.add(
                TaskLog(
                    account_id=account.id,
                    action="health_check",
                    result="flood_wait",
                    target_ref="@SpamBot",
                    wait_seconds=wait_sec,
                    error_detail=str(exc),
                )
            )
            await db.commit()
            await db.refresh(account)
            return account

        except AuthKeyUnregisteredError:
            account.status = "invalid"
            account.spambot_status = "AuthKeyUnregisteredError"
            account.last_health_check_at = now_utc
            db.add(
                TaskLog(
                    account_id=account.id,
                    action="health_check",
                    result="auth_invalid",
                    target_ref="@SpamBot",
                    error_detail="AuthKeyUnregisteredError",
                )
            )
            await db.commit()
            await db.refresh(account)
            return account

        except UserDeactivatedBanError:
            account.status = "banned"
            account.spambot_status = "UserDeactivatedBanError"
            account.last_health_check_at = now_utc
            db.add(
                TaskLog(
                    account_id=account.id,
                    action="health_check",
                    result="auth_invalid",
                    target_ref="@SpamBot",
                    error_detail="UserDeactivatedBanError",
                )
            )
            await db.commit()
            await db.refresh(account)
            return account

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

