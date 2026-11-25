import asyncio
import logging
import random
import re
import uuid
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telethon import events

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.engine.guard import run_safe_account_task
from app.engine.pool import client_pool
from app.engine.proxy_checker import ProxyChecker
from app.models.account import Account
from app.models.channel_sync import ChannelSyncRule, SyncMessageHistory
from app.models.keyword import KeywordRule
from app.models.task import TaskLog

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEMP_DIR = BACKEND_DIR / "storage" / "temp"


def contains_blocked_keyword(text: str, blocked_keywords: list[str]) -> str | None:
    """检查文本是否命中屏蔽词（忽略大小写），命中则返回对应关键词。"""
    if not text or not blocked_keywords:
        return None
    lowered = text.lower()
    for kw in blocked_keywords:
        kw_clean = kw.strip()
        if kw_clean and kw_clean.lower() in lowered:
            return kw_clean
    return None


def apply_regex_replacements(
    text: str, regex_replacements: list[dict[str, Any]]
) -> str:
    """按顺序对文本执行正则清洗替换。"""
    result = text
    for item in regex_replacements:
        pattern = item.get("pattern")
        replace = item.get("replace", "")
        if not pattern:
            continue
        try:
            result = re.sub(pattern, replace, result)
        except re.error as exc:
            logger.warning("无效的正则表达式 [%s]: %s", pattern, exc)
    return result.strip()


async def translate_text_with_ai(text: str, system_prompt: str) -> str:
    """异步调用 OpenAI 兼容接口进行翻译，超时或未配置密钥时降级保留原文。"""
    if not text.strip():
        return text
    if not settings.AI_API_KEY:
        logger.warning("未配置 AI_API_KEY，跳过 AI 翻译并降级保留原文")
        return text

    try:
        client = AsyncOpenAI(
            base_url=settings.AI_API_BASE,
            api_key=settings.AI_API_KEY,
            timeout=30.0,
        )
        resp = await client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        translated = resp.choices[0].message.content
        return translated.strip() if translated else text
    except Exception as exc:
        logger.error("AI 翻译调用失败，降级保留原文: %s", exc)
        return text


def _normalize_chat_ref(chat_id: str) -> int | str:
    """将数字字符串频道 ID 转为 int，@username 保持字符串。"""
    cleaned = chat_id.strip()
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return cleaned


class ChannelSyncManager:
    """多频道采集与 AI 翻译转发管理器，支持规则热加载。"""

    def __init__(self) -> None:
        self._registered_handlers: list[tuple[int, Any]] = []
        self._reload_lock = asyncio.Lock()

    async def process_incoming_message(
        self,
        db: AsyncSession,
        rule: ChannelSyncRule,
        *,
        source_chat_id: str,
        source_msg_id: int,
        raw_text: str,
        media_path: Path | None = None,
        delay_override: tuple[float, float] | None = None,
    ) -> str:
        """
        处理单条新消息的完整流水线：去重 -> 屏蔽词 -> 正则 -> AI 翻译 -> 尾注 -> 延迟 -> RiskGuard 发布。
        返回处理状态码：forwarded / duplicate / blocked / failed。
        """
        # 1. 去重校验
        dup_stmt = select(SyncMessageHistory.id).where(
            and_(
                SyncMessageHistory.rule_id == rule.id,
                SyncMessageHistory.source_chat_id == source_chat_id,
                SyncMessageHistory.source_msg_id == source_msg_id,
            )
        )
        if (await db.execute(dup_stmt)).scalar_one_or_none() is not None:
            return "duplicate"

        # 2. 屏蔽词过滤
        hit_kw = contains_blocked_keyword(raw_text, rule.blocked_keywords or [])
        if hit_kw is not None:
            db.add(
                TaskLog(
                    account_id=rule.publisher_account_id,
                    action="sync_forward",
                    result="skipped",
                    target_ref=f"{source_chat_id}/{source_msg_id}",
                    error_detail=f"命中屏蔽词: {hit_kw}",
                )
            )
            await db.commit()
            return "blocked"

        # 3. 正则清洗
        processed_text = apply_regex_replacements(
            raw_text, rule.regex_replacements or []
        )

        # 4. AI 翻译
        if rule.enable_ai_translate and processed_text:
            processed_text = await translate_text_with_ai(
                processed_text, rule.ai_system_prompt
            )

        # 5. 追加底部文案
        if rule.append_footer:
            processed_text = (
                f"{processed_text}\n\n{rule.append_footer}"
                if processed_text
                else rule.append_footer
            )

        # 6. 随机延迟
        if delay_override is not None:
            min_d, max_d = delay_override
        else:
            min_d = float(rule.min_delay_sec)
            max_d = float(max(rule.min_delay_sec, rule.max_delay_sec))
        if max_d > 0:
            await asyncio.sleep(random.uniform(min_d, max_d))

        # 7. 交给 RiskGuard 由发布账号发出（不带转发来源标记）
        target_chat = _normalize_chat_ref(rule.target_chat_id)

        async def _send_coro(client: Any):
            if media_path is not None and media_path.exists():
                return await client.send_file(
                    target_chat,
                    file=str(media_path),
                    caption=processed_text or None,
                )
            return await client.send_message(target_chat, processed_text or " ")

        task_res = await run_safe_account_task(
            rule.publisher_account_id,
            "sync_forward",
            _send_coro,
            target_ref=rule.target_chat_id,
            db_session=db,
            jitter_range=(0.0, 0.0) if delay_override == (0.0, 0.0) else (2.0, 8.0),
        )
        if not task_res.success:
            return "failed"

        # 8. 写入去重历史
        target_msg_id = getattr(task_res.data, "id", None)
        db.add(
            SyncMessageHistory(
                rule_id=rule.id,
                source_chat_id=source_chat_id,
                source_msg_id=source_msg_id,
                target_msg_id=target_msg_id,
            )
        )
        await db.commit()
        return "forwarded"

    async def reload_rules(self) -> None:
        """热加载所有启用中的频道转发规则并挂载至常驻监听池。"""
        async with self._reload_lock:
            # 先卸载旧的监听处理器
            for acc_id, handler in self._registered_handlers:
                client = client_pool.get_pinned_client(acc_id)
                if client is not None:
                    try:
                        client.remove_event_handler(handler)
                    except Exception:
                        pass
            self._registered_handlers.clear()

            async with AsyncSessionLocal() as db:
                rules = list(
                    (
                        await db.execute(
                            select(ChannelSyncRule).where(
                                ChannelSyncRule.is_enabled.is_(True)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if not rules:
                    return

                # 按 listener_account_id 分组规则
                by_listener: dict[int, list[ChannelSyncRule]] = {}
                for rule in rules:
                    by_listener.setdefault(rule.listener_account_id, []).append(rule)

                for listener_id, acc_rules in by_listener.items():
                    account = (
                        await db.execute(
                            select(Account)
                            .options(
                                selectinload(Account.device_profile),
                                selectinload(Account.proxy),
                            )
                            .where(Account.id == listener_id)
                        )
                    ).scalar_one_or_none()
                    if account is None or account.status != "active":
                        logger.warning("监听账号 [id=%s] 不存在或非 active 状态，跳过挂载", listener_id)
                        continue

                    probe = await ProxyChecker.verify_proxy_alive(
                        db, account.proxy, commit=True
                    )
                    if not probe.alive:
                        logger.warning("监听账号 [id=%s] 代理不可达，严禁直连，跳过挂载", listener_id)
                        continue

                    try:
                        client = await client_pool.pin_listener_client(account)
                    except Exception as exc:
                        logger.error("常驻监听账号 [id=%s] 连接失败: %s", listener_id, exc)
                        continue

                    for rule in acc_rules:
                        chat_ref = _normalize_chat_ref(rule.source_chat_id)
                        rule_id = rule.id

                        async def _on_new_message(event: Any, rid: int = rule_id) -> None:
                            TEMP_DIR.mkdir(parents=True, exist_ok=True)
                            downloaded_path: Path | None = None
                            try:
                                if event.message and event.message.media:
                                    dl_target = TEMP_DIR / f"sync_{rid}_{uuid.uuid4().hex}"
                                    res_path = await event.message.download_media(
                                        file=str(dl_target)
                                    )
                                    if res_path:
                                        downloaded_path = Path(res_path)

                                async with AsyncSessionLocal() as session:
                                    latest_rule = await session.get(ChannelSyncRule, rid)
                                    if not latest_rule or not latest_rule.is_enabled:
                                        return
                                    await self.process_incoming_message(
                                        session,
                                        latest_rule,
                                        source_chat_id=latest_rule.source_chat_id,
                                        source_msg_id=event.message.id,
                                        raw_text=event.message.message or "",
                                        media_path=downloaded_path,
                                    )
                            except Exception as exc:
                                logger.exception("处理频道转发消息异常 [rule_id=%s]: %s", rid, exc)
                            finally:
                                if downloaded_path and downloaded_path.exists():
                                    downloaded_path.unlink(missing_ok=True)

                        builder = events.NewMessage(chats=[chat_ref])
                        client.add_event_handler(_on_new_message, builder)
                        self._registered_handlers.append((listener_id, _on_new_message))
                        logger.info(
                            "已挂载频道转发监听 [rule_id=%s, %s -> %s]",
                            rule.id,
                            rule.source_chat_id,
                            rule.target_chat_id,
                        )

            # 若某个常驻号已没有任何启用规则（包括关键词规则），可清理空闲监听
            async with AsyncSessionLocal() as db:
                kw_cnt = (
                    await db.execute(
                        select(KeywordRule.listener_account_id).where(
                            KeywordRule.is_enabled.is_(True)
                        )
                    )
                ).scalars().all()
                active_listener_ids = {r.listener_account_id for r in rules} | set(kw_cnt)
                for pinned_id in list(client_pool._pinned_clients.keys()):
                    if pinned_id not in active_listener_ids:
                        await client_pool.unpin_listener_client(pinned_id)


channel_sync_manager = ChannelSyncManager()

