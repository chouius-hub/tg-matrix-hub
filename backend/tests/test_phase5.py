import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402
from app.models.keyword import KeywordAlert, KeywordRule  # noqa: E402
from app.workers.keyword_monitor import (  # noqa: E402
    KeywordMonitorManager,
    match_keyword_rule,
)


def test_keyword_match_contains_mode() -> None:
    """验证包含模式下的大小写不敏感匹配。"""
    matched = match_keyword_rule(
        "重磅：限时 AirDrop 空投活动开启",
        keywords=["空投", "免费API"],
        exclude_keywords=[],
        match_mode="contains",
    )
    assert matched == "空投"

    assert (
        match_keyword_rule(
            "普通市场分析文章",
            keywords=["空投", "免费API"],
            exclude_keywords=[],
            match_mode="contains",
        )
        is None
    )


def test_keyword_match_regex_mode() -> None:
    """验证正则模式匹配与非法正则容错。"""
    matched = match_keyword_rule(
        "New key: sk-abc123456789",
        keywords=[r"sk-[a-z0-9]{8,}"],
        exclude_keywords=[],
        match_mode="regex",
    )
    assert matched == r"sk-[a-z0-9]{8,}"

    # 非法正则不应崩溃
    assert (
        match_keyword_rule(
            "hello world",
            keywords=[r"[unclosed"],
            exclude_keywords=[],
            match_mode="regex",
        )
        is None
    )


def test_keyword_exclude_priority_over_match() -> None:
    """验证排除词优先级高于包含/正则匹配。"""
    assert (
        match_keyword_rule(
            "警惕：假消息！不要参加所谓空投活动",
            keywords=["空投"],
            exclude_keywords=["假消息", "钓鱼"],
            match_mode="contains",
        )
        is None
    )
    assert (
        match_keyword_rule(
            "钓鱼链接 sk-abc123456789 请勿点击",
            keywords=[r"sk-[a-z0-9]{8,}"],
            exclude_keywords=["钓鱼"],
            match_mode="regex",
        )
        is None
    )


@pytest.mark.asyncio
async def test_keyword_monitor_alert_pipeline() -> None:
    """验证关键词命中后写库 KeywordAlert 并推送 WebSocket 告警。"""
    manager = KeywordMonitorManager()
    rule = KeywordRule(
        id=10,
        name="监控测试",
        listener_account_id=1,
        monitored_chat_ids=["@test_group"],
        keywords=["空投"],
        match_mode="contains",
        exclude_keywords=["骗局"],
        alert_webhook_url=None,
        alert_target_chat_id=None,
        is_enabled=True,
    )

    added: list[object] = []
    mock_db = AsyncMock()
    mock_db.add = MagicMock(side_effect=lambda obj: added.append(obj))
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("app.workers.keyword_monitor.ws_manager.broadcast", AsyncMock()) as mock_ws:
        alert = await manager.process_incoming_message(
            mock_db,
            rule,
            source_chat_id="-100123",
            source_chat_title="测试群",
            sender_username="alice",
            message_text="最新官方空投公告",
            message_link="https://t.me/test_group/42",
        )

    assert alert is not None
    assert any(isinstance(x, KeywordAlert) and x.matched_keyword == "空投" for x in added)
    mock_ws.assert_awaited_once()


def test_openapi_contains_all_business_routes() -> None:
    """验证全部业务路由均已注册至 OpenAPI。"""
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for p in [
        "/api/sync-rules",
        "/api/sync-rules/{rule_id}/toggle",
        "/api/scheduled-posts",
        "/api/uploads/media",
        "/api/keyword-rules",
        "/api/keyword-alerts",
        "/api/keyword-alerts/{alert_id}/read",
    ]:
        assert p in paths, f"缺少路由: {p}"

