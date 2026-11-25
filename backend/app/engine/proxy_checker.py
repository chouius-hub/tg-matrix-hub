import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp
import socks
from aiohttp_socks import ProxyConnector
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models.proxy import Proxy

logger = logging.getLogger(__name__)

PROXY_CHECK_TIMEOUT_SEC = 8.0
SLOW_LATENCY_THRESHOLD_MS = 2500
# 通过代理访问 Telegram 官方 API 域名探活，同时避免任何直连回退
PROXY_PROBE_URL = "https://api.telegram.org"


@dataclass(slots=True)
class ProxyCheckResult:
    """代理探活结果数据结构。"""

    alive: bool
    status: str
    latency_ms: int | None
    error: str | None = None


def _build_proxy_url(proxy: Proxy) -> str:
    """构造供 aiohttp-socks 使用的代理 URL，严禁在外部日志中打印返回值。"""
    scheme = "socks5" if proxy.protocol.lower() == "socks5" else "http"
    auth_part = ""
    if proxy.username:
        user_encoded = quote(proxy.username, safe="")
        if proxy.password_encrypted:
            raw_password = decrypt_secret(proxy.password_encrypted)
            pass_encoded = quote(raw_password, safe="")
            auth_part = f"{user_encoded}:{pass_encoded}@"
        else:
            auth_part = f"{user_encoded}@"
    return f"{scheme}://{auth_part}{proxy.host}:{proxy.port}"


def build_telethon_proxy(proxy: Proxy) -> tuple:
    """将数据库 Proxy 模型转换为 Telethon / PySocks 所需的代理元组。"""
    proxy_type = socks.SOCKS5 if proxy.protocol.lower() == "socks5" else socks.HTTP
    if proxy.username:
        password = (
            decrypt_secret(proxy.password_encrypted)
            if proxy.password_encrypted
            else None
        )
        return (proxy_type, proxy.host, proxy.port, True, proxy.username, password)
    return (proxy_type, proxy.host, proxy.port)


class ProxyChecker:
    """代理强制探活器：仅通过代理发起连接，绝对禁止直连回退。"""

    @staticmethod
    async def check_proxy(
        proxy: Proxy,
        probe_url: str = PROXY_PROBE_URL,
        timeout_sec: float = PROXY_CHECK_TIMEOUT_SEC,
    ) -> ProxyCheckResult:
        """异步检测代理连通性与延迟，超时强制 8 秒。"""
        try:
            proxy_url = _build_proxy_url(proxy)
        except Exception as exc:
            logger.error("代理 [id=%s] 密钥解析失败: %s", proxy.id, type(exc).__name__)
            return ProxyCheckResult(
                alive=False,
                status="dead",
                latency_ms=None,
                error="代理凭证解密失败",
            )

        start_ts = time.perf_counter()
        try:
            connector = ProxyConnector.from_url(proxy_url, rdns=True)
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                async with session.get(probe_url, allow_redirects=False) as resp:
                    # 只要能通过代理收到远端 HTTP 响应，即代表代理链路畅通
                    _ = resp.status
            latency_ms = int((time.perf_counter() - start_ts) * 1000)
            status = (
                "slow" if latency_ms > SLOW_LATENCY_THRESHOLD_MS else "active"
            )
            return ProxyCheckResult(
                alive=True,
                status=status,
                latency_ms=latency_ms,
                error=None,
            )
        except asyncio.TimeoutError:
            logger.warning("代理 [id=%s, %s:%s] 探活超时", proxy.id, proxy.host, proxy.port)
            return ProxyCheckResult(
                alive=False,
                status="dead",
                latency_ms=None,
                error=f"连接超时（>{int(timeout_sec)}s）",
            )
        except Exception as exc:
            logger.warning(
                "代理 [id=%s, %s:%s] 探活失败: %s",
                proxy.id,
                proxy.host,
                proxy.port,
                type(exc).__name__,
            )
            return ProxyCheckResult(
                alive=False,
                status="dead",
                latency_ms=None,
                error=f"代理不可达: {type(exc).__name__}",
            )

    @classmethod
    async def verify_proxy_alive(
        cls,
        db: AsyncSession,
        proxy: Proxy,
        commit: bool = True,
    ) -> ProxyCheckResult:
        """执行探活并将最新状态、延迟与检测时间写回数据库。"""
        result = await cls.check_proxy(proxy)
        proxy.status = result.status
        proxy.latency_ms = result.latency_ms
        proxy.last_checked_at = datetime.now(timezone.utc)
        if commit:
            await db.commit()
            await db.refresh(proxy)
        return result

