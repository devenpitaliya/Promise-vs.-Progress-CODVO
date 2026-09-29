"""Workflow: ask the trackers (GitHub, Jira) what actually happened, persist it, and evaluate promise vs. progress."""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import SyncStatus, TaskStatus, VerificationStatus
from app.models.task import Task
from app.repositories import TaskRepository
from app.schemas.reconciliation import ReconciliationReport
from app.services.connectors import TrackerConnector, load_connectors
from app.services.reconciliation_service import build_report
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)


@observe("github-verification")
async def refresh_verification(db: AsyncSession, owner_id: int, tasks: Sequence[Task]) -> None:
    """Ask each task's tracker (bounded concurrency) whether it is really done, and record the answer."""
    candidates = [t for t in tasks if t.sync_status == SyncStatus.SYNCED and t.status != TaskStatus.CANCELLED]
    if not candidates:
        return

    connectors = await load_connectors(db, owner_id)
    groups: Dict[str, List[Task]] = defaultdict(list)
    for task in candidates:
        groups[connectors.tracker_for(task).kind].append(task)

    semaphore = asyncio.Semaphore(settings.GITHUB_MAX_CONCURRENCY)
    now = datetime.now(UTC)

    async def check(tracker: TrackerConnector, task: Task) -> None:
        async with semaphore:
            outcome = await tracker.verify(task)
        task.verification_status = outcome.status
        task.github_state = outcome.state
        task.verification_note = outcome.note
        task.last_checked_at = now
        if outcome.status == VerificationStatus.VERIFIED_DONE:
            task.verified_at = task.verified_at or now
            task.status = TaskStatus.DONE  # evidence overrides the self-reported state
        else:
            task.verified_at = None

    for kind, group in groups.items():
        tracker = connectors.tracker(kind)
        async with tracker.session():
            await asyncio.gather(*(check(tracker, t) for t in group))


@observe("reconciliation")
async def run_reconciliation(
    db: AsyncSession, owner_id: int, meeting_id: Optional[int] = None, task_ids: Optional[Iterable[int]] = None
) -> ReconciliationReport:
    session_id = f"meeting-{meeting_id}" if meeting_id else None
    with tracing.trace_attributes(user_id=owner_id, session_id=session_id, name="reconciliation", tags=["reconciliation"]):
        return await _run_reconciliation(db, owner_id, meeting_id, task_ids)


async def _run_reconciliation(
    db: AsyncSession, owner_id: int, meeting_id: Optional[int], task_ids: Optional[Iterable[int]]
) -> ReconciliationReport:
    tasks = await TaskRepository(db).list_tracked(owner_id, meeting_id=meeting_id, task_ids=task_ids)
    await refresh_verification(db, owner_id, tasks)
    await db.flush()
    report = build_report(tasks, meeting_id=meeting_id, github_mode=(await load_connectors(db, owner_id)).mode("github"))
    logger.info(
        "Reconciliation for user %s (meeting=%s): %s tracked, %s%% verified, %s overdue, %s claimed-unverified",
        owner_id,
        meeting_id or "all",
        report.total,
        report.completion_rate,
        report.counts["OVERDUE"],
        report.counts["CLAIMED_UNVERIFIED"],
    )
    tracing.update_span(output={"total": report.total, "completion_rate": report.completion_rate, "counts": report.counts})
    return report


@observe("scheduled-verification")
async def verify_all_owners(db: AsyncSession) -> None:
    """Background job: refresh every user's tracked commitments, isolating failures per user."""
    repo = TaskRepository(db)
    owners = await repo.owners_with_synced_tasks()
    logger.info("Background verification started for %s user(s)", len(owners))
    for owner_id in owners:
        try:
            with tracing.trace_attributes(user_id=owner_id, name="scheduled-verification", tags=["scheduler"]):
                await refresh_verification(db, owner_id, await repo.list_tracked(owner_id))
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Background verification failed for owner %s", owner_id)
    await tracing.flush()
