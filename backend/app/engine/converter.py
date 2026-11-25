import asyncio
import json
import logging
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from opentele2.api import API, UseCurrentSession
from opentele2.td import TDesktop
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.core.security import encrypt_secret
from app.engine.proxy_checker import ProxyChecker, build_telethon_proxy
from app.models.account import Account
from app.models.device_profile import DeviceProfile
from app.models.proxy import Proxy

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SESSIONS_DIR = BACKEND_DIR / "storage" / "sessions"
TEMP_DIR = BACKEND_DIR / "storage" / "temp"

PENDING_LOGIN_TTL_SEC = 300.0


@dataclass
class PendingLogin:
    """手机号网页端登录的暂存会话状态。"""

    login_token: str
    account_uuid: uuid.UUID
    phone: str
    phone_code_hash: str
    proxy_id: int
    platform: str
    country_code: str | None
    account_role: str
    session_path: Path
    api_profile: dict[str, Any]
    client: TelegramClient
    created_at: float


# 内存中暂存手机号登录态，超过 5 分钟自动清理
_pending_logins: dict[str, PendingLogin] = {}


def _ensure_storage_dirs() -> None:
    """确保存储目录存在。"""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _generate_opentele_api(platform: str, unique_seed: str) -> Any:
    """根据平台类型使用 opentele2 生成固定设备指纹对象。"""
    normalized = platform.lower()
    if normalized == "android":
        return API.TelegramAndroid.Generate(unique_id=unique_seed)
    if normalized == "ios":
        return API.TelegramIOS.Generate(unique_id=unique_seed)
    return API.TelegramDesktop.Generate(unique_id=unique_seed)


def _extract_profile_dict(api_obj: Any, platform: str, unique_seed: str) -> dict[str, Any]:
    """从 opentele2 API 对象提取可入库的设备指纹字段。"""
    return {
        "platform": platform.lower(),
        "api_id": int(api_obj.api_id),
        "api_hash": str(api_obj.api_hash),
        "device_model": str(api_obj.device_model),
        "system_version": str(api_obj.system_version),
        "app_version": str(api_obj.app_version),
        "lang_code": str(getattr(api_obj, "lang_code", "en") or "en"),
        "system_lang_code": str(getattr(api_obj, "system_lang_code", "en-US") or "en-US"),
        "unique_seed": unique_seed,
    }


async def _validate_and_probe_proxy(db: AsyncSession, proxy_id: int) -> Proxy:
    """校验代理存在性、绑定容量并强制探活（绝对禁止直连回退）。"""
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定的代理不存在",
        )

    bound_count = (
        await db.execute(
            select(func.count(Account.id)).where(
                Account.proxy_id == proxy_id,
                Account.status != "banned",
            )
        )
    ).scalar_one()

    if bound_count >= proxy.max_accounts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"代理 [{proxy.name}] 已达到最大账号绑定上限 ({bound_count}/{proxy.max_accounts})",
        )

    probe_result = await ProxyChecker.verify_proxy_alive(db, proxy, commit=True)
    if not probe_result.alive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"代理探活失败，已拒绝导入（严禁直连）: {probe_result.error or '不可达'}",
        )
    return proxy


async def _ensure_account_not_duplicate(
    db: AsyncSession, phone: str, tg_user_id: int | None
) -> None:
    """校验手机号和 Telegram 用户 ID 是否重复入库。"""
    existing_phone = (
        await db.execute(select(Account.id).where(Account.phone == phone))
    ).scalar_one_or_none()
    if existing_phone is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"手机号 {phone} 已存在于账号库中",
        )

    if tg_user_id is not None:
        existing_uid = (
            await db.execute(select(Account.id).where(Account.tg_user_id == tg_user_id))
        ).scalar_one_or_none()
        if existing_uid is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Telegram 用户 ID ({tg_user_id}) 已存在于账号库中",
            )


async def _save_account_with_profile(
    db: AsyncSession,
    *,
    account_uuid: uuid.UUID,
    phone: str,
    tg_user_id: int | None,
    username: str | None,
    first_name: str | None,
    import_source: str,
    session_path: Path,
    two_fa: str | None,
    country_code: str | None,
    account_role: str,
    proxy_id: int,
    profile_data: dict[str, Any],
) -> Account:
    """将固化设备指纹与账号记录原子写入 PostgreSQL。"""
    await _ensure_account_not_duplicate(db, phone, tg_user_id)

    device_profile = DeviceProfile(**profile_data)
    db.add(device_profile)
    await db.flush()

    two_fa_encrypted = encrypt_secret(two_fa) if two_fa else None
    rel_session_path = str(session_path.relative_to(BACKEND_DIR)).replace("\\", "/")

    account = Account(
        account_uuid=account_uuid,
        phone=phone,
        country_code=country_code.upper() if country_code else None,
        tg_user_id=tg_user_id,
        username=username,
        first_name=first_name,
        import_source=import_source,
        session_file_path=rel_session_path,
        two_fa_encrypted=two_fa_encrypted,
        account_role=account_role,
        device_profile_id=device_profile.id,
        proxy_id=proxy_id,
        status="active",
        health_score=100,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


def _safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    """安全解压 ZIP 文件，防止路径穿越（ZipSlip）攻击。"""
    base_resolved = extract_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target_path = (extract_dir / member.filename).resolve()
            if not str(target_path).startswith(str(base_resolved)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="压缩包包含非法路径，已拒绝解压",
                )
        zf.extractall(extract_dir)


def _locate_tdata_dir(extract_dir: Path) -> Path:
    """在解压目录中定位 tdata 文件夹路径。"""
    direct_tdata = extract_dir / "tdata"
    if direct_tdata.is_dir():
        return direct_tdata

    for candidate in extract_dir.rglob("tdata"):
        if candidate.is_dir():
            return candidate

    # 兼容直接把 key_datas 等 tdata 内部文件放在压缩包根目录的情况
    if (extract_dir / "key_datas").exists():
        return extract_dir

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="ZIP 压缩包中未找到有效的 tdata 目录",
    )


async def import_from_tdata(
    db: AsyncSession,
    *,
    zip_bytes: bytes,
    proxy_id: int,
    two_fa: str | None = None,
    country_code: str | None = None,
    account_role: str = "worker",
) -> Account:
    """方式 1：通过 tdata 压缩包导入账号并固化桌面端指纹。"""
    _ensure_storage_dirs()
    proxy = await _validate_and_probe_proxy(db, proxy_id)
    proxy_tuple = build_telethon_proxy(proxy)

    temp_uuid = uuid.uuid4().hex
    temp_work_dir = TEMP_DIR / f"tdata_{temp_uuid}"
    temp_zip_path = temp_work_dir / "upload.zip"

    account_uuid = uuid.uuid4()
    session_path = SESSIONS_DIR / f"{account_uuid}.session"
    client: TelegramClient | None = None
    saved = False

    try:
        temp_work_dir.mkdir(parents=True, exist_ok=True)
        temp_zip_path.write_bytes(zip_bytes)
        extract_dir = temp_work_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        _safe_extract_zip(temp_zip_path, extract_dir)

        tdata_dir = _locate_tdata_dir(extract_dir)
        api_obj = _generate_opentele_api("desktop", str(account_uuid))
        profile_data = _extract_profile_dict(api_obj, "desktop", str(account_uuid))

        tdesk = TDesktop(basePath=str(tdata_dir))
        if not tdesk.isLoaded():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法解析 tdata 数据，请确认压缩包完整且未设置本地密码",
            )

        client = await tdesk.ToTelethon(
            session=str(session_path),
            flag=UseCurrentSession,
            api=api_obj,
            proxy=proxy_tuple,
            flood_sleep_threshold=0,
        )
        await client.connect()
        if not await client.is_user_authorized():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tdata 转换后的 Session 未授权或已失效",
            )

        me = await client.get_me()
        phone = f"+{me.phone}" if me.phone and not str(me.phone).startswith("+") else (me.phone or f"tg_{me.id}")

        account = await _save_account_with_profile(
            db,
            account_uuid=account_uuid,
            phone=phone,
            tg_user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            import_source="tdata",
            session_path=session_path,
            two_fa=two_fa,
            country_code=country_code,
            account_role=account_role,
            proxy_id=proxy.id,
            profile_data=profile_data,
        )
        saved = True
        return account
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("tdata 导入失败: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"tdata 导入失败: {type(exc).__name__}",
        ) from exc
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        if not saved and session_path.exists():
            session_path.unlink(missing_ok=True)
        shutil.rmtree(temp_work_dir, ignore_errors=True)


def _parse_session_json(json_bytes: bytes | None, unique_seed: str) -> dict[str, Any]:
    """解析号商附带的设备 JSON，缺失字段时使用 opentele2 默认指纹补全。"""
    fallback_api = _generate_opentele_api("desktop", unique_seed)
    profile = _extract_profile_dict(fallback_api, "desktop", unique_seed)
    if not json_bytes:
        return profile

    try:
        raw = json.loads(json_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="附带的 JSON 设备文件格式无效",
        ) from exc

    if not isinstance(raw, dict):
        return profile

    if raw.get("app_id") or raw.get("api_id"):
        profile["api_id"] = int(raw.get("app_id") or raw.get("api_id"))
    if raw.get("app_hash") or raw.get("api_hash"):
        profile["api_hash"] = str(raw.get("app_hash") or raw.get("api_hash"))
    if raw.get("device") or raw.get("device_model"):
        profile["device_model"] = str(raw.get("device") or raw.get("device_model"))
    if raw.get("sdk") or raw.get("system_version"):
        profile["system_version"] = str(raw.get("sdk") or raw.get("system_version"))
    if raw.get("app_version"):
        profile["app_version"] = str(raw["app_version"])
    if raw.get("lang_code"):
        profile["lang_code"] = str(raw["lang_code"])
    if raw.get("system_lang_code") or raw.get("system_lang_pack"):
        profile["system_lang_code"] = str(
            raw.get("system_lang_code") or raw.get("system_lang_pack")
        )
    return profile


async def import_from_session(
    db: AsyncSession,
    *,
    session_bytes: bytes,
    json_bytes: bytes | None,
    proxy_id: int,
    two_fa: str | None = None,
    country_code: str | None = None,
    account_role: str = "worker",
) -> Account:
    """方式 2：通过已有 .session 文件（可选附带 .json）导入账号。"""
    _ensure_storage_dirs()
    proxy = await _validate_and_probe_proxy(db, proxy_id)
    proxy_tuple = build_telethon_proxy(proxy)

    account_uuid = uuid.uuid4()
    session_path = SESSIONS_DIR / f"{account_uuid}.session"
    profile_data = _parse_session_json(json_bytes, str(account_uuid))

    client: TelegramClient | None = None
    saved = False

    try:
        session_path.write_bytes(session_bytes)
        client = TelegramClient(
            str(session_path),
            profile_data["api_id"],
            profile_data["api_hash"],
            proxy=proxy_tuple,
            device_model=profile_data["device_model"],
            system_version=profile_data["system_version"],
            app_version=profile_data["app_version"],
            lang_code=profile_data["lang_code"],
            system_lang_code=profile_data["system_lang_code"],
            flood_sleep_threshold=0,
        )
        await client.connect()
        if not await client.is_user_authorized():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session 已失效或未授权，无法完成导入",
            )

        me = await client.get_me()
        phone = f"+{me.phone}" if me.phone and not str(me.phone).startswith("+") else (me.phone or f"tg_{me.id}")

        account = await _save_account_with_profile(
            db,
            account_uuid=account_uuid,
            phone=phone,
            tg_user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            import_source="session",
            session_path=session_path,
            two_fa=two_fa,
            country_code=country_code,
            account_role=account_role,
            proxy_id=proxy.id,
            profile_data=profile_data,
        )
        saved = True
        return account
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("session 导入失败: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"session 导入失败: {type(exc).__name__}",
        ) from exc
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        if not saved and session_path.exists():
            session_path.unlink(missing_ok=True)


async def cleanup_expired_pending_logins() -> None:
    """清理超过 5 分钟未完成的手机号登录暂存状态与临时会话文件。"""
    now_ts = time.monotonic()
    expired_tokens = [
        token
        for token, pending in _pending_logins.items()
        if now_ts - pending.created_at > PENDING_LOGIN_TTL_SEC
    ]
    for token in expired_tokens:
        pending = _pending_logins.pop(token, None)
        if pending is None:
            continue
        try:
            await pending.client.disconnect()
        except Exception:
            pass
        pending.session_path.unlink(missing_ok=True)


async def send_phone_login_code(
    db: AsyncSession,
    *,
    phone: str,
    proxy_id: int,
    platform: str = "android",
    country_code: str | None = None,
    account_role: str = "worker",
) -> dict[str, str]:
    """方式 3 第一步：探活代理、生成固化指纹并发送登录验证码。"""
    _ensure_storage_dirs()
    await cleanup_expired_pending_logins()
    await _ensure_account_not_duplicate(db, phone, None)

    proxy = await _validate_and_probe_proxy(db, proxy_id)
    proxy_tuple = build_telethon_proxy(proxy)

    account_uuid = uuid.uuid4()
    session_path = SESSIONS_DIR / f"{account_uuid}.session"
    api_obj = _generate_opentele_api(platform, str(account_uuid))
    profile_data = _extract_profile_dict(api_obj, platform, str(account_uuid))

    client = TelegramClient(
        str(session_path),
        profile_data["api_id"],
        profile_data["api_hash"],
        proxy=proxy_tuple,
        device_model=profile_data["device_model"],
        system_version=profile_data["system_version"],
        app_version=profile_data["app_version"],
        lang_code=profile_data["lang_code"],
        system_lang_code=profile_data["system_lang_code"],
        flood_sleep_threshold=0,
    )

    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        login_token = uuid.uuid4().hex
        _pending_logins[login_token] = PendingLogin(
            login_token=login_token,
            account_uuid=account_uuid,
            phone=phone,
            phone_code_hash=sent.phone_code_hash,
            proxy_id=proxy.id,
            platform=platform,
            country_code=country_code,
            account_role=account_role,
            session_path=session_path,
            api_profile=profile_data,
            client=client,
            created_at=time.monotonic(),
        )
        return {
            "login_token": login_token,
            "phone_code_hash": sent.phone_code_hash,
        }
    except HTTPException:
        await client.disconnect()
        session_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        try:
            await client.disconnect()
        except Exception:
            pass
        session_path.unlink(missing_ok=True)
        logger.exception("发送验证码失败: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"发送验证码失败: {type(exc).__name__}",
        ) from exc


async def verify_phone_login_code(
    db: AsyncSession,
    *,
    login_token: str,
    code: str,
    two_fa: str | None = None,
) -> dict[str, Any]:
    """方式 3 第二步：提交验证码及可选 2FA 完成登录并固化入库。"""
    await cleanup_expired_pending_logins()
    pending = _pending_logins.get(login_token)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登录会话不存在或已超过 5 分钟有效期，请重新获取验证码",
        )

    client = pending.client
    try:
        try:
            await client.sign_in(
                phone=pending.phone,
                code=code,
                phone_code_hash=pending.phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not two_fa:
                return {
                    "need_2fa": True,
                    "login_token": login_token,
                    "account": None,
                }
            await client.sign_in(password=two_fa)

        me = await client.get_me()
        phone = f"+{me.phone}" if me.phone and not str(me.phone).startswith("+") else (me.phone or pending.phone)

        account = await _save_account_with_profile(
            db,
            account_uuid=pending.account_uuid,
            phone=phone,
            tg_user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            import_source="phone_login",
            session_path=pending.session_path,
            two_fa=two_fa,
            country_code=pending.country_code,
            account_role=pending.account_role,
            proxy_id=pending.proxy_id,
            profile_data=pending.api_profile,
        )

        _pending_logins.pop(login_token, None)
        await client.disconnect()
        return {
            "need_2fa": False,
            "login_token": login_token,
            "account": account,
        }
    except HTTPException:
        raise
    except Exception as exc:
        _pending_logins.pop(login_token, None)
        try:
            await client.disconnect()
        except Exception:
            pass
        pending.session_path.unlink(missing_ok=True)
        logger.exception("验证码登录失败: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"验证码或 2FA 登录失败: {type(exc).__name__}",
        ) from exc

