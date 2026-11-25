import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engine.guard import SafeTaskResult  # noqa: E402
from app.models.channel_sync import ChannelSyncRule, SyncMessageHistory  # noqa: E402
from app.models.scheduled_post import ScheduledPost  # noqa: E402
from app.models.task import TaskLog  # noqa: E402
from app.workers.channel_sync import (  # noqa: E402
    ChannelSyncManager,
    apply_regex_replacements,
    contains_blocked_keyword,
)
from app.workers.scheduled_post import dispatch_single_scheduled_post  # noqa: E402


def test_regex_and_blocked_keyword_helpers() -> None:
    """验证正则清洗与屏蔽词过滤逻辑。"""
    assert contains_blocked_keyword("限时免费空投活动", ["博彩", "空投"]) == "空投"
    assert contains_blocked_keyword("正常技术新闻", ["博彩", "空投"]) is None

    cleaned = apply_regex_replacements(
        "Join @old_channel for news! Ad: http://spam.test",
        [
            {"pattern": r"@old_channel", "replace": "@my_channel"},
            {"pattern": r"Ad:\s*https?://\S+", "replace": ""},
        ],
    )
    assert cleaned == "Join @my_channel for news!"


@pytest.mark.asyncio
async def test_channel_sync_dedup_and_ai_translate_flow() -> None:
    """验证频道转发去重拦截、AI 翻译 Mock 流程与追加尾注。"""
    manager = ChannelSyncManager()
    rule = ChannelSyncRule(
        id=1,
        name="test-sync",
        listener_account_id=1,
        publisher_account_id=2,
        source_chat_id="@src",
        target_chat_id="@dst",
        enable_ai_translate=True,
        ai_system_prompt="翻译为中文",
        regex_replacements=[{"pattern": "@old", "replace": "@new"}],
        blocked_keywords=["scam"],
        append_footer="— 来自我的频道",
        min_delay_sec=0,
        max_delay_sec=0,
        is_enabled=True,
    )

    # 1. 模拟已存在历史记录 -> 去重拦截
    mock_db_dup = AsyncMock()
    dup_res = MagicMock()
    dup_res.scalar_one_or_none.return_value = 999
    mock_db_dup.execute = AsyncMock(return_value=dup_res)
    status_dup = await manager.process_incoming_message(
        mock_db_dup,
        rule,
        source_chat_id="@src",
        source_msg_id=10,
        raw_text="Hello @old",
        delay_override=(0.0, 0.0),
    )
    assert status_dup == "duplicate"

    # 2. 模拟命中屏蔽词 -> 跳过并写 TaskLog
    added_blocked: list[object] = []
    mock_db_blk = AsyncMock()
    no_dup_res = MagicMock()
    no_dup_res.scalar_one_or_none.return_value = None
    mock_db_blk.execute = AsyncMock(return_value=no_dup_res)
    mock_db_blk.add = MagicMock(side_effect=lambda obj: added_blocked.append(obj))
    mock_db_blk.commit = AsyncMock()

    status_blk = await manager.process_incoming_message(
        mock_db_blk,
        rule,
        source_chat_id="@src",
        source_msg_id=11,
        raw_text="This is a SCAM link",
        delay_override=(0.0, 0.0),
    )
    assert status_blk == "blocked"
    assert any(isinstance(x, TaskLog) and x.result == "skipped" for x in added_blocked)

    # 3. 模拟正常消息 -> 正则清洗 + AI 翻译 + 尾注 + RiskGuard 发布 + 写入去重表
    added_ok: list[object] = []
    mock_db_ok = AsyncMock()
    mock_db_ok.execute = AsyncMock(return_value=no_dup_res)
    mock_db_ok.add = MagicMock(side_effect=lambda obj: added_ok.append(obj))
    mock_db_ok.commit = AsyncMock()

    captured_text: list[str] = []

    async def _fake_guard(account_id, action_name, coro_factory, **kwargs):
        fake_client = MagicMock()

        async def _fake_send_message(_target, text, **_kw):
            captured_text.append(text)
            return SimpleNamespace(id=777)

        fake_client.send_message = _fake_send_message
        data = await coro_factory(fake_client)
        return SafeTaskResult(success=True, result_code="success", data=data)

    with (
        patch(
            "app.workers.channel_sync.translate_text_with_ai",
            AsyncMock(return_value="你好 @new"),
        ),
        patch("app.workers.channel_sync.run_safe_account_task", side_effect=_fake_guard),
    ):
        status_ok = await manager.process_incoming_message(
            mock_db_ok,
            rule,
            source_chat_id="@src",
            source_msg_id=12,
            raw_text="Hello @old",
            delay_override=(0.0, 0.0),
        )

    assert status_ok == "forwarded"
    assert captured_text == ["你好 @new\n\n— 来自我的频道"]
    assert any(
        isinstance(x, SyncMessageHistory) and x.target_msg_id == 777 for x in added_ok
    )


@pytest.mark.asyncio
async def test_scheduled_post_atomic_lock_and_dispatch() -> None:
    """验证定时发帖原子抢锁、调用 RiskGuard 发送多频道并更新状态为 sent。"""
    post = ScheduledPost(
        id=5,
        title="定时测试帖",
        publisher_account_id=3,
        target_chat_ids=["@ch_a", "@ch_b"],
        content_text="<b>Hello</b>",
        parse_mode="html",
        media_file_path=None,
        disable_web_page_preview=False,
        scheduled_at=datetime.now(timezone.utc),
        status="pending",
    )

    mock_db = AsyncMock()
    lock_res = MagicMock()
    lock_res.scalar_one_or_none.return_value = 5
    mock_db.execute = AsyncMock(return_value=lock_res)
    mock_db.get = AsyncMock(return_value=post)
    mock_db.commit = AsyncMock()

    sent_targets: list[str] = []

    async def _fake_guard(account_id, action_name, coro_factory, **kwargs):
        sent_targets.append(kwargs["target_ref"])
        fake_client = MagicMock()
        fake_client.send_message = AsyncMock(return_value=SimpleNamespace(id=100))
        data = await coro_factory(fake_client)
        return SafeTaskResult(success=True, result_code="success", data=data)

    with patch("app.workers.scheduled_post.run_safe_account_task", side_effect=_fake_guard):
        final_status = await dispatch_single_scheduled_post(
            mock_db,
            5,
            channel_delay_range=(0.0, 0.0),
            guard_jitter_range=(0.0, 0.0),
        )

    assert final_status == "sent"
    assert post.status == "sent"
    assert post.sent_at is not None
    assert sent_targets == ["@ch_a", "@ch_b"]

