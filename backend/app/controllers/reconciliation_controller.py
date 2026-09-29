from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.meeting_controller import MeetingController
from app.models.user import User
from app.repositories import TaskRepository
from app.schemas.integration import SlackPostResponse
from app.schemas.reconciliation import ReconcileRequest, ReconciliationReport
from app.services.connectors import is_available, load_connectors
from app.services.notification_service import reminder_message
from app.services.reconciliation_service import build_report
from app.utils.exceptions import ConflictError, UpstreamError
from app.workflows.reconciliation_workflow import run_reconciliation


class ReconciliationController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    async def report(self, meeting_id: Optional[int]) -> ReconciliationReport:
        """Read-only: evaluates stored state; never calls GitHub or writes."""
        if meeting_id is not None:
            await MeetingController(self.db, self.user).get_owned(meeting_id)
        tasks = await TaskRepository(self.db).list_tracked(self.user.id, meeting_id=meeting_id)
        connectors = await load_connectors(self.db, self.user.id)
        return build_report(tasks, meeting_id=meeting_id, github_mode=connectors.mode("github"))

    async def run(self, payload: ReconcileRequest) -> ReconciliationReport:
        if payload.meeting_id is not None:
            await MeetingController(self.db, self.user).get_owned(payload.meeting_id)
        return await run_reconciliation(self.db, self.user.id, meeting_id=payload.meeting_id, task_ids=payload.task_ids)

    async def remind_on_slack(self, meeting_id: Optional[int]) -> SlackPostResponse:
        """Post overdue, due-today, at-risk, blocked and unverified commitments to Slack, grouped by owner."""
        if not is_available("slack"):
            raise ConflictError("Slack reminders are coming soon.")
        connectors = await load_connectors(self.db, self.user.id)
        if not connectors.slack.is_configured():
            raise ConflictError("Slack is not connected. Add it in Settings > Integrations.")
        meeting = await MeetingController(self.db, self.user).get_owned(meeting_id) if meeting_id is not None else None
        report = await self.report(meeting_id)
        message = reminder_message(report, meeting.title if meeting else "all meetings")
        if message is None:
            return SlackPostResponse(ok=True, message="Nothing needs attention, so no reminder was posted.")
        result = await connectors.slack.send(message)
        if not result.ok:
            raise UpstreamError(result.message)
        return SlackPostResponse(ok=True, message=result.message)
