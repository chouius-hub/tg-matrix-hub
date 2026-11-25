import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket 实时事件与风控告警广播管理器。"""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def active_connection_count(self) -> int:
        """返回当前活跃的 WebSocket 客户端数量。"""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """接受并注册新的 WebSocket 连接。"""
        await websocket.accept()
        self._connections.add(websocket)
        logger.debug("WebSocket 客户端已连接，当前连接数: %d", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """注销断开的 WebSocket 连接。"""
        self._connections.discard(websocket)
        logger.debug("WebSocket 客户端已断开，当前连接数: %d", len(self._connections))

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """向所有在线前端客户端广播 JSON 事件，自动清理失效连接。"""
        if not self._connections:
            return

        payload = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        dead_sockets: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception:
                dead_sockets.append(ws)

        for ws in dead_sockets:
            self._connections.discard(ws)


ws_manager = WebSocketManager()

