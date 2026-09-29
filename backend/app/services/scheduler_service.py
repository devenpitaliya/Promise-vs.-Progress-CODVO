"""Scheduling only: builds APScheduler triggers; the work itself lives in app/workflows.

Schedules are rows in `scheduled_audits`; in-memory jobs are rebuilt from them on startup, so a
restart never loses a schedule. Run the scheduler in exactly one process (ENABLE_SCHEDULER).
"""

import logging
from datetime import UTC, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from app.config import settings
from app.database.session import async_session_maker
from app.enums import ScheduleStatus, ScheduleType
from app.models.audit import ScheduledAudit
from app.repositories import ScheduledAuditRepository
from app.workflows.pre_meeting_audit_workflow import AuditRunResult, run_pre_meeting_audit
from app.workflows.reconciliation_workflow import verify_all_owners

logger = logging.getLogger(__name__)

VERIFICATION_JOB_ID = "periodic-verification"
MISFIRE_GRACE_SECONDS = 3600


def _job_id(audit_id: int) -> str:
    return f"audit-{audit_id}"


class SchedulerService:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=UTC)

    @property
    def running(self) -> bool:
        return self.scheduler.running

    async def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.start()
        self.scheduler.add_job(
            self._verify_all,
            "interval",
            minutes=settings.VERIFICATION_INTERVAL_MINUTES,
            id=VERIFICATION_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        async with async_session_maker() as db:
            for audit in await ScheduledAuditRepository(db).list_active():
                self.schedule(audit)
        logger.info("Scheduler started (verification every %s min)", settings.VERIFICATION_INTERVAL_MINUTES)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule(self, audit: ScheduledAudit) -> None:
        if not self.scheduler.running:
            return  # jobs are rebuilt from the table when the scheduler starts
        tz = ZoneInfo(audit.timezone)
        if audit.schedule_type == ScheduleType.SINGLE:
            run_at = audit.run_at if audit.run_at.tzinfo else audit.run_at.replace(tzinfo=UTC)
            trigger = DateTrigger(run_date=run_at)
        else:
            hour, minute = (int(part) for part in audit.daily_time.split(":"))
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                start_date=datetime.combine(audit.start_date, time(0, 0), tzinfo=tz),
                end_date=datetime.combine(audit.end_date, time(23, 59, 59), tzinfo=tz),
                timezone=tz,
            )
        self.scheduler.add_job(
            self.run_audit,
            trigger,
            args=[audit.id],
            id=_job_id(audit.id),
            replace_existing=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            coalesce=True,
            max_instances=1,
        )

    def unschedule(self, audit_id: int) -> None:
        job = self.scheduler.get_job(_job_id(audit_id)) if self.scheduler.running else None
        if job:
            job.remove()

    def next_run_at(self, audit_id: int) -> Optional[datetime]:
        job = self.scheduler.get_job(_job_id(audit_id)) if self.scheduler.running else None
        return job.next_run_time if job else None

    async def run_audit(self, audit_id: int) -> tuple[AuditRunResult, Optional[ScheduledAudit]]:
        result, audit = await run_pre_meeting_audit(audit_id)
        if audit is not None and audit.status != ScheduleStatus.ACTIVE:
            self.unschedule(audit_id)
        return result, audit

    async def _verify_all(self) -> None:
        async with async_session_maker() as db:
            await verify_all_owners(db)


scheduler_service = SchedulerService()
