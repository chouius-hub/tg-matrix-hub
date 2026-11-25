from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.keyword import KeywordAlert, KeywordRule
from app.schemas.keyword import (
    KeywordAlertOut,
    KeywordRuleCreate,
    KeywordRuleOut,
    KeywordRuleUpdate,
)
from app.workers.keyword_monitor import keyword_monitor_manager

router = APIRouter(tags=["关键词实时监控与告警"])


@router.get("/api/keyword-rules", response_model=list[KeywordRuleOut], summary="获取关键词规则列表")
async def list_keyword_rules(
    db: AsyncSession = Depends(get_db),
) -> list[KeywordRule]:
    """查询全部关键词监控规则。"""
    return list(
        (await db.execute(select(KeywordRule).order_by(KeywordRule.id.desc())))
        .scalars()
        .all()
    )


@router.post(
    "/api/keyword-rules",
    response_model=KeywordRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建关键词监控规则",
)
async def create_keyword_rule(
    payload: KeywordRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> KeywordRule:
    """创建关键词监控规则并热加载至监听池。"""
    if await db.get(Account, payload.listener_account_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="监听账号不存在"
        )

    rule = KeywordRule(
        name=payload.name,
        listener_account_id=payload.listener_account_id,
        monitored_chat_ids=[c.strip() for c in payload.monitored_chat_ids if c.strip()],
        keywords=[k.strip() for k in payload.keywords if k.strip()],
        match_mode=payload.match_mode,
        exclude_keywords=[k.strip() for k in payload.exclude_keywords if k.strip()],
        alert_webhook_url=payload.alert_webhook_url,
        alert_target_chat_id=payload.alert_target_chat_id,
        is_enabled=payload.is_enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await keyword_monitor_manager.reload_rules()
    return rule


@router.patch(
    "/api/keyword-rules/{rule_id}",
    response_model=KeywordRuleOut,
    summary="更新关键词监控规则",
)
async def update_keyword_rule(
    rule_id: int,
    payload: KeywordRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> KeywordRule:
    """更新关键词监控规则并热加载。"""
    rule = await db.get(KeywordRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="关键词规则不存在"
        )

    data = payload.model_dump(exclude_unset=True)
    if "listener_account_id" in data:
        if await db.get(Account, data["listener_account_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="监听账号不存在"
            )

    for key, value in data.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    await keyword_monitor_manager.reload_rules()
    return rule


@router.delete(
    "/api/keyword-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除关键词监控规则",
)
async def delete_keyword_rule(
    rule_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """删除关键词监控规则并刷新监听池。"""
    rule = await db.get(KeywordRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="关键词规则不存在"
        )
    await db.delete(rule)
    await db.commit()
    await keyword_monitor_manager.reload_rules()


@router.get("/api/keyword-alerts", response_model=list[KeywordAlertOut], summary="获取关键词告警列表")
async def list_keyword_alerts(
    is_read: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[KeywordAlert]:
    """查询关键词命中告警记录。"""
    stmt = (
        select(KeywordAlert)
        .order_by(KeywordAlert.created_at.desc(), KeywordAlert.id.desc())
        .limit(limit)
    )
    if is_read is not None:
        stmt = stmt.where(KeywordAlert.is_read.is_(is_read))
    return list((await db.execute(stmt)).scalars().all())


@router.patch(
    "/api/keyword-alerts/{alert_id}/read",
    response_model=KeywordAlertOut,
    summary="标记告警为已读",
)
async def mark_keyword_alert_read(
    alert_id: int, db: AsyncSession = Depends(get_db)
) -> KeywordAlert:
    """将指定关键词告警标记为已读。"""
    alert = await db.get(KeywordAlert, alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="告警记录不存在"
        )
    alert.is_read = True
    await db.commit()
    await db.refresh(alert)
    return alert

