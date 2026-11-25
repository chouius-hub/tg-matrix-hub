import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    """Telegram 账号生命周期与健康状态主表，对应数据表 accounts。"""

    __tablename__ = "accounts"
    __table_args__ = (
        Index("idx_accounts_schedulable", "status", "cooldown_until", "account_role"),
        Index("idx_accounts_proxy_id", "proxy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_uuid: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), unique=True, nullable=False
    )
    phone: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    tg_user_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    import_source: Mapped[str] = mapped_column(String(24), nullable=False)
    session_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    two_fa_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_role: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'worker'")
    )

    device_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("device_profiles.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    proxy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proxies.id", ondelete="RESTRICT"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'active'")
    )
    health_score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("100")
    )
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    spambot_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'America/New_York'")
    )
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    daily_action_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    daily_action_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30")
    )

    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    device_profile: Mapped["DeviceProfile"] = relationship(
        "DeviceProfile", back_populates="account"
    )
    proxy: Mapped["Proxy"] = relationship("Proxy", back_populates="accounts")

