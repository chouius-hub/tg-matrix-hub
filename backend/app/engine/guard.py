import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    FloodWaitError,
    PeerFloodError,
    SlowModeWaitError,
    UserDeactivatedBanError,
)

from app.core.database import AsyncSessionLocal
from app.core.ws_manager import ws_manager
from app.engine.pool import client_pool
from app.engine.proxy_checker import ProxyChecker
from app.models.account import Account
from app.models.task import TaskLog

logger = logging.getLogger(__name__)

# 红线 5：全局写操作并发闸门，严格限制同时执行的写任务不超过 6 个
GLOBAL_SEMAPHORE = asyncio.Semaphore(6)


@dataclass(slots=True)
class SafeTaskResult:
    """风控执行器统一返回结构。"""

    success: bool
    result_code: str
    data: Any = None
    error: str | None = None


def _is_in_quiet_hours(account: Account, now_utc: datetime) -> bool:
    """判断当前时间是否处于账号所属时区的夜间静默时段（00:00 - 07:30）。"""
    if not account.quiet_hours_enabled:
        return False
    try:
        tz = ZoneInfo(account.timezone)
    except Exception:
        logger.warning("账号 [id=%s] 时区无效 (%s)，回退为 UTC", account.id, account.timezone)
        tz = ZoneInfo("UTC")

    local_now = now_utc.astimezone(tz)
    return local_now.hour < 7 or (local_now.hour == 7 and local_now.minute < 30)


async def _record_log_and_broadcast(
    db: AsyncSession,
    *,
    account_id: int,
    action: str,
    result: str,
    job_id: int | None = None,
    target_ref: str | None = None,
    wait_seconds: int = 0,
    error_detail: str | None = None,
    alert_level: str | None = None,
) -> None:
    """写入审计日志并通过 WebSocket 实时推送到前端。"""
    log_entry = TaskLog(
        job_id=job_id,
        account_id=account_id,
        action=action,
        result=result,
        target_ref=target_ref,
        wait_seconds=wait_seconds,
        error_detail=error_detail,
    )
    db.add(log_entry)
    await db.commit()

    await ws_manager.broadcast(
        "task_log",
        {
            "account_id": account_id,
            "action": action,
            "result": result,
            "target_ref": target_ref,
            "wait_seconds": wait_seconds,
            "error_detail": error_detail,
        },
    )
    if alert_level:
        await ws_manager.broadcast(
            "alert",
            {
                "level": alert_level,
                "account_id": account_id,
                "action": action,
                "result": result,
                "message": error_detail or result,
            },
        )


async def run_safe_account_task(
    account_id: int,
    action_name: str,
    coro_factory: Callable[[TelegramClient], Awaitable[Any]],
    *,
    job_id: int | None = None,
    target_ref: str | None = None,
    db_session: AsyncSession | None = None,
    jitter_range: tuple[float, float] = (2.0, 8.0),
) -> SafeTaskResult:
    """
    风控熔断统一执行器：所有主动调用 Telegram 写操作必须通过此入口包装执行。
    严格落实 SPEC.md 第四节全部 8 步校验、探活、抖动与异常分类熔断。
    """
    owns_session = db_session is None
    db = db_session if db_session is not None else AsyncSessionLocal()

    try:
        # 第 1 步：读取最新账号与代理，校验状态、冷却期与每日配额
        stmt = (
            select(Account)
            .options(
                selectinload(Account.device_profile),
                selectinload(Account.proxy),
            )
            .where(Account.id == account_id)
        )
        account = (await db.execute(stmt)).scalar_one_or_none()
        if account is None:
            return SafeTaskResult(False, "error", error="账号不存在")

        now_utc = datetime.now(timezone.utc)

        if account.status != "active":
            msg = f"账号状态为 {account.status}，不允许执行调度"
            await _record_log_and_broadcast(
                db,
                account_id=account.id,
                action=action_name,
                result="skipped",
                job_id=job_id,
                target_ref=target_ref,
                error_detail=msg,
            )
            return SafeTaskResult(False, "skipped", error=msg)

        if account.cooldown_until is not None and account.cooldown_until > now_utc:
            msg = f"账号仍在冷却期至 {account.cooldown_until.isoformat()}"
            await _record_log_and_broadcast(
                db,
                account_id=account.id,
                action=action_name,
                result="skipped",
                job_id=job_id,
                target_ref=target_ref,
                error_detail=msg,
            )
            return SafeTaskResult(False, "skipped", error=msg)

        if account.daily_action_count >= account.daily_action_limit:
            msg = f"已达今日操作配额上限 ({account.daily_action_count}/{account.daily_action_limit})"
            await _record_log_and_broadcast(
                db,
                account_id=account.id,
                action=action_name,
                result="skipped",
                job_id=job_id,
                target_ref=target_ref,
                error_detail=msg,
            )
            return SafeTaskResult(False, "skipped", error=msg)

        # 第 2 步：校验夜间静默时段（00:00 - 07:30）
        if _is_in_quiet_hours(account, now_utc):
            msg = f"处于账号时区 ({account.timezone}) 夜间静默时段（00:00-07:30）"
            await _record_log_and_broadcast(
                db,
                account_id=account.id,
                action=action_name,
                result="skipped",
                job_id=job_id,
                target_ref=target_ref,
                error_detail=msg,
            )
            return SafeTaskResult(False, "skipped", error=msg)

        # 第 3 步：获取单账号独占锁与全局并发闸门
        account_lock = client_pool.get_account_lock(account.id)
        async with account_lock:
            async with GLOBAL_SEMAPHORE:
                # 第 4 步：强制探活绑定代理，严禁直连回退
                probe = await ProxyChecker.verify_proxy_alive(
                    db, account.proxy, commit=True
                )
                if not probe.alive:
                    account.health_score = max(0, account.health_score - 5)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="proxy_dead",
                        job_id=job_id,
                        target_ref=target_ref,
                        error_detail=probe.error or "代理探活失败",
                        alert_level="warning",
                    )
                    return SafeTaskResult(
                        False, "proxy_dead", error=probe.error or "代理探活失败"
                    )

                # 第 5 步：前置随机抖动，模拟人类操作节奏
                delay_min, delay_max = jitter_range
                if delay_max > 0:
                    await asyncio.sleep(random.uniform(delay_min, delay_max))

                # 第 6 步：从连接池获取绑定固化指纹与代理的客户端并执行任务
                try:
                    client = await client_pool.get_task_client(account)
                    data = await coro_factory(client)

                # 第 7 步：严格异常分类熔断
                except FloodWaitError as exc:
                    wait_sec = int(exc.seconds)
                    cooldown_delta = (
                        timedelta(hours=24)
                        if wait_sec > 1800
                        else timedelta(seconds=wait_sec + random.randint(30, 120))
                    )
                    account.status = "cooldown"
                    account.cooldown_until = datetime.now(timezone.utc) + cooldown_delta
                    account.health_score = max(0, account.health_score - 15)
                    await client_pool.evict_client(account.id)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="flood_wait",
                        job_id=job_id,
                        target_ref=target_ref,
                        wait_seconds=wait_sec,
                        error_detail=f"触发 FloodWait({wait_sec}s)，已进入冷却",
                        alert_level="warning",
                    )
                    return SafeTaskResult(
                        False, "flood_wait", error=f"FloodWaitError({wait_sec}s)"
                    )

                except PeerFloodError as exc:
                    account.status = "restricted"
                    account.health_score = max(0, account.health_score - 40)
                    await client_pool.evict_client(account.id)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="peer_flood",
                        job_id=job_id,
                        target_ref=target_ref,
                        error_detail="触发 PeerFloodError，账号已自动受限并停止写操作",
                        alert_level="critical",
                    )
                    return SafeTaskResult(False, "peer_flood", error=str(exc))

                except AuthKeyUnregisteredError as exc:
                    account.status = "invalid"
                    await client_pool.evict_client(account.id)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="auth_invalid",
                        job_id=job_id,
                        target_ref=target_ref,
                        error_detail="AuthKeyUnregisteredError: Session 已失效",
                        alert_level="critical",
                    )
                    return SafeTaskResult(False, "auth_invalid", error=str(exc))

                except UserDeactivatedBanError as exc:
                    account.status = "banned"
                    await client_pool.evict_client(account.id)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="auth_invalid",
                        job_id=job_id,
                        target_ref=target_ref,
                        error_detail="UserDeactivatedBanError: 账号已被官方封禁",
                        alert_level="critical",
                    )
                    return SafeTaskResult(False, "auth_invalid", error=str(exc))

                except SlowModeWaitError as exc:
                    wait_sec = int(exc.seconds)
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="skipped",
                        job_id=job_id,
                        target_ref=target_ref,
                        wait_seconds=wait_sec,
                        error_detail=f"目标群组开启慢速模式，需等待 {wait_sec}s（不惩罚账号）",
                    )
                    return SafeTaskResult(False, "skipped", error=str(exc))

                except Exception as exc:
                    logger.exception(
                        "账号 [id=%s] 执行任务 [%s] 发生未预期异常",
                        account.id,
                        action_name,
                    )
                    await _record_log_and_broadcast(
                        db,
                        account_id=account.id,
                        action=action_name,
                        result="error",
                        job_id=job_id,
                        target_ref=target_ref,
                        error_detail=f"{type(exc).__name__}: {exc}",
                    )
                    return SafeTaskResult(
                        False, "error", error=f"{type(exc).__name__}: {exc}"
                    )

                # 第 8 步：执行成功，更新配额、活跃时间与审计日志
                account.daily_action_count += 1
                account.last_active_at = datetime.now(timezone.utc)
                await _record_log_and_broadcast(
                    db,
                    account_id=account.id,
                    action=action_name,
                    result="success",
                    job_id=job_id,
                    target_ref=target_ref,
                )
                return SafeTaskResult(True, "success", data=data)
    finally:
        if owns_session:
            await db.close()

