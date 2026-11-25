from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SystemStatsOut(BaseModel):
    """系统运行状态与账号分布统计响应模型。"""

    total_accounts: int
    status_counts: dict[str, int]
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    pool_pinned_count: int
    pool_lru_count: int
    pool_total_active: int
    ws_connections: int


class TaskLogOut(BaseModel):
    """风控与任务审计日志响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int | None
    account_id: int
    action: str
    result: str
    target_ref: str | None
    wait_seconds: int
    error_detail: str | None
    created_at: datetime

