import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.errors import FloodWaitError, PeerFloodError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.engine.guard import run_safe_account_task  # noqa: E402
from app.engine.pool import ClientPoolManager  # noqa: E402
from app.engine.proxy_checker import ProxyChecker, ProxyCheckResult  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.device_profile import DeviceProfile  # noqa: E402
from app.models.proxy import Proxy  # noqa: E402
from app.models.task import TaskLog  # noqa: E402


def _make_mock_account(account_id: int = 1) -> Account:
    """构造用于风控单元测试的活跃账号、设备指纹与代理对象。"""
    proxy = Proxy(
        id=10,
        name="us-socks5",
        protocol="socks5",
        host="127.0.0.1",
        port=1080,
        max_accounts=2,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    profile = DeviceProfile(
        id=10,
        platform="desktop",
        api_id=2040,
        api_hash="b18441a1ff607e10a989891a5462e627",
        device_model="Desktop",
        system_version="Windows 10",
        app_version="4.16.0",
        lang_code="en",
        system_lang_code="en-US",
        unique_seed=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
    )
    return Account(
        id=account_id,
        account_uuid=uuid.uuid4(),
        phone="+12025550101",
        import_source="session",
        session_file_path="storage/sessions/mock.session",
        account_role="worker",
        device_profile_id=10,
        proxy_id=10,
        status="active",
        health_score=100,
        cooldown_until=None,
        timezone="UTC",
        quiet_hours_enabled=False,
        daily_action_count=0,
        daily_action_limit=30,
        device_profile=profile,
        proxy=proxy,
    )


def _make_mock_db(account: Account) -> tuple[AsyncMock, list[TaskLog]]:
    """构造捕获 db.add(TaskLog) 的异步数据库 Session Mock。"""
    added_logs: list[TaskLog] = []

    mock_db = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = account
    mock_db.execute = AsyncMock(return_value=exec_result)
    mock_db.commit = AsyncMock()

    def _capture_add(obj) -> None:
        if isinstance(obj, TaskLog):
            added_logs.append(obj)

    mock_db.add = MagicMock(side_effect=_capture_add)
    return mock_db, added_logs


@pytest.mark.asyncio
async def test_guard_flood_wait_triggers_cooldown() -> None:
    """模拟 FloodWaitError(60)：账号置为 cooldown、cooldown_until 正确、健康分-15、写 task_logs。"""
    account = _make_mock_account(account_id=101)
    mock_db, logs = _make_mock_db(account)

    alive_probe = ProxyCheckResult(alive=True, status="active", latency_ms=50)
    mock_client = MagicMock()

    async def _raise_flood(_client):
        err = FloodWaitError(request=None, capture=60)
        err.seconds = 60
        raise err

    before_ts = datetime.now(timezone.utc)
    with (
        patch.object(ProxyChecker, "verify_proxy_alive", AsyncMock(return_value=alive_probe)),
        patch("app.engine.guard.client_pool.get_task_client", AsyncMock(return_value=mock_client)),
        patch("app.engine.guard.client_pool.evict_client", AsyncMock()) as mock_evict,
        patch("app.engine.guard.ws_manager.broadcast", AsyncMock()),
    ):
        result = await run_safe_account_task(
            101,
            "send_post",
            _raise_flood,
            target_ref="@test_ch",
            db_session=mock_db,
            jitter_range=(0.0, 0.0),
        )

    assert result.success is False
    assert result.result_code == "flood_wait"
    assert account.status == "cooldown"
    assert account.health_score == 85
    assert account.cooldown_until is not None
    assert account.cooldown_until >= before_ts + timedelta(seconds=90)
    assert len(logs) == 1
    assert logs[0].result == "flood_wait"
    assert logs[0].wait_seconds == 60
    mock_evict.assert_awaited_once_with(101)


@pytest.mark.asyncio
async def test_guard_peer_flood_restricts_without_retry() -> None:
    """模拟 PeerFloodError：账号置为 restricted、健康分-40、绝不重试。"""
    account = _make_mock_account(account_id=102)
    mock_db, logs = _make_mock_db(account)

    alive_probe = ProxyCheckResult(alive=True, status="active", latency_ms=40)
    mock_client = MagicMock()
    call_count = 0

    async def _raise_peer_flood(_client):
        nonlocal call_count
        call_count += 1
        raise PeerFloodError(request=None)

    with (
        patch.object(ProxyChecker, "verify_proxy_alive", AsyncMock(return_value=alive_probe)),
        patch("app.engine.guard.client_pool.get_task_client", AsyncMock(return_value=mock_client)),
        patch("app.engine.guard.client_pool.evict_client", AsyncMock()),
        patch("app.engine.guard.ws_manager.broadcast", AsyncMock()),
    ):
        result = await run_safe_account_task(
            102,
            "send_post",
            _raise_peer_flood,
            target_ref="@target",
            db_session=mock_db,
            jitter_range=(0.0, 0.0),
        )

    assert result.success is False
    assert result.result_code == "peer_flood"
    assert call_count == 1
    assert account.status == "restricted"
    assert account.health_score == 60
    assert len(logs) == 1
    assert logs[0].result == "peer_flood"


@pytest.mark.asyncio
async def test_guard_proxy_dead_aborts_before_connect() -> None:
    """模拟代理探活失败：直接返回 proxy_dead，绝不获取或连接 TelegramClient。"""
    account = _make_mock_account(account_id=103)
    mock_db, logs = _make_mock_db(account)

    dead_probe = ProxyCheckResult(
        alive=False, status="dead", latency_ms=None, error="连接超时"
    )
    coro_mock = AsyncMock()

    with (
        patch.object(ProxyChecker, "verify_proxy_alive", AsyncMock(return_value=dead_probe)),
        patch("app.engine.guard.client_pool.get_task_client", AsyncMock()) as mock_get_client,
        patch("app.engine.guard.ws_manager.broadcast", AsyncMock()),
    ):
        result = await run_safe_account_task(
            103,
            "send_post",
            coro_mock,
            db_session=mock_db,
            jitter_range=(0.0, 0.0),
        )

    assert result.success is False
    assert result.result_code == "proxy_dead"
    assert account.health_score == 95
    assert len(logs) == 1
    assert logs[0].result == "proxy_dead"
    mock_get_client.assert_not_awaited()
    coro_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_pool_lru_eviction() -> None:
    """验证 ClientPoolManager 达到上限时驱逐最久未使用的连接。"""
    pool = ClientPoolManager(max_lru_size=2, idle_timeout_sec=600.0)
    created_clients: dict[int, MagicMock] = {}

    def _fake_build(account: Account):
        c = MagicMock()
        c.is_connected.return_value = True
        c.connect = AsyncMock()
        c.disconnect = AsyncMock()
        created_clients[account.id] = c
        return c

    with patch.object(pool, "_build_client", side_effect=_fake_build):
        a1 = _make_mock_account(1)
        a2 = _make_mock_account(2)
        a3 = _make_mock_account(3)

        await pool.get_task_client(a1)
        await pool.get_task_client(a2)
        # 访问 a1 使其变为最近使用，接下来插入 a3 应驱逐 a2
        await pool.get_task_client(a1)
        await pool.get_task_client(a3)

    assert pool.get_stats()["lru_count"] == 2
    assert 2 not in pool._lru_clients
    assert 1 in pool._lru_clients and 3 in pool._lru_clients
    created_clients[2].disconnect.assert_awaited_once()
    await pool.close_all()

