from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KeywordRuleCreate(BaseModel):
    """创建关键词监控规则请求模型。"""

    name: str = Field(..., min_length=1, max_length=128)
    listener_account_id: int
    monitored_chat_ids: list[str] = Field(..., min_length=1)
    keywords: list[str] = Field(..., min_length=1)
    match_mode: Literal["contains", "regex"] = "contains"
    exclude_keywords: list[str] = Field(default_factory=list)
    alert_webhook_url: str | None = None
    alert_target_chat_id: str | None = None
    is_enabled: bool = True


class KeywordRuleUpdate(BaseModel):
    """更新关键词监控规则请求模型。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    listener_account_id: int | None = None
    monitored_chat_ids: list[str] | None = Field(default=None, min_length=1)
    keywords: list[str] | None = Field(default=None, min_length=1)
    match_mode: Literal["contains", "regex"] | None = None
    exclude_keywords: list[str] | None = None
    alert_webhook_url: str | None = None
    alert_target_chat_id: str | None = None
    is_enabled: bool | None = None


class KeywordRuleOut(BaseModel):
    """关键词监控规则响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    listener_account_id: int
    monitored_chat_ids: list[str]
    keywords: list[str]
    match_mode: str
    exclude_keywords: list[str]
    alert_webhook_url: str | None
    alert_target_chat_id: str | None
    is_enabled: bool
    created_at: datetime


class KeywordAlertOut(BaseModel):
    """关键词命中告警响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    matched_keyword: str
    source_chat_title: str | None
    source_chat_id: str
    sender_username: str | None
    message_text: str
    message_link: str | None
    is_read: bool
    created_at: datetime

