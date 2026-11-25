from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_secret
from app.engine.proxy_checker import ProxyChecker
from app.models.account import Account
from app.models.proxy import Proxy
from app.schemas.proxy import ProxyCheckOut, ProxyCreate, ProxyOut

router = APIRouter(prefix="/api/proxies", tags=["代理池管理"])


def _to_proxy_out(proxy: Proxy, bound_count: int) -> ProxyOut:
    """将 Proxy ORM 对象转换为脱敏的响应模型。"""
    return ProxyOut(
        id=proxy.id,
        name=proxy.name,
        protocol=proxy.protocol,
        host=proxy.host,
        port=proxy.port,
        username=proxy.username,
        has_password=bool(proxy.password_encrypted),
        country_code=proxy.country_code,
        max_accounts=proxy.max_accounts,
        status=proxy.status,
        latency_ms=proxy.latency_ms,
        last_checked_at=proxy.last_checked_at,
        created_at=proxy.created_at,
        bound_account_count=bound_count,
    )


@router.get("", response_model=list[ProxyOut], summary="获取代理列表")
async def list_proxies(db: AsyncSession = Depends(get_db)) -> list[ProxyOut]:
    """查询全部代理及各自绑定的有效账号数量（banned 账号不计入配额）。"""
    count_stmt = (
        select(Account.proxy_id, func.count(Account.id))
        .where(Account.status != "banned")
        .group_by(Account.proxy_id)
    )
    count_rows = (await db.execute(count_stmt)).all()
    bound_map: dict[int, int] = {row[0]: row[1] for row in count_rows}

    proxies = (await db.execute(select(Proxy).order_by(Proxy.id.desc()))).scalars().all()
    return [_to_proxy_out(proxy, bound_map.get(proxy.id, 0)) for proxy in proxies]


@router.post(
    "",
    response_model=ProxyOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增代理",
)
async def create_proxy(
    payload: ProxyCreate,
    db: AsyncSession = Depends(get_db),
) -> ProxyOut:
    """创建新代理，密码使用 FERNET_KEY 加密后入库。"""
    password_encrypted = (
        encrypt_secret(payload.password) if payload.password else None
    )
    proxy = Proxy(
        name=payload.name,
        protocol=payload.protocol,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password_encrypted=password_encrypted,
        country_code=payload.country_code.upper() if payload.country_code else None,
        max_accounts=payload.max_accounts,
        status="active",
    )
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return _to_proxy_out(proxy, 0)


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除代理")
async def delete_proxy(proxy_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """删除指定代理，若仍绑定有账号则拒绝删除。"""
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在"
        )

    bound_count = (
        await db.execute(
            select(func.count(Account.id)).where(Account.proxy_id == proxy_id)
        )
    ).scalar_one()
    if bound_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该代理仍绑定了 {bound_count} 个账号，请先迁移或删除关联账号",
        )

    await db.delete(proxy)
    await db.commit()


@router.post("/{proxy_id}/check", response_model=ProxyCheckOut, summary="手动测速探活")
async def check_proxy(
    proxy_id: int, db: AsyncSession = Depends(get_db)
) -> ProxyCheckOut:
    """对指定代理执行强制探活并更新状态与延迟。"""
    proxy = await db.get(Proxy, proxy_id)
    if not proxy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="代理不存在"
        )

    result = await ProxyChecker.verify_proxy_alive(db, proxy, commit=True)
    return ProxyCheckOut(
        proxy_id=proxy.id,
        alive=result.alive,
        status=result.status,
        latency_ms=result.latency_ms,
        error=result.error,
        last_checked_at=proxy.last_checked_at or datetime.now(timezone.utc),
    )

