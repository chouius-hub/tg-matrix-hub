import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import and_, select, update

from app.core.database import AsyncSessionLocal
from app.core.ws_manager import ws_manager
from app.models.account import Account
from app.models.task import TaskJob, TaskLog
from app.workers.health_check import run_spambot_health_check
from app.workers.scheduled_post import scan_and_dispatch_due_posts

logger = logging.getLogger(__name__)


async def recover_cooldown_accounts() -> int:
    """每分钟扫描并自动恢复已过冷却期的账号（cooldown -> active）。"""
    now_utc = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        stmt = (
            update(Account)
            .where(
                and_(
                    Account.status == "cooldown",
                    Account.cooldown_until.is_not(None),
                    Account.cooldown_until <= now_utc,
                )
            )
            .values(status="active", cooldown_until=None)
            .returning(Account.id)
        )
        recovered_ids = list((await db.execute(stmt)).scalars().all())
        if recovered_ids:
            await db.commit()
            logger.info("已自动恢复 %d 个冷却期结束的账号: %s", len(recovered_ids), recovered_ids)
            await ws_manager.broadcast(
                "account_status",
                {
                    "event": "cooldown_recovered",
                    "account_ids": recovered_ids,
                },
            )
        return len(recovered_ids)


async def reset_daily_quotas_and_recover_health() -> None:
    """每日 UTC 00:00 清零全部账号的今日操作配额，并为连续 24h 无风控的活跃号恢复健康分。"""
    now_utc = datetime.now(timezone.utc)
    since_24h = now_utc - timedelta(hours=24)

    async with AsyncSessionLocal() as db:
        # 1. 查询过去 24 小时有成功任务且无风控错误的账号 ID
        success_ids_stmt = (
            select(TaskLog.account_id)
            .where(
                TaskLog.created_at >= since_24h,
                TaskLog.result == "success",
            )
            .distinct()
        )
        risk_ids_stmt = (
            select(TaskLog.account_id)
            .where(
                TaskLog.created_at >= since_24h,
                TaskLog.result.in_(["flood_wait", "peer_flood", "auth_invalid", "proxy_dead"]),
            )
            .distinct()
        )
        success_ids = set((await db.execute(success_ids_stmt)).scalars().all())
        risk_ids = set((await db.execute(risk_ids_stmt)).scalars().all())
        healthy_ids = list(success_ids - risk_ids)

        if healthy_ids:
            active_accounts = (
                await db.execute(
                    select(Account).where(
                        Account.id.in_(healthy_ids),
                        Account.status == "active",
                        Account.health_score < 100,
                    )
                )
            ).scalars().all()
            for acc in active_accounts:
                acc.health_score = min(100, acc.health_score + 5)

        # 2. 清零全部账号每日配额计数
        await db.execute(update(Account).values(daily_action_count=0))
        await db.commit()
        logger.info("每日 UTC 00:00 配额已全部清零，%d 个健康账号已加分。", len(healthy_ids))


async def execute_scheduled_task_job(job_id: int) -> None:
    """执行 task_jobs 表中配置的周期性任务（如批量体检）。"""
    async with AsyncSessionLocal() as db:
        job = await db.get(TaskJob, job_id)
        if not job or not job.is_enabled:
            return

        job.last_run_at = datetime.now(timezone.utc)
        await db.commit()

        if job.job_type == "health_check":
            target_ids = job.target_account_ids or []
            if not target_ids:
                target_ids = list(
                    (
                        await db.execute(
                            select(Account.id).where(Account.status == "active")
                        )
                    )
                    .scalars()
                    .all()
                )
            for acc_id in target_ids:
                try:
                    await run_spambot_health_check(db, int(acc_id))
                except Exception as exc:
                    logger.warning("定时体检账号 [id=%s] 跳过/失败: %s", acc_id, exc)


class SchedulerManager:
    """基于 APScheduler 3.x 的全局异步任务调度管理器。"""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    @property
    def scheduler(self) -> AsyncIOScheduler:
        return self._scheduler

    async def sync_task_jobs_from_db(self) -> None:
        """从 task_jobs 表加载并刷新启用中的 Cron 定时任务。"""
        async with AsyncSessionLocal() as db:
            jobs = (
                await db.execute(
                    select(TaskJob).where(
                        TaskJob.is_enabled.is_(True),
                        TaskJob.cron_expr.is_not(None),
                    )
                )
            ).scalars().all()

        # 清理旧的动态任务（保留系统内置任务）
        for existing in list(self._scheduler.get_jobs()):
            if existing.id.startswith("db_job_"):
                existing.remove()

        for job in jobs:
            if not job.cron_expr:
                continue
            try:
                trigger = CronTrigger.from_crontab(job.cron_expr, timezone="UTC")
                self._scheduler.add_job(
                    execute_scheduled_task_job,
                    trigger=trigger,
                    args=[job.id],
                    id=f"db_job_{job.id}",
                    replace_existing=True,
                )
            except Exception as exc:
                logger.error("加载定时任务 [id=%s, name=%s] Cron 表达式失败: %s", job.id, job.name, exc)

    async def start(self) -> None:
        """启动调度器并注册系统内置定时任务。"""
        if self._scheduler.running:
            return

        self._scheduler.add_job(
            recover_cooldown_accounts,
            trigger=IntervalTrigger(minutes=1),
            id="sys_recover_cooldown",
            replace_existing=True,
        )
        self._scheduler.add_job(
            reset_daily_quotas_and_recover_health,
            trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
            id="sys_reset_daily_quotas",
            replace_existing=True,
        )
        self._scheduler.add_job(
            scan_and_dispatch_due_posts,
            trigger=IntervalTrigger(seconds=30),
            id="sys_scan_scheduled_posts",
            replace_existing=True,
        )

        await self.sync_task_jobs_from_db()
        self._scheduler.start()
        logger.info("SchedulerManager 已启动（UTC 时区）。")

    def shutdown(self) -> None:
        """优雅关闭调度器。"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("SchedulerManager 已关闭。")


scheduler_manager = SchedulerManager()

