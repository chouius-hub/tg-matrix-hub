from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DeviceProfile(Base):
    """设备指纹固化模型，对应数据表 device_profiles。"""

    __tablename__ = "device_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    api_id: Mapped[int] = mapped_column(Integer, nullable=False)
    api_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    device_model: Mapped[str] = mapped_column(String(128), nullable=False)
    system_version: Mapped[str] = mapped_column(String(64), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)
    lang_code: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'en'")
    )
    system_lang_code: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'en-US'")
    )
    unique_seed: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    account: Mapped["Account | None"] = relationship(
        "Account", back_populates="device_profile", uselist=False
    )

