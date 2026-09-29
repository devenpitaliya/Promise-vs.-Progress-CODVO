"""Workflow: apply a human review decision and sync approved commitments to their tracker (GitHub or Jira)."""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import ApprovalStatus, SyncStatus, VerificationStatus
from app.models.meeting import Meeting
from app.models.task import Task
from app.schemas.task import ReviewFailure, ReviewRequest, ReviewResult, TaskResponse
from app.services.connectors import TrackerConnector, load_connectors
from app.utils import tracing
from app.utils.exceptions import ConflictError, InvalidRequestError
from app.utils.tracing import observe

logger = logging.getLogger(__name__)


async def sync_tasks(db: AsyncSession, owner_id: int, tasks: List[Task]) -> List[ReviewFailure]:
    """Create or link the ticket for each task in its tracker and record the outcome on the task."""
    if not tasks:
        return []
    connectors = await load_connectors(db, owner_id)
    groups: Dict[str, List[Task]] = defaultdict(list)
    for task in tasks:
        groups[connectors.tracker_for(task).kind].append(task)

    failures: List[ReviewFailure] = []
    semaphore = asyncio.Semaphore(settings.GITHUB_MAX_CONCURRENCY)

    async def sync_one(tracker: TrackerConnector, task: Task) -> None:
        was_simulated = task.is_simulated and task.sync_status == SyncStatus.SYNCED
        async with semaphore:
            outcome = await tracker.sync(task)
        task.is_simulated = outcome.is_simulated
        if was_simulated and outcome.ok and not outcome.is_simulated:
            # Moving from simulation to the real tool: forget simulated evidence so only real state counts.
            task.verification_status = VerificationStatus.NOT_CHECKED
            task.verification_note = None
            task.verified_at = None
            task.last_checked_at = None
        if outcome.ok:
            task.sync_status = SyncStatus.SYNCED
            task.sync_error = None
            task.github_url = outcome.url
            task.github_issue_number = outcome.issue_number
            task.github_pr_number = outcome.pr_number
            task.external_key = outcome.external_key
            task.github_state = outcome.state
        else:
            task.sync_status = SyncStatus.FAILED
            task.sync_error = outcome.error
            failures.append(ReviewFailure(task_id=task.id, error=outcome.error or "Sync failed"))

    for kind, group in groups.items():
        tracker = connectors.tracker(kind)
        async with tracker.session():
            await asyncio.gather(*(sync_one(tracker, t) for t in group))
    return failures


@observe("commitment-review")
async def apply_review(db: AsyncSession, meeting: Meeting, request: ReviewRequest) -> ReviewResult:
    """Only the listed IDs are decided; everything else stays pending."""
    with tracing.trace_attributes(user_id=meeting.owner_id, session_id=f"meeting-{meeting.id}", name="commitment-review", tags=["review"]):
        return await _apply_review(db, meeting, request)


async def _apply_review(db: AsyncSession, meeting: Meeting, request: ReviewRequest) -> ReviewResult:
    approve, reject = set(request.approve_ids), set(request.reject_ids)
    if approve & reject:
        raise InvalidRequestError("A commitment cannot be both approved and rejected.")
    by_id = {t.id: t for t in meeting.tasks}
    unknown = (approve | reject) - by_id.keys()
    if unknown:
        raise InvalidRequestError(f"Commitments {sorted(unknown)} do not belong to this meeting.")
    already = [i for i in approve | reject if by_id[i].approval_status != ApprovalStatus.PENDING]
    if already:
        raise ConflictError(f"Commitments {sorted(already)} were already reviewed.")

    for task_id in reject:
        by_id[task_id].approval_status = ApprovalStatus.REJECTED

    approved = [by_id[i] for i in sorted(approve)]
    for task in approved:
        task.approval_status = ApprovalStatus.APPROVED
        if not task.repository and request.default_repository:
            task.repository = request.default_repository
    failures = await sync_tasks(db, meeting.owner_id, approved)
    await db.flush()
    logger.info("Review of meeting %s: %s approved, %s rejected, %s sync failure(s)", meeting.id, len(approved), len(reject), len(failures))
    for failure in failures:
        logger.warning("Sync failed for commitment %s: %s", failure.task_id, failure.error)
    tracing.update_span(
        output={"approved": len(approved), "rejected": len(reject), "sync_failures": len(failures)}, metadata={"meeting_id": meeting.id}
    )

    return ReviewResult(
        approved=[TaskResponse.model_validate(t) for t in approved],
        rejected_ids=sorted(reject),
        sync_failures=failures,
    )
