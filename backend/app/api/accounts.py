from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.engine.converter import (
    import_from_session,
    import_from_tdata,
    send_phone_login_code,
    verify_phone_login_code,
)
from app.engine.proxy_checker import ProxyChecker
from app.models.account import Account
from app.models.proxy import Proxy
from app.schemas.account import (
    AccountOut,
    AccountUpdate,
    BatchHealthCheckRequest,
    HealthCheckResultOut,
    PhoneSendCodeRequest,
    PhoneSendCodeResponse,
    PhoneVerifyRequest,
    PhoneVerifyResponse,
)
from app.workers.health_check import run_spambot_health_check

router = APIRouter(prefix="/api/accounts", tags=["账号管理与导入"])

BACKEND_DIR = Path(__file__).resolve().parents[2]


async def _load_account_with_profile(db: AsyncSession, account_id: int) -> Account:
    """查询单个账号并预加载设备指纹。"""
    stmt = (
        select(Account)
        .options(selectinload(Account.device_profile))
        .where(Account.id == account_id)
    )
    account = (await db.execute(stmt)).scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在"
        )
    return account


@router.get("", response_model=list[AccountOut], summary="获取账号列表")
async def list_accounts(
    status_filter: str | None = Query(default=None, alias="status"),
    account_role: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[Account]:
    """按状态、角色或关键字筛选账号列表。"""
    stmt = (
        select(Account)
        .options(selectinload(Account.device_profile))
        .order_by(Account.id.desc())
    )
    if status_filter:
        stmt = stmt.where(Account.status == status_filter)
    if account_role:
        stmt = stmt.where(Account.account_role == account_role)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Account.phone.ilike(pattern),
                Account.username.ilike(pattern),
                Account.first_name.ilike(pattern),
            )
        )
    return list((await db.execute(stmt)).scalars().all())


@router.patch("/{account_id}", response_model=AccountOut, summary="更新账号配置")
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: AsyncSession = Depends(get_db),
) -> Account:
    """修改账号冻结状态、角色、每日限额、作息时区或绑定代理。"""
    account = await _load_account_with_profile(db, account_id)

    if payload.proxy_id is not None and payload.proxy_id != account.proxy_id:
        new_proxy = await db.get(Proxy, payload.proxy_id)
        if not new_proxy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="目标代理不存在"
            )
        bound_count = (
            await db.execute(
                select(func.count(Account.id)).where(
                    Account.proxy_id == new_proxy.id,
                    Account.status != "banned",
                )
            )
        ).scalar_one()
        if bound_count >= new_proxy.max_accounts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标代理已达到最大账号绑定上限",
            )
        probe = await ProxyChecker.verify_proxy_alive(db, new_proxy, commit=True)
        if not probe.alive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"目标代理探活失败: {probe.error}",
            )
        account.proxy_id = new_proxy.id

    if payload.status is not None:
        if account.status in ("invalid", "banned"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"状态为 {account.status} 的账号不可直接启用/冻结",
            )
        account.status = payload.status
    if payload.account_role is not None:
        account.account_role = payload.account_role
    if payload.daily_action_limit is not None:
        account.daily_action_limit = payload.daily_action_limit
    if payload.timezone is not None:
        account.timezone = payload.timezone
    if payload.quiet_hours_enabled is not None:
        account.quiet_hours_enabled = payload.quiet_hours_enabled

    await db.commit()
    return await _load_account_with_profile(db, account.id)


@router.delete(
    "/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除账号"
)
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """删除账号记录、关联设备指纹与本地 .session 文件。"""
    account = await _load_account_with_profile(db, account_id)
    device_profile = account.device_profile
    session_path = BACKEND_DIR / account.session_file_path

    await db.delete(account)
    await db.flush()
    if device_profile is not None:
        await db.delete(device_profile)
    await db.commit()

    if session_path.exists():
        session_path.unlink(missing_ok=True)


@router.post(
    "/import/tdata",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
    summary="方式 1：tdata 压缩包导入",
)
async def api_import_tdata(
    file: UploadFile = File(...),
    proxy_id: int = Form(...),
    two_fa: str | None = Form(default=None),
    country_code: str | None = Form(default=None),
    account_role: str = Form(default="worker"),
    db: AsyncSession = Depends(get_db),
) -> Account:
    """上传包含 tdata 的 .zip 压缩包并转换固化为 Telethon Session。"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 .zip 格式的 tdata 压缩包"
        )
    zip_bytes = await file.read()
    account = await import_from_tdata(
        db,
        zip_bytes=zip_bytes,
        proxy_id=proxy_id,
        two_fa=two_fa,
        country_code=country_code,
        account_role=account_role,
    )
    return await _load_account_with_profile(db, account.id)


@router.post(
    "/import/session",
    response_model=AccountOut,
    status_code=status.HTTP_201_CREATED,
    summary="方式 2：已有 .session 文件导入",
)
async def api_import_session(
    session_file: UploadFile = File(...),
    json_file: UploadFile | None = File(default=None),
    proxy_id: int = Form(...),
    two_fa: str | None = Form(default=None),
    country_code: str | None = Form(default=None),
    account_role: str = Form(default="worker"),
    db: AsyncSession = Depends(get_db),
) -> Account:
    """上传 .session 文件（可选附带设备 .json）导入账号。"""
    if not session_file.filename or not session_file.filename.lower().endswith(".session"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请上传有效的 .session 文件"
        )
    session_bytes = await session_file.read()
    json_bytes = await json_file.read() if json_file is not None else None
    account = await import_from_session(
        db,
        session_bytes=session_bytes,
        json_bytes=json_bytes,
        proxy_id=proxy_id,
        two_fa=two_fa,
        country_code=country_code,
        account_role=account_role,
    )
    return await _load_account_with_profile(db, account.id)


@router.post(
    "/import/phone/send-code",
    response_model=PhoneSendCodeResponse,
    summary="方式 3 第一步：发送登录验证码",
)
async def api_phone_send_code(
    payload: PhoneSendCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> PhoneSendCodeResponse:
    """探活代理并向目标手机号发送 Telegram 登录验证码。"""
    result = await send_phone_login_code(
        db,
        phone=payload.phone,
        proxy_id=payload.proxy_id,
        platform=payload.platform,
        country_code=payload.country_code,
        account_role=payload.account_role,
    )
    return PhoneSendCodeResponse(**result)


@router.post(
    "/import/phone/verify",
    response_model=PhoneVerifyResponse,
    summary="方式 3 第二步：提交验证码与 2FA 登录",
)
async def api_phone_verify(
    payload: PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> PhoneVerifyResponse:
    """提交验证码（及可选 2FA 密码）完成账号登录与入库。"""
    result = await verify_phone_login_code(
        db,
        login_token=payload.login_token,
        code=payload.code,
        two_fa=payload.two_fa,
    )
    account_out = None
    if result["account"] is not None:
        loaded = await _load_account_with_profile(db, result["account"].id)
        account_out = AccountOut.model_validate(loaded)
    return PhoneVerifyResponse(
        need_2fa=result["need_2fa"],
        login_token=result["login_token"],
        account=account_out,
    )


@router.post(
    "/{account_id}/health-check",
    response_model=HealthCheckResultOut,
    summary="单账号 @SpamBot 体检",
)
async def api_health_check_account(
    account_id: int, db: AsyncSession = Depends(get_db)
) -> HealthCheckResultOut:
    """触发单个账号向 @SpamBot 发送 /start 并更新体检状态。"""
    account = await run_spambot_health_check(db, account_id)
    return HealthCheckResultOut(
        account_id=account.id,
        status=account.status,
        spambot_status=account.spambot_status or "",
        checked_at=account.last_health_check_at or datetime.now(timezone.utc),
    )


@router.post(
    "/batch-health-check",
    response_model=list[HealthCheckResultOut],
    summary="批量 @SpamBot 体检",
)
async def api_batch_health_check(
    payload: BatchHealthCheckRequest, db: AsyncSession = Depends(get_db)
) -> list[HealthCheckResultOut]:
    """依次对指定账号列表执行 @SpamBot 体检（单账号失败不中断其余账号）。"""
    results: list[HealthCheckResultOut] = []
    for account_id in payload.account_ids:
        try:
            account = await run_spambot_health_check(db, account_id)
            results.append(
                HealthCheckResultOut(
                    account_id=account.id,
                    status=account.status,
                    spambot_status=account.spambot_status or "",
                    checked_at=account.last_health_check_at or datetime.now(timezone.utc),
                )
            )
        except HTTPException as exc:
            results.append(
                HealthCheckResultOut(
                    account_id=account_id,
                    status="error",
                    spambot_status=str(exc.detail),
                    checked_at=datetime.now(timezone.utc),
                )
            )
    return results

