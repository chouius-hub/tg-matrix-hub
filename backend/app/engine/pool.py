import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient

from app.engine.proxy_checker import build_telethon_proxy
from app.models.account import Account

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass
class _PooledClient:
    """LRU 任务池中的客户端封装。"""

    account_id: int
    client: TelegramClient
    last_used_at: float


class ClientPoolManager:
    """Telegram 客户端连接池管理器（单账号互斥锁 + 常驻监听池 + LRU 任务池）。"""

    def __init__(self, max_lru_size: int = 20, idle_timeout_sec: float = 600.0) -> None:
        self._max_lru_size = max_lru_size
        self._idle_timeout_sec = idle_timeout_sec
        self._account_locks: dict[int, asyncio.Lock] = {}
        self._pinned_clients: dict[int, TelegramClient] = {}
        self._lru_clients: OrderedDict[int, _PooledClient] = OrderedDict()
        self._cleanup_task: asyncio.Task[None] | None = None

    def get_account_lock(self, account_id: int) -> asyncio.Lock:
        """获取指定账号的独占异步互斥锁，严禁并发操作同一 .session 文件。"""
        lock = self._account_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            self._account_locks[account_id] = lock
        return lock

    def get_stats(self) -> dict[str, int]:
        """返回当前连接池统计信息。"""
        return {
            "pinned_count": len(self._pinned_clients),
            "lru_count": len(self._lru_clients),
            "total_active_clients": len(self._pinned_clients) + len(self._lru_clients),
        }

    def _build_client(self, account: Account) -> TelegramClient:
        """严格使用数据库固化设备指纹与绑定代理构造 TelegramClient。"""
        session_path = BACKEND_DIR / account.session_file_path
        if not session_path.exists():
            raise FileNotFoundError(f"Session 文件不存在: {session_path}")

        profile = account.device_profile
        proxy_tuple = build_telethon_proxy(account.proxy)
        return TelegramClient(
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

    async def get_task_client(self, account: Account) -> TelegramClient:
        """从常驻池或 LRU 任务池获取已连接的 TelegramClient。"""
        # 若该账号已是常驻监听客户端，直接复用
        pinned = self._pinned_clients.get(account.id)
        if pinned is not None:
            if not pinned.is_connected():
                await pinned.connect()
            return pinned

        entry = self._lru_clients.get(account.id)
        if entry is not None:
            self._lru_clients.move_to_end(account.id)
            entry.last_used_at = time.monotonic()
            if not entry.client.is_connected():
                await entry.client.connect()
            return entry.client

        # 超出 LRU 容量上限时，驱逐并断开最久未使用的连接
        while len(self._lru_clients) >= self._max_lru_size:
            evicted_id, evicted_entry = self._lru_clients.popitem(last=False)
            logger.info("LRU 池已满，断开最久未使用的账号连接 [account_id=%s]", evicted_id)
            await self._safe_disconnect(evicted_entry.client)

        client = self._build_client(account)
        await client.connect()
        self._lru_clients[account.id] = _PooledClient(
            account_id=account.id,
            client=client,
            last_used_at=time.monotonic(),
        )
        return client

    async def pin_listener_client(self, account: Account) -> TelegramClient:
        """为常驻监听任务注册并连接持久化客户端。"""
        existing = self._pinned_clients.get(account.id)
        if existing is not None:
            if not existing.is_connected():
                await existing.connect()
            return existing

        # 若此前存在于 LRU 池，则升级为常驻客户端
        lru_entry = self._lru_clients.pop(account.id, None)
        if lru_entry is not None:
            client = lru_entry.client
            if not client.is_connected():
                await client.connect()
            self._pinned_clients[account.id] = client
            return client

        client = self._build_client(account)
        await client.connect()
        self._pinned_clients[account.id] = client
        return client

    async def unpin_listener_client(self, account_id: int) -> None:
        """卸载并断开不再需要的常驻监听客户端。"""
        client = self._pinned_clients.pop(account_id, None)
        if client is not None:
            await self._safe_disconnect(client)

    def get_pinned_client(self, account_id: int) -> TelegramClient | None:
        """获取已注册的常驻监听客户端（若存在）。"""
        return self._pinned_clients.get(account_id)

    async def evict_client(self, account_id: int) -> None:
        """强制断开并移除指定账号在池中的连接（风控失效或删除账号时调用）。"""
        pinned = self._pinned_clients.pop(account_id, None)
        if pinned is not None:
            await self._safe_disconnect(pinned)
        lru_entry = self._lru_clients.pop(account_id, None)
        if lru_entry is not None:
            await self._safe_disconnect(lru_entry.client)

    async def cleanup_idle_clients(self) -> int:
        """清理 LRU 池中闲置超过阈值的连接，返回本次清理数量。"""
        now_ts = time.monotonic()
        expired_ids = [
            acc_id
            for acc_id, entry in self._lru_clients.items()
            if now_ts - entry.last_used_at > self._idle_timeout_sec
        ]
        for acc_id in expired_ids:
            entry = self._lru_clients.pop(acc_id, None)
            if entry is not None:
                logger.info("断开闲置超过 10 分钟的账号连接 [account_id=%s]", acc_id)
                await self._safe_disconnect(entry.client)
        return len(expired_ids)

    def start_background_cleanup(self, interval_sec: float = 120.0) -> None:
        """启动每 2 分钟扫描一次闲置连接的后台任务。"""
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        async def _loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval_sec)
                    await self.cleanup_idle_clients()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("LRU 池闲置清理任务异常: %s", exc)

        self._cleanup_task = asyncio.create_task(_loop(), name="lru-pool-cleanup")

    async def close_all(self) -> None:
        """优雅关闭后台清理任务并断开全部客户端连接。"""
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        for acc_id in list(self._pinned_clients.keys()):
            client = self._pinned_clients.pop(acc_id)
            await self._safe_disconnect(client)

        for acc_id in list(self._lru_clients.keys()):
            entry = self._lru_clients.pop(acc_id)
            await self._safe_disconnect(entry.client)

        logger.info("ClientPoolManager 已优雅关闭全部连接。")

    @staticmethod
    async def _safe_disconnect(client: Any) -> None:
        """安全断开客户端连接，忽略断开阶段非关键异常。"""
        try:
            await client.disconnect()
        except Exception as exc:
            logger.debug("断开客户端连接时出现异常: %s", exc)


client_pool = ClientPoolManager()

