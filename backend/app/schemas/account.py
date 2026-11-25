import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceProfileOut(BaseModel):
    """固化设备指纹响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    api_id: int
    device_model: str
    system_version: str
    app_version: str
    lang_code: str
    system_lang_code: str
    unique_seed: str


class AccountOut(BaseModel):
    """账号响应模型（绝不返回 2FA 密码明文或密文）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_uuid: uuid.UUID
    phone: str
    country_code: str | None
    tg_user_id: int | None
    username: str | None
    first_name: str | None
    import_source: str
    account_role: str
    proxy_id: int
    device_profile_id: int
    status: str
    health_score: int
    cooldown_until: datetime | None
    spambot_status: str | None
    last_health_check_at: datetime | None
    timezone: str
    quiet_hours_enabled: bool
    daily_action_count: int
    daily_action_limit: int
    last_active_at: datetime | None
    created_at: datetime
    updated_at: datetime
    device_profile: DeviceProfileOut | None = None


class AccountUpdate(BaseModel):
    """账号配置更新请求模型（冻结/解冻、限额、作息时区、角色、更换代理）。"""

    status: Literal["active", "frozen"] | None = None
    account_role: Literal["listener", "worker", "publisher"] | None = None
    daily_action_limit: int | None = Field(default=None, ge=1, le=500)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    quiet_hours_enabled: bool | None = None
    proxy_id: int | None = None


class PhoneSendCodeRequest(BaseModel):
    """手机号登录：发送验证码请求模型。"""

    phone: str = Field(..., min_length=5, max_length=32)
    proxy_id: int
    platform: Literal["android", "ios", "desktop"] = "android"
    country_code: str | None = Field(default=None, max_length=8)
    account_role: Literal["listener", "worker", "publisher"] = "worker"


class PhoneSendCodeResponse(BaseModel):
    """手机号登录：发送验证码响应模型。"""

    login_token: str
    phone_code_hash: str


class PhoneVerifyRequest(BaseModel):
    """手机号登录：提交验证码与可选 2FA 请求模型。"""

    login_token: str = Field(..., min_length=1)
    code: str = Field(..., min_length=3, max_length=16)
    two_fa: str | None = None


class PhoneVerifyResponse(BaseModel):
    """手机号登录：校验结果响应模型。"""

    need_2fa: bool = False
    login_token: str
    account: AccountOut | None = None


class BatchHealthCheckRequest(BaseModel):
    """批量 @SpamBot 体检请求模型。"""

    account_ids: list[int] = Field(..., min_length=1, max_length=100)


class HealthCheckResultOut(BaseModel):
    """单个账号 @SpamBot 体检结果响应模型。"""

    account_id: int
    status: str
    spambot_status: str
    checked_at: datetime

