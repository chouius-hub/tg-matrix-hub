import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.accounts import router as accounts_router
from app.api.keywords import router as keywords_router
from app.api.posts import router as posts_router
from app.api.proxies import router as proxies_router
from app.api.sync import router as sync_router
from app.api.system import router as system_router
from app.core.database import engine, get_db
from app.engine.pool import client_pool
from app.engine.scheduler import scheduler_manager
from app.workers.channel_sync import channel_sync_manager
from app.workers.keyword_monitor import keyword_monitor_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI 生命周期管理：启动与优雅关闭连接池、调度器及数据库连接池。"""
    logger.info("tg-matrix-hub 后端服务正在启动...")
    client_pool.start_background_cleanup()
    await scheduler_manager.start()
    await channel_sync_manager.reload_rules()
    await keyword_monitor_manager.reload_rules()
    yield
    scheduler_manager.shutdown()
    await client_pool.close_all()
    await engine.dispose()
    logger.info("tg-matrix-hub 后端服务已优雅关闭。")


app = FastAPI(
    title="tg-matrix-hub API",
    description="Telegram 矩阵运营与风控调度系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(proxies_router)
app.include_router(accounts_router)
app.include_router(sync_router)
app.include_router(posts_router)
app.include_router(keywords_router)
app.include_router(system_router)


@app.get("/api/health", summary="服务与数据库健康检查")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """校验 API 服务与 PostgreSQL 数据库连通性。"""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        logger.error("数据库健康检查失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库连接异常",
        ) from exc
