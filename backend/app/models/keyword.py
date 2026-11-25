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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KeywordRule(Base):
    """关键词实时监控规则表，对应数据表 keyword_rules。"""

    __tablename__ = "keyword_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    listener_account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    monitored_chat_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    keywords: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    match_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'contains'")
    )
    exclude_keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    alert_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_target_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KeywordAlert(Base):
    """关键词命中告警记录表，对应数据表 keyword_alerts。"""

    __tablename__ = "keyword_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("keyword_rules.id", ondelete="CASCADE"), nullable=False
    )
    matched_keyword: Mapped[str] = mapped_column(String(128), nullable=False)
    source_chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_chat_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sender_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

