import asyncio
import sys
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import delete

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.account import Account  # noqa: E402
from app.models.device_profile import DeviceProfile  # noqa: E402
from app.models.proxy import Proxy  # noqa: E402

STATUSES = ["active", "active", "active", "cooldown", "restricted", "frozen"]
ROLES = ["worker", "worker", "listener", "publisher"]


async def seed_mock_data() -> tuple[list[int], list[int], list[int]]:
    """插入 50 条模拟代理与 100 条模拟账号数据。"""
    proxy_ids: list[int] = []
    profile_ids: list[int] = []
    account_ids: list[int] = []

    async with AsyncSessionLocal() as db:
        for i in range(50):
            proxy = Proxy(
                name=f"bench-proxy-{i+1}",
                protocol="socks5",
                host="127.0.0.1",
                port=20000 + i,
                country_code="US",
                max_accounts=2,
                status="active",
                latency_ms=80 + i,
            )
            db.add(proxy)
            await db.flush()
            proxy_ids.append(proxy.id)

        for i in range(100):
            acc_uuid = uuid.uuid4()
            profile = DeviceProfile(
                platform="android",
                api_id=2040,
                api_hash="b18441a1ff607e10a989891a5462e627",
                device_model=f"Pixel {6 + (i % 3)}",
                system_version="Android 14",
                app_version="10.9.1",
                lang_code="en",
                system_lang_code="en-US",
                unique_seed=f"bench_{acc_uuid.hex}",
            )
            db.add(profile)
            await db.flush()
            profile_ids.append(profile.id)

            account = Account(
                account_uuid=acc_uuid,
                phone=f"+1999555{1000 + i:04d}",
                country_code="US",
                tg_user_id=900000000 + i,
                username=f"bench_user_{i+1}",
                first_name=f"Bench{i+1}",
                import_source="session",
                session_file_path=f"storage/sessions/{acc_uuid}.session",
                account_role=ROLES[i % len(ROLES)],
                device_profile_id=profile.id,
                proxy_id=proxy_ids[i // 2],
                status=STATUSES[i % len(STATUSES)],
                health_score=100 - (i % 30),
                daily_action_count=i % 15,
                daily_action_limit=30,
            )
            db.add(account)
            await db.flush()
            account_ids.append(account.id)

        await db.commit()
    return proxy_ids, profile_ids, account_ids


async def cleanup_mock_data(
    proxy_ids: list[int], profile_ids: list[int], account_ids: list[int]
) -> None:
    """清理压测注入的模拟数据，保持数据库干净。"""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Account).where(Account.id.in_(account_ids)))
        await db.execute(delete(DeviceProfile).where(DeviceProfile.id.in_(profile_ids)))
        await db.execute(delete(Proxy).where(Proxy.id.in_(proxy_ids)))
        await db.commit()


async def main() -> None:
    proxy_ids, profile_ids, account_ids = await seed_mock_data()
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
            t0 = time.perf_counter()
            stats_resp = await client.get("/api/system/stats")
            stats_ms = (time.perf_counter() - t0) * 1000
            stats_data = stats_resp.json()

            t1 = time.perf_counter()
            acc_resp = await client.get("/api/accounts")
            acc_ms = (time.perf_counter() - t1) * 1000
            acc_data = acc_resp.json()

            t2 = time.perf_counter()
            proxy_resp = await client.get("/api/proxies")
            proxy_ms = (time.perf_counter() - t2) * 1000
            proxy_data = proxy_resp.json()

            print(f"STATS_TOTAL_ACCOUNTS={stats_data['total_accounts']} STATS_MS={stats_ms:.2f}")
            print(f"ACCOUNTS_LEN={len(acc_data)} ACCOUNTS_MS={acc_ms:.2f}")
            print(f"PROXIES_LEN={len(proxy_data)} PROXIES_MS={proxy_ms:.2f}")
            assert stats_data["total_accounts"] >= 100
            assert len(acc_data) >= 100
            assert stats_ms < 200.0
    finally:
        await cleanup_mock_data(proxy_ids, profile_ids, account_ids)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

