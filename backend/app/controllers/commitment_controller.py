import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.meeting_controller import MeetingController
from app.enums import ApprovalStatus, SyncStatus, TargetSystem, TaskStatus, VerificationStatus
from app.models.task import Task
from app.models.user import User
from app.repositories import TaskRepository
from app.schemas.task import (
    RetryFailedRequest,
    RetryFailedResult,
    ReviewRequest,
    ReviewResult,
    SearchHit,
    SearchResponse,
    SimulatedSyncResult,
    SimulateStateRequest,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services.connectors import is_available, load_connectors
from app.services.vector_store_service import vector_store
from app.utils.exceptions import ConflictError, InvalidRequestError, NotFoundError
from app.workflows.reconciliation_workflow import refresh_verification
from app.workflows.review_workflow import apply_review, sync_tasks


def _require_tracker_available(target_system: Optional[str]) -> None:
    if target_system == TargetSystem.JIRA and not is_available("jira"):
        raise InvalidRequestError("Jira is coming soon. Track this commitment as a GitHub issue or PR.")


_LINK_FIELDS = {"target_system", "repository", "external_ref"}
# Edits that are mirrored to the ticket as a comment (and the title, for "description").
_MIRRORED_EDITS = ("description", "assignee", "target_date", "priority")

logger = logging.getLogger(__name__)


class CommitmentController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.tasks = TaskRepository(db)

    async def get_owned(self, task_id: int) -> Task:
        task = await self.tasks.get_owned(self.user.id, task_id)
        if task is None:
            raise NotFoundError("Commitment not found")
        return task

    async def list(
        self,
        meeting_id: Optional[int] = None,
        approval_status: Optional[ApprovalStatus] = None,
        status: Optional[TaskStatus] = None,
    ) -> List[Task]:
        return await self.tasks.list_owned(self.user.id, meeting_id=meeting_id, approval_status=approval_status, status=status)

    async def search(self, query: str) -> SearchResponse:
        hits = await vector_store.search(self.user.id, query)
        if hits is None:
            return SearchResponse(available=False, results=[])
        by_id = {t.id: t for t in await self.tasks.list_owned(self.user.id, task_ids=[h["task_id"] for h in hits])}
        return SearchResponse(
            available=True,
            results=[
                SearchHit(score=h["score"], task=TaskResponse.model_validate(by_id[h["task_id"]])) for h in hits if h["task_id"] in by_id
            ],
        )

    async def create(self, payload: TaskCreate) -> Task:
        """A commitment the extraction missed. It starts pending, like extracted ones."""
        meeting = await MeetingController(self.db, self.user).get_owned(payload.meeting_id)
        _require_tracker_available(payload.target_system)
        task = await self.tasks.add(Task(owner_id=self.user.id, meeting_id=meeting.id, **payload.model_dump(exclude={"meeting_id"})))
        await self.db.refresh(task)
        await vector_store.index_tasks([task])
        return task

    async def review(self, meeting_id: int, payload: ReviewRequest) -> ReviewResult:
        meeting = await MeetingController(self.db, self.user).get_owned(meeting_id)
        return await apply_review(self.db, meeting, payload)

    async def update(self, task_id: int, payload: TaskUpdate) -> Task:
        task = await self.get_owned(task_id)
        changes = payload.model_dump(exclude_unset=True)
        _require_tracker_available(changes.get("target_system"))
        before = {field: getattr(task, field) for field in changes}
        for field, value in changes.items():
            setattr(task, field, value)
        changed = {field: value for field, value in changes.items() if before[field] != value}

        # Re-pointing a synced commitment at a different ticket invalidates the old link.
        relinked = bool(_LINK_FIELDS & changed.keys()) and task.sync_status == SyncStatus.SYNCED
        if relinked:
            task.sync_status = SyncStatus.NOT_SYNCED
            task.github_url = task.github_issue_number = task.github_pr_number = task.external_key = None
            task.github_state = task.app_closed_marker = None
            task.verification_status = VerificationStatus.NOT_CHECKED
            task.verified_at = None
        elif task.sync_status == SyncStatus.SYNCED and not task.is_simulated:
            await self._push_to_tracker(task, before, changed)

        await self.db.flush()
        await self.db.refresh(task)
        await vector_store.index_tasks([task])
        return task

    async def _push_to_tracker(self, task: Task, before: dict, changed: dict) -> None:
        """Two-way sync: mirror status and edits to the linked ticket (comment, close/reopen, title).

        A close done from here is remembered, so reconciliation treats it as a claim; only a close made in the
        tracker itself counts as verified. The local change is always kept, even when the tracker call fails.
        """
        status_change = (str(before["status"]), str(task.status)) if "status" in changed else None
        edits = {field: changed[field] for field in _MIRRORED_EDITS if field in changed}
        if not status_change and not edits:
            return
        tracker = (await load_connectors(self.db, self.user.id)).tracker_for(task)
        async with tracker.session():
            outcome = await tracker.push_update(task, status_change, edits, actor=self.user.full_name or f"User {self.user.id}")
        if outcome is None:
            return
        task.tracker_update = outcome.message  # returned to the client once, not stored
        if outcome.closed_marker is not None:
            task.app_closed_marker = outcome.closed_marker or None
        if outcome.ok and status_change:
            await refresh_verification(self.db, self.user.id, [task])
        logger.info("User %s updated %s for commitment %s: %s", self.user.id, tracker.label, task.id, "ok" if outcome.ok else "failed")

    async def delete(self, task_id: int) -> None:
        task = await self.get_owned(task_id)
        await self.tasks.delete(task)
        await vector_store.delete_tasks([task_id])

    async def retry_sync(self, task_id: int) -> Task:
        task = await self.get_owned(task_id)
        if task.approval_status != ApprovalStatus.APPROVED:
            raise ConflictError("Approve the commitment before syncing it.")
        await sync_tasks(self.db, self.user.id, [task])
        if task.sync_status == SyncStatus.SYNCED:
            await refresh_verification(self.db, self.user.id, [task])  # show the tool's real state straight away
        await self.db.flush()
        return task

    async def retry_failed(self, payload: RetryFailedRequest) -> RetryFailedResult:
        """Fix the common causes of failed syncs in one go, then retry them all.

        `repository` is applied to every failed GitHub commitment. `create_missing` drops references to issues
        or PRs that could not be linked, so a new issue is created instead (a PR cannot be created, so a failed
        PR commitment becomes an issue that tracks the work). Jira commitments are retried with their own settings.
        """
        if payload.meeting_id is not None:
            await MeetingController(self.db, self.user).get_owned(payload.meeting_id)
        failed = [
            t for t in await self.tasks.list_tracked(self.user.id, meeting_id=payload.meeting_id) if t.sync_status == SyncStatus.FAILED
        ]
        if not failed:
            return RetryFailedResult(retried=0, synced=0, failures=[])

        for task in failed:
            is_github = task.target_system != TargetSystem.JIRA
            if is_github and payload.repository:
                task.repository = payload.repository.strip()
            if payload.create_missing:
                task.external_ref = None
                if task.target_system == TargetSystem.GITHUB_PR:
                    task.target_system = TargetSystem.GITHUB_ISSUE
        failures = await sync_tasks(self.db, self.user.id, failed)
        synced = [t for t in failed if t.sync_status == SyncStatus.SYNCED]
        await refresh_verification(self.db, self.user.id, synced)
        await self.db.flush()
        logger.info("User %s retried %s failed sync(s): %s synced, %s still failing", self.user.id, len(failed), len(synced), len(failures))
        return RetryFailedResult(retried=len(failed), synced=len(synced), failures=failures)

    async def sync_simulated(self) -> SimulatedSyncResult:
        """Move commitments tracked in simulation to their tool once it is connected (creates or links real tickets)."""
        connectors = await load_connectors(self.db, self.user.id)
        pending = [
            t
            for t in await self.tasks.list_tracked(self.user.id)
            if t.is_simulated and t.sync_status == SyncStatus.SYNCED and connectors.tracker_for(t).mode == "live"
        ]
        if not pending:
            return SimulatedSyncResult(moved=0, failures=[])
        failures = await sync_tasks(self.db, self.user.id, pending)
        moved = [t for t in pending if t.sync_status == SyncStatus.SYNCED and not t.is_simulated]
        await refresh_verification(self.db, self.user.id, moved)
        await self.db.flush()
        logger.info("User %s moved %s simulated commitment(s) to live trackers, %s failed", self.user.id, len(moved), len(failures))
        return SimulatedSyncResult(moved=len(moved), failures=failures)

    async def simulate(self, task_id: int, payload: SimulateStateRequest) -> Task:
        """Move a simulated tracker item to a new state. Items synced to a live GitHub or Jira cannot be simulated."""
        task = await self.get_owned(task_id)
        if not (task.is_simulated and task.sync_status == SyncStatus.SYNCED):
            raise ConflictError("Only approved, simulated commitments can be simulated.")
        tracker = (await load_connectors(self.db, self.user.id)).tracker_for(task)
        if tracker.mode == "live":
            # Evidence must come from the real tool once it is connected.
            raise ConflictError(f"Simulation is disabled because live {tracker.label} is connected.")
        if payload.state == "merged" and task.target_system != TargetSystem.GITHUB_PR:
            raise ConflictError("Only pull requests can be merged.")
        task.github_state = payload.state
        await refresh_verification(self.db, self.user.id, [task])
        await self.db.flush()
        return task
