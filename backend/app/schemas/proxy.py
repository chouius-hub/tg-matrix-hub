from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProxyCreate(BaseModel):
    """新增代理请求模型。"""

    name: str = Field(..., min_length=1, max_length=64)
    protocol: Literal["socks5", "http"] = "socks5"
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = None
    country_code: str | None = Field(default=None, max_length=8)
    max_accounts: int = Field(default=2, ge=1, le=20)


class ProxyOut(BaseModel):
    """代理响应模型（绝不返回密码明文或密文）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    protocol: str
    host: str
    port: int
    username: str | None
    has_password: bool = False
    country_code: str | None
    max_accounts: int
    status: str
    latency_ms: int | None
    last_checked_at: datetime | None
    created_at: datetime
    bound_account_count: int = 0


class ProxyCheckOut(BaseModel):
    """代理手动探活响应模型。"""

    proxy_id: int
    alive: bool
    status: str
    latency_ms: int | None
    error: str | None = None
    last_checked_at: datetime

