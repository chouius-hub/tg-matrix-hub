import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.account import Account
from app.models.scheduled_post import ScheduledPost
from app.schemas.post import (
    MediaUploadOut,
    ScheduledPostCreate,
    ScheduledPostOut,
    ScheduledPostUpdate,
)

router = APIRouter(tags=["定时发帖排期"])

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOADS_DIR = BACKEND_DIR / "storage" / "uploads"
ALLOWED_MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".mov"}


@router.post("/api/uploads/media", response_model=MediaUploadOut, summary="上传发帖媒体文件")
async def upload_post_media(file: UploadFile = File(...)) -> MediaUploadOut:
    """将图片或视频保存至 storage/uploads/，返回相对路径供定时发帖引用。"""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    orig_name = file.filename or "media.bin"
    suffix = Path(orig_name).suffix.lower()
    if suffix not in ALLOWED_MEDIA_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的媒体格式 ({suffix})，仅支持 jpg/png/gif/webp/mp4/mov",
        )

    content = await file.read()
    saved_name = f"{uuid.uuid4().hex}{suffix}"
    target_path = UPLOADS_DIR / saved_name
    target_path.write_bytes(content)

    rel_path = str(target_path.relative_to(BACKEND_DIR)).replace("\\", "/")
    return MediaUploadOut(
        file_path=rel_path,
        filename=orig_name,
        size_bytes=len(content),
    )


@router.get("/api/scheduled-posts", response_model=list[ScheduledPostOut], summary="获取定时发帖列表")
async def list_scheduled_posts(
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledPost]:
    """按计划时间倒序返回全部定时发帖任务。"""
    return list(
        (
            await db.execute(
                select(ScheduledPost).order_by(ScheduledPost.scheduled_at.desc())
            )
        )
        .scalars()
        .all()
    )


@router.post(
    "/api/scheduled-posts",
    response_model=ScheduledPostOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建定时发帖任务",
)
async def create_scheduled_post(
    payload: ScheduledPostCreate,
    db: AsyncSession = Depends(get_db),
) -> ScheduledPost:
    """新增定时发帖排期。"""
    if await db.get(Account, payload.publisher_account_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="发布账号不存在"
        )

    post = ScheduledPost(
        title=payload.title,
        publisher_account_id=payload.publisher_account_id,
        target_chat_ids=[t.strip() for t in payload.target_chat_ids if t.strip()],
        content_text=payload.content_text,
        parse_mode=payload.parse_mode,
        media_file_path=payload.media_file_path,
        disable_web_page_preview=payload.disable_web_page_preview,
        scheduled_at=payload.scheduled_at,
        status="pending",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.patch(
    "/api/scheduled-posts/{post_id}",
    response_model=ScheduledPostOut,
    summary="修改定时发帖任务",
)
async def update_scheduled_post(
    post_id: int,
    payload: ScheduledPostUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScheduledPost:
    """修改处于 pending 状态的定时发帖任务（或取消排期）。"""
    post = await db.get(ScheduledPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="定时发帖记录不存在"
        )
    if post.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态为 {post.status}，仅 pending 状态可修改",
        )

    data = payload.model_dump(exclude_unset=True)
    if "publisher_account_id" in data:
        if await db.get(Account, data["publisher_account_id"]) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="发布账号不存在"
            )
    if "target_chat_ids" in data and data["target_chat_ids"] is not None:
        data["target_chat_ids"] = [
            t.strip() for t in data["target_chat_ids"] if t.strip()
        ]

    for key, value in data.items():
        setattr(post, key, value)

    await db.commit()
    await db.refresh(post)
    return post


@router.delete(
    "/api/scheduled-posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除定时发帖任务",
)
async def delete_scheduled_post(
    post_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """删除定时发帖排期记录。"""
    post = await db.get(ScheduledPost, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="定时发帖记录不存在"
        )
    await db.delete(post)
    await db.commit()

