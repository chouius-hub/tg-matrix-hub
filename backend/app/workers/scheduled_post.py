import asyncio
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.engine.guard import run_safe_account_task
from app.models.scheduled_post import ScheduledPost

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _normalize_chat_ref(chat_id: str) -> int | str:
    """将数字字符串频道 ID 转为 int，@username 保持字符串。"""
    cleaned = chat_id.strip()
    if cleaned.lstrip("-").isdigit():
        return int(cleaned)
    return cleaned


async def dispatch_single_scheduled_post(
    db: AsyncSession,
    post_id: int,
    *,
    channel_delay_range: tuple[float, float] = (10.0, 30.0),
    guard_jitter_range: tuple[float, float] = (2.0, 8.0),
) -> str:
    """
    原子抢锁并执行单条到期定时发帖任务。
    返回最终状态：sent / failed / skipped_lock。
    """
    # 原子抢锁：仅当状态仍为 pending 时更新为 running，防止并发重复发送
    lock_stmt = (
        update(ScheduledPost)
        .where(
            and_(
                ScheduledPost.id == post_id,
                ScheduledPost.status == "pending",
            )
        )
        .values(status="running")
        .returning(ScheduledPost.id)
    )
    locked_id = (await db.execute(lock_stmt)).scalar_one_or_none()
    if locked_id is None:
        return "skipped_lock"
    await db.commit()

    post = await db.get(ScheduledPost, post_id)
    if post is None:
        return "failed"

    media_abs_path: Path | None = None
    if post.media_file_path:
        candidate = BACKEND_DIR / post.media_file_path
        if candidate.exists():
            media_abs_path = candidate

    errors: list[str] = []
    targets = [str(t).strip() for t in (post.target_chat_ids or []) if str(t).strip()]
    for idx, target_str in enumerate(targets):
        target_chat = _normalize_chat_ref(target_str)

        async def _send_coro(client: Any):
            if media_abs_path is not None:
                return await client.send_file(
                    target_chat,
                    file=str(media_abs_path),
                    caption=post.content_text,
                    parse_mode=post.parse_mode,
                )
            return await client.send_message(
                target_chat,
                post.content_text,
                parse_mode=post.parse_mode,
                link_preview=not post.disable_web_page_preview,
            )

        res = await run_safe_account_task(
            post.publisher_account_id,
            "send_post",
            _send_coro,
            target_ref=target_str,
            db_session=db,
            jitter_range=guard_jitter_range,
        )
        if not res.success:
            errors.append(f"{target_str}: {res.error or res.result_code}")

        # 多个目标频道之间插入 10~30 秒随机延迟
        if idx < len(targets) - 1 and channel_delay_range[1] > 0:
            await asyncio.sleep(random.uniform(*channel_delay_range))

    if errors:
        post.status = "failed"
        post.error_message = " | ".join(errors)[:1000]
    else:
        post.status = "sent"
        post.sent_at = datetime.now(timezone.utc)
        post.error_message = None

    await db.commit()
    return post.status


async def scan_and_dispatch_due_posts() -> None:
    """APScheduler 每 30 秒调用：扫描并执行所有已到期的定时发帖任务。"""
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        due_ids = list(
            (
                await db.execute(
                    select(ScheduledPost.id)
                    .where(
                        and_(
                            ScheduledPost.status == "pending",
                            ScheduledPost.scheduled_at <= now_utc,
                        )
                    )
                    .order_by(ScheduledPost.scheduled_at.asc())
                )
            )
            .scalars()
            .all()
        )

    for post_id in due_ids:
        async with AsyncSessionLocal() as task_db:
            try:
                await dispatch_single_scheduled_post(task_db, post_id)
            except Exception as exc:
                logger.exception("执行定时发帖任务 [id=%s] 异常: %s", post_id, exc)

