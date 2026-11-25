import asyncio
import logging
import re
from typing import Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telethon import events

from app.core.database import AsyncSessionLocal
from app.core.ws_manager import ws_manager
from app.engine.guard import run_safe_account_task
from app.engine.pool import client_pool
from app.engine.proxy_checker import ProxyChecker
from app.models.account import Account
from app.models.channel_sync import ChannelSyncRule
from app.models.keyword import KeywordAlert, KeywordRule

logger = logging.getLogger(__name__)


def match_keyword_rule(
    text: str,
    keywords: list[str],
    exclude_keywords: list[str],
    match_mode: str = "contains",
) -> str | None:
    """
    检查文本是否命中关键词规则。
    优先级：先校验排除词（命中则直接跳过），再按 contains 或 regex 匹配关键词。
    """
    if not text:
        return None

    lowered = text.lower()
    for ex in exclude_keywords:
        ex_clean = ex.strip()
        if ex_clean and ex_clean.lower() in lowered:
            return None

    for kw in keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        if match_mode == "regex":
            try:
                if re.search(kw_clean, text, flags=re.IGNORECASE):
                    return kw_clean
            except re.error as exc:
                logger.warning("关键词正则无效 [%s]: %s", kw_clean, exc)
        else:
            if kw_clean.lower() in lowered:
                return kw_clean
    return None


def _normalize_chat_ref(chat_id: str) -> int | str:
    """将数字字符串群组/频道 ID 转为 int，@username 保持字符串。"""
    cleaned = chat_id.strip()
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return cleaned


async def _push_webhook(webhook_url: str, payload: dict[str, Any]) -> None:
    """异步 POST JSON 载荷到外部 Webhook（兼容飞书/钉钉/Telegram Bot）。"""
    try:
        timeout = aiohttp.ClientTimeout(total=10.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(webhook_url, json=payload) as resp:
                if resp.status >= 400:
                    logger.warning("外部 Webhook 推送返回状态 %s", resp.status)
    except Exception as exc:
        logger.warning("外部 Webhook 推送失败: %s", exc)


class KeywordMonitorManager:
    """关键词实时监控与告警管理器，支持规则热加载。"""

    def __init__(self) -> None:
        self._registered_handlers: list[tuple[int, Any]] = []
        self._reload_lock = asyncio.Lock()

    async def process_incoming_message(
        self,
        db: AsyncSession,
        rule: KeywordRule,
        *,
        source_chat_id: str,
        source_chat_title: str | None,
        sender_username: str | None,
        message_text: str,
        message_link: str | None,
    ) -> KeywordAlert | None:
        """匹配关键词并执行写库、WebSocket 广播、Webhook 推送与内部群转发。"""
        matched = match_keyword_rule(
            message_text,
            rule.keywords or [],
            rule.exclude_keywords or [],
            rule.match_mode,
        )
        if matched is None:
            return None

        # 1. 写入 keyword_alerts 表
        alert = KeywordAlert(
            rule_id=rule.id,
            matched_keyword=matched,
            source_chat_title=source_chat_title,
            source_chat_id=source_chat_id,
            sender_username=sender_username,
            message_text=message_text,
            message_link=message_link,
            is_read=False,
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)

        # 2. 广播实时告警给前端
        await ws_manager.broadcast(
            "keyword_alert",
            {
                "alert_id": alert.id,
                "rule_id": rule.id,
                "rule_name": rule.name,
                "matched_keyword": matched,
                "source_chat_title": source_chat_title,
                "source_chat_id": source_chat_id,
                "sender_username": sender_username,
                "message_text": message_text[:300],
                "message_link": message_link,
            },
        )

        # 3. 异步推送外部 Webhook
        if rule.alert_webhook_url:
            summary_text = (
                f"【关键词监控告警】规则: {rule.name}\n"
                f"命中词: {matched}\n"
                f"来源: {source_chat_title or source_chat_id}\n"
                f"发送者: @{sender_username or '未知'}\n"
                f"内容: {message_text[:300]}\n"
                f"链接: {message_link or '-'}"
            )
            asyncio.create_task(
                _push_webhook(
                    rule.alert_webhook_url,
                    {
                        "msg_type": "text",
                        "content": {"text": summary_text},
                        "text": summary_text,
                        "alert": {
                            "rule_name": rule.name,
                            "matched_keyword": matched,
                            "source_chat_id": source_chat_id,
                            "message_link": message_link,
                        },
                    },
                )
            )

        # 4. 可选通过 RiskGuard 转发告警至内部群
        if rule.alert_target_chat_id:
            target_chat = _normalize_chat_ref(rule.alert_target_chat_id)
            alert_msg = (
                f"🔔 **关键词命中告警**\n"
                f"• 规则：{rule.name}\n"
                f"• 关键词：`{matched}`\n"
                f"• 来源：{source_chat_title or source_chat_id}\n"
                f"• 内容：{message_text[:400]}\n"
                f"• 链接：{message_link or '无'}"
            )

            async def _send_alert_coro(client: Any):
                return await client.send_message(target_chat, alert_msg)

            await run_safe_account_task(
                rule.listener_account_id,
                "keyword_hit",
                _send_alert_coro,
                target_ref=rule.alert_target_chat_id,
                db_session=db,
            )

        return alert

    async def reload_rules(self) -> None:
        """热加载全部启用中的关键词监控规则并挂载监听事件。"""
        async with self._reload_lock:
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
                            select(KeywordRule).where(KeywordRule.is_enabled.is_(True))
                        )
                    )
                    .scalars()
                    .all()
                )

                by_listener: dict[int, list[KeywordRule]] = {}
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
                        continue

                    probe = await ProxyChecker.verify_proxy_alive(
                        db, account.proxy, commit=True
                    )
                    if not probe.alive:
                        logger.warning("关键词监听账号 [id=%s] 代理不可达，跳过挂载", listener_id)
                        continue

                    try:
                        client = await client_pool.pin_listener_client(account)
                    except Exception as exc:
                        logger.error("关键词监听账号 [id=%s] 连接失败: %s", listener_id, exc)
                        continue

                    for rule in acc_rules:
                        chats = [
                            _normalize_chat_ref(cid)
                            for cid in (rule.monitored_chat_ids or [])
                            if str(cid).strip()
                        ]
                        if not chats:
                            continue
                        rule_id = rule.id

                        async def _on_keyword_message(
                            event: Any, rid: int = rule_id
                        ) -> None:
                            try:
                                text = event.message.message or ""
                                if not text:
                                    return
                                chat = await event.get_chat()
                                sender = await event.get_sender()
                                chat_title = getattr(chat, "title", None) or getattr(
                                    chat, "username", None
                                )
                                chat_username = getattr(chat, "username", None)
                                chat_id_str = str(event.chat_id)
                                sender_username = getattr(sender, "username", None)
                                msg_link = (
                                    f"https://t.me/{chat_username}/{event.message.id}"
                                    if chat_username
                                    else None
                                )

                                async with AsyncSessionLocal() as session:
                                    latest_rule = await session.get(KeywordRule, rid)
                                    if not latest_rule or not latest_rule.is_enabled:
                                        return
                                    await self.process_incoming_message(
                                        session,
                                        latest_rule,
                                        source_chat_id=chat_id_str,
                                        source_chat_title=chat_title,
                                        sender_username=sender_username,
                                        message_text=text,
                                        message_link=msg_link,
                                    )
                            except Exception as exc:
                                logger.exception("关键词监控处理异常 [rule_id=%s]: %s", rid, exc)

                        builder = events.NewMessage(chats=chats)
                        client.add_event_handler(_on_keyword_message, builder)
                        self._registered_handlers.append(
                            (listener_id, _on_keyword_message)
                        )

                # 清理已没有任何启用规则的常驻监听账号
                sync_listener_ids = set(
                    (
                        await db.execute(
                            select(ChannelSyncRule.listener_account_id).where(
                                ChannelSyncRule.is_enabled.is_(True)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                active_ids = {r.listener_account_id for r in rules} | sync_listener_ids
                for pinned_id in list(client_pool._pinned_clients.keys()):
                    if pinned_id not in active_ids:
                        await client_pool.unpin_listener_client(pinned_id)


keyword_monitor_manager = KeywordMonitorManager()

