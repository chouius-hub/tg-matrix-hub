from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegexReplacementItem(BaseModel):
    """正则替换规则条目。"""

    pattern: str = Field(..., min_length=1)
    replace: str = ""


class ChannelSyncRuleCreate(BaseModel):
    """创建频道转发规则请求模型。"""

    name: str = Field(..., min_length=1, max_length=128)
    listener_account_id: int
    publisher_account_id: int
    source_chat_id: str = Field(..., min_length=1, max_length=128)
    target_chat_id: str = Field(..., min_length=1, max_length=128)
    enable_ai_translate: bool = True
    ai_system_prompt: str = (
        "将以下内容翻译为流畅、口语化的中文，保留核心信息与排版，去除原频道广告和推广链接。"
    )
    regex_replacements: list[RegexReplacementItem] = Field(default_factory=list)
    blocked_keywords: list[str] = Field(default_factory=list)
    append_footer: str | None = None
    min_delay_sec: int = Field(default=15, ge=0, le=3600)
    max_delay_sec: int = Field(default=60, ge=0, le=3600)
    is_enabled: bool = True


class ChannelSyncRuleUpdate(BaseModel):
    """更新频道转发规则请求模型。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    listener_account_id: int | None = None
    publisher_account_id: int | None = None
    source_chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    enable_ai_translate: bool | None = None
    ai_system_prompt: str | None = None
    regex_replacements: list[RegexReplacementItem] | None = None
    blocked_keywords: list[str] | None = None
    append_footer: str | None = None
    min_delay_sec: int | None = Field(default=None, ge=0, le=3600)
    max_delay_sec: int | None = Field(default=None, ge=0, le=3600)
    is_enabled: bool | None = None


class ChannelSyncRuleOut(BaseModel):
    """频道转发规则响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    listener_account_id: int
    publisher_account_id: int
    source_chat_id: str
    target_chat_id: str
    enable_ai_translate: bool
    ai_system_prompt: str
    regex_replacements: list[RegexReplacementItem]
    blocked_keywords: list[str]
    append_footer: str | None
    min_delay_sec: int
    max_delay_sec: int
    is_enabled: bool
    created_at: datetime

