from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScheduledPostCreate(BaseModel):
    """创建定时发帖排期请求模型。"""

    title: str = Field(..., min_length=1, max_length=128)
    publisher_account_id: int
    target_chat_ids: list[str] = Field(..., min_length=1)
    content_text: str = Field(..., min_length=1)
    parse_mode: Literal["html", "md"] = "html"
    media_file_path: str | None = None
    disable_web_page_preview: bool = False
    scheduled_at: datetime


class ScheduledPostUpdate(BaseModel):
    """更新定时发帖排期请求模型（仅 pending 状态允许修改）。"""

    title: str | None = Field(default=None, min_length=1, max_length=128)
    publisher_account_id: int | None = None
    target_chat_ids: list[str] | None = Field(default=None, min_length=1)
    content_text: str | None = Field(default=None, min_length=1)
    parse_mode: Literal["html", "md"] | None = None
    media_file_path: str | None = None
    disable_web_page_preview: bool | None = None
    scheduled_at: datetime | None = None
    status: Literal["pending", "cancelled"] | None = None


class ScheduledPostOut(BaseModel):
    """定时发帖排期响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    publisher_account_id: int
    target_chat_ids: list[str]
    content_text: str
    parse_mode: str
    media_file_path: str | None
    disable_web_page_preview: bool
    scheduled_at: datetime
    status: str
    error_message: str | None
    sent_at: datetime | None
    created_at: datetime


class MediaUploadOut(BaseModel):
    """媒体上传响应模型。"""

    file_path: str
    filename: str
    size_bytes: int

