from datetime import datetime

import psutil
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ws_manager import ws_manager
from app.engine.pool import client_pool
from app.models.account import Account
from app.models.task import TaskLog
from app.schemas.system import SystemStatsOut, TaskLogOut

router = APIRouter(tags=["系统监控与审计日志"])


@router.get("/api/system/stats", response_model=SystemStatsOut, summary="获取系统与账号大盘统计")
async def get_system_stats(db: AsyncSession = Depends(get_db)) -> SystemStatsOut:
    """统计各状态账号数量、本机 CPU/内存资源及连接池活跃数。"""
    rows = (
        await db.execute(
            select(Account.status, func.count(Account.id)).group_by(Account.status)
        )
    ).all()

    status_counts = {
        "pending": 0,
        "active": 0,
        "cooldown": 0,
        "restricted": 0,
        "frozen": 0,
        "invalid": 0,
        "banned": 0,
    }
    total_accounts = 0
    for acc_status, cnt in rows:
        status_counts[acc_status] = cnt
        total_accounts += cnt

    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    pool_stats = client_pool.get_stats()

    return SystemStatsOut(
        total_accounts=total_accounts,
        status_counts=status_counts,
        cpu_percent=round(cpu_percent, 1),
        memory_percent=round(mem.percent, 1),
        memory_used_mb=round(mem.used / (1024 * 1024), 1),
        memory_total_mb=round(mem.total / (1024 * 1024), 1),
        pool_pinned_count=pool_stats["pinned_count"],
        pool_lru_count=pool_stats["lru_count"],
        pool_total_active=pool_stats["total_active_clients"],
        ws_connections=ws_manager.active_connection_count,
    )


@router.get("/api/logs", response_model=list[TaskLogOut], summary="查询风控审计日志")
async def list_task_logs(
    account_id: int | None = Query(default=None),
    result: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[TaskLog]:
    """支持按账号、风控结果及时间范围筛选任务审计日志。"""
    stmt = select(TaskLog).order_by(TaskLog.created_at.desc(), TaskLog.id.desc())
    if account_id is not None:
        stmt = stmt.where(TaskLog.account_id == account_id)
    if result:
        stmt = stmt.where(TaskLog.result == result)
    if start_time is not None:
        stmt = stmt.where(TaskLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(TaskLog.created_at <= end_time)

    stmt = stmt.offset(offset).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """WebSocket 实时日志、账号状态与关键词告警推送通道。"""
    await ws_manager.connect(websocket)
    try:
        while True:
            # 维持连接并接收前端可选的心跳包
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

