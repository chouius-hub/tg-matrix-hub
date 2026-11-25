import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import get_db  # noqa: E402
from app.engine.proxy_checker import ProxyChecker, ProxyCheckResult  # noqa: E402
from app.main import app  # noqa: E402
from app.models.proxy import Proxy  # noqa: E402
from app.workers.health_check import parse_spambot_reply  # noqa: E402


def _make_dummy_proxy(proxy_id: int = 1) -> Proxy:
    """构造测试用 Proxy ORM 对象。"""
    return Proxy(
        id=proxy_id,
        name="test-socks5",
        protocol="socks5",
        host="127.0.0.1",
        port=19999,
        username=None,
        password_encrypted=None,
        country_code="US",
        max_accounts=2,
        status="active",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_proxy_checker_unreachable_marks_dead() -> None:
    """验证代理不可达时返回 alive=False 且状态为 dead，绝不直连回退。"""
    proxy = _make_dummy_proxy()
    result = await ProxyChecker.check_proxy(proxy, timeout_sec=1.0)
    assert result.alive is False
    assert result.status == "dead"
    assert result.latency_ms is None
    assert result.error is not None


@pytest.mark.asyncio
async def test_proxy_checker_timeout_marks_dead() -> None:
    """验证代理探活超时时强制中止并标记为 dead。"""
    proxy = _make_dummy_proxy()

    class TimeoutSession:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def get(self, *args, **kwargs):
            raise asyncio.TimeoutError()

    with patch("app.engine.proxy_checker.aiohttp.ClientSession", TimeoutSession):
        result = await ProxyChecker.check_proxy(proxy, timeout_sec=0.1)

    assert result.alive is False
    assert result.status == "dead"
    assert "超时" in (result.error or "")


def test_parse_spambot_reply() -> None:
    """验证 @SpamBot 回复文本解析逻辑。"""
    status_ok, _ = parse_spambot_reply("Good news, no limits are currently applied to your account.")
    assert status_ok == "active"

    status_bad, _ = parse_spambot_reply("Unfortunately, your account is limited for spam.")
    assert status_bad == "restricted"


def test_import_routes_reject_invalid_file_extensions() -> None:
    """验证 tdata 与 session 导入路由的参数校验（非 zip / 非 session 被拦截）。"""
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        client = TestClient(app)

        resp_tdata = client.post(
            "/api/accounts/import/tdata",
            data={"proxy_id": "1"},
            files={"file": ("not_a_zip.txt", b"hello", "text/plain")},
        )
        assert resp_tdata.status_code == 400
        assert "zip" in resp_tdata.json()["detail"].lower()

        resp_session = client.post(
            "/api/accounts/import/session",
            data={"proxy_id": "1"},
            files={"session_file": ("invalid.txt", b"hello", "text/plain")},
        )
        assert resp_session.status_code == 400
        assert "session" in resp_session.json()["detail"].lower()

        resp_phone_send = client.post(
            "/api/accounts/import/phone/send-code",
            json={"phone": "12", "proxy_id": 1},
        )
        assert resp_phone_send.status_code == 422

        resp_phone_verify = client.post(
            "/api/accounts/import/phone/verify",
            json={"login_token": "", "code": "1"},
        )
        assert resp_phone_verify.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_import_blocked_when_proxy_dead_without_direct_fallback() -> None:
    """核心红线测试：代理探活失败时，导入接口明确报错且绝不初始化 TelegramClient。"""
    proxy = _make_dummy_proxy(proxy_id=99)

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=proxy)
    mock_count_result = MagicMock()
    mock_count_result.scalar_one.return_value = 0
    mock_none_result = MagicMock()
    mock_none_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[mock_none_result, mock_count_result])

    dead_probe = ProxyCheckResult(
        alive=False, status="dead", latency_ms=None, error="连接超时"
    )

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        client = TestClient(app)
        with (
            patch.object(
                ProxyChecker, "verify_proxy_alive", AsyncMock(return_value=dead_probe)
            ),
            patch("app.engine.converter.TelegramClient") as mock_tg_client,
        ):
            resp = client.post(
                "/api/accounts/import/phone/send-code",
                json={"phone": "+12025550123", "proxy_id": 99},
            )
        assert resp.status_code == 400
        assert "严禁直连" in resp.json()["detail"]
        mock_tg_client.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_swagger_openapi_contains_phase1_routes() -> None:
    """验证 Swagger OpenAPI 文档包含全部代理、账号及 3 种导入接口。"""
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]

    expected_paths = [
        "/api/health",
        "/api/proxies",
        "/api/proxies/{proxy_id}/check",
        "/api/accounts",
        "/api/accounts/import/tdata",
        "/api/accounts/import/session",
        "/api/accounts/import/phone/send-code",
        "/api/accounts/import/phone/verify",
        "/api/accounts/{account_id}/health-check",
        "/api/accounts/batch-health-check",
    ]
    for path in expected_paths:
        assert path in paths, f"缺少路由: {path}"

