from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.channel_sync import ChannelSyncRule
from app.schemas.sync import (
    ChannelSyncRuleCreate,
    ChannelSyncRuleOut,
    ChannelSyncRuleUpdate,
)
from app.workers.channel_sync import channel_sync_manager

router = APIRouter(prefix="/api/sync-rules", tags=["多频道 AI 翻译转发"])


async def _ensure_accounts_exist(
    db: AsyncSession, listener_id: int, publisher_id: int
) -> None:
    """校验监听号与发布号是否存在。"""
    if await db.get(Account, listener_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="监听账号不存在"
        )
    if await db.get(Account, publisher_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="发布账号不存在"
        )


@router.get("", response_model=list[ChannelSyncRuleOut], summary="获取频道转发规则列表")
async def list_sync_rules(db: AsyncSession = Depends(get_db)) -> list[ChannelSyncRule]:
    """查询所有频道采集转发规则。"""
    return list(
        (await db.execute(select(ChannelSyncRule).order_by(ChannelSyncRule.id.desc())))
        .scalars()
        .all()
    )


@router.post(
    "",
    response_model=ChannelSyncRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建频道转发规则",
)
async def create_sync_rule(
    payload: ChannelSyncRuleCreate,
    db: AsyncSession = Depends(get_db),
) -> ChannelSyncRule:
    """新增频道转发规则并热加载至常驻监听池。"""
    await _ensure_accounts_exist(
        db, payload.listener_account_id, payload.publisher_account_id
    )
    rule = ChannelSyncRule(
        name=payload.name,
        listener_account_id=payload.listener_account_id,
        publisher_account_id=payload.publisher_account_id,
        source_chat_id=payload.source_chat_id.strip(),
        target_chat_id=payload.target_chat_id.strip(),
        enable_ai_translate=payload.enable_ai_translate,
        ai_system_prompt=payload.ai_system_prompt,
        regex_replacements=[item.model_dump() for item in payload.regex_replacements],
        blocked_keywords=payload.blocked_keywords,
        append_footer=payload.append_footer,
        min_delay_sec=payload.min_delay_sec,
        max_delay_sec=max(payload.min_delay_sec, payload.max_delay_sec),
        is_enabled=payload.is_enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await channel_sync_manager.reload_rules()
    return rule


@router.patch("/{rule_id}", response_model=ChannelSyncRuleOut, summary="更新频道转发规则")
async def update_sync_rule(
    rule_id: int,
    payload: ChannelSyncRuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> ChannelSyncRule:
    """更新转发规则并热加载。"""
    rule = await db.get(ChannelSyncRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="转发规则不存在"
        )

    data = payload.model_dump(exclude_unset=True)
    if "listener_account_id" in data or "publisher_account_id" in data:
        await _ensure_accounts_exist(
            db,
            data.get("listener_account_id", rule.listener_account_id),
            data.get("publisher_account_id", rule.publisher_account_id),
        )
    if "regex_replacements" in data and payload.regex_replacements is not None:
        data["regex_replacements"] = [
            item.model_dump() for item in payload.regex_replacements
        ]

    for key, value in data.items():
        setattr(rule, key, value)
    if rule.max_delay_sec < rule.min_delay_sec:
        rule.max_delay_sec = rule.min_delay_sec

    await db.commit()
    await db.refresh(rule)
    await channel_sync_manager.reload_rules()
    return rule


@router.delete(
    "/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除频道转发规则"
)
async def delete_sync_rule(rule_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """删除转发规则并刷新监听池。"""
    rule = await db.get(ChannelSyncRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="转发规则不存在"
        )
    await db.delete(rule)
    await db.commit()
    await channel_sync_manager.reload_rules()


@router.post("/{rule_id}/toggle", response_model=ChannelSyncRuleOut, summary="启停转发规则")
async def toggle_sync_rule(
    rule_id: int, db: AsyncSession = Depends(get_db)
) -> ChannelSyncRule:
    """一键切换频道转发规则的启用/停用状态并热加载。"""
    rule = await db.get(ChannelSyncRule, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="转发规则不存在"
        )
    rule.is_enabled = not rule.is_enabled
    await db.commit()
    await db.refresh(rule)
    await channel_sync_manager.reload_rules()
    return rule

