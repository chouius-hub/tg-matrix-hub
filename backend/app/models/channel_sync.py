from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChannelSyncRule(Base):
    """多频道采集与 AI 翻译转发规则表，对应数据表 channel_sync_rules。"""

    __tablename__ = "channel_sync_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    listener_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    publisher_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    source_chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    enable_ai_translate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    ai_system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text(
            "'将以下内容翻译为流畅、口语化的中文，保留核心信息与排版，去除原频道广告和推广链接。'"
        ),
    )
    regex_replacements: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    blocked_keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    append_footer: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_delay_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("15")
    )
    max_delay_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SyncMessageHistory(Base):
    """转发去重历史记录表，对应数据表 sync_message_history。"""

    __tablename__ = "sync_message_history"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "source_chat_id",
            "source_msg_id",
            name="uq_sync_message_history_rule_chat_msg",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channel_sync_rules.id", ondelete="CASCADE"), nullable=False
    )
    source_chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_msg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

