import logging
from datetime import UTC, datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.limits import EMAIL_HISTORY_LIMIT
from app.controllers.meeting_controller import MeetingController
from app.enums import ScheduleStatus, ScheduleType
from app.models.audit import EmailLog, ScheduledAudit
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import EmailLogRepository, ScheduledAuditRepository
from app.schemas.briefing import (
    AuditRunResponse,
    BriefingPreview,
    BriefingRequest,
    EmailLogResponse,
    ScheduleAuditRequest,
    ScheduledAuditResponse,
    SendBriefingRequest,
    SendBriefingResponse,
)
from app.schemas.integration import SlackPostRequest, SlackPostResponse
from app.services.connectors import is_available, load_connectors
from app.services.email_service import send_email
from app.services.notification_service import briefing_message
from app.services.scheduler_service import scheduler_service
from app.utils.exceptions import ConflictError, InvalidRequestError, NotFoundError, UpstreamError
from app.workflows.briefing_workflow import build_briefing

logger = logging.getLogger(__name__)


class BriefingController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.audits = ScheduledAuditRepository(db)

    async def _meeting(self, meeting_id: Optional[int]) -> Optional[Meeting]:
        return await MeetingController(self.db, self.user).get_owned(meeting_id) if meeting_id else None

    async def _owned_audit(self, audit_id: int) -> ScheduledAudit:
        audit = await self.audits.get_owned(self.user.id, audit_id)
        if audit is None:
            raise NotFoundError("Scheduled audit not found")
        return audit

    @staticmethod
    def _audit_response(audit: ScheduledAudit) -> ScheduledAuditResponse:
        response = ScheduledAuditResponse.model_validate(audit)
        if audit.status == ScheduleStatus.ACTIVE:
            response.next_run_at = scheduler_service.next_run_at(audit.id)
        return response

    async def preview(self, payload: BriefingRequest) -> BriefingPreview:
        return await build_briefing(self.db, self.user, await self._meeting(payload.meeting_id), payload.custom_instructions)

    async def send(self, payload: SendBriefingRequest) -> SendBriefingResponse:
        """The server builds the email from verified data; clients cannot supply HTML."""
        meeting = await self._meeting(payload.meeting_id)
        preview = await build_briefing(self.db, self.user, meeting, payload.custom_instructions)
        log = await send_email(
            self.db,
            owner_id=self.user.id,
            recipient=str(payload.recipient_email),
            subject=preview.subject,
            html=preview.html,
            meeting_id=meeting.id if meeting else None,
        )
        return SendBriefingResponse(email=EmailLogResponse.model_validate(log), preview=preview)

    async def post_to_slack(self, payload: SlackPostRequest) -> SlackPostResponse:
        """Same verified briefing as the email, posted to the connected Slack channel."""
        if not is_available("slack"):
            raise ConflictError("Slack is coming soon.")
        connectors = await load_connectors(self.db, self.user.id)
        if not connectors.slack.is_configured():
            raise ConflictError("Slack is not connected. Add it in Settings > Integrations.")
        preview = await build_briefing(self.db, self.user, await self._meeting(payload.meeting_id), payload.custom_instructions)
        result = await connectors.slack.send(briefing_message(preview))
        logger.info("User %s posted a briefing to Slack: %s", self.user.id, "ok" if result.ok else "failed")
        if not result.ok:
            raise UpstreamError(result.message)
        return SlackPostResponse(ok=True, message=result.message)

    async def email_history(self) -> List[EmailLog]:
        return await EmailLogRepository(self.db).list_recent(self.user.id, EMAIL_HISTORY_LIMIT)

    async def create_schedule(self, payload: ScheduleAuditRequest) -> ScheduledAuditResponse:
        await self._meeting(payload.meeting_id)
        if payload.post_to_slack and not is_available("slack"):
            raise InvalidRequestError("Slack briefings are coming soon; deliver this schedule by email.")
        if payload.post_to_slack and not (await load_connectors(self.db, self.user.id)).slack.is_configured():
            raise InvalidRequestError("Connect Slack in Settings > Integrations before scheduling Slack briefings.")
        if payload.schedule_type == ScheduleType.SINGLE:
            run_at = payload.run_at if payload.run_at.tzinfo else payload.run_at.replace(tzinfo=UTC)
            if run_at <= datetime.now(UTC):
                raise InvalidRequestError("run_at must be in the future.")
            payload.run_at = run_at

        audit = await self.audits.add(ScheduledAudit(owner_id=self.user.id, **payload.model_dump()))
        await self.db.commit()  # persist before scheduling so the job can always load its row
        scheduler_service.schedule(audit)
        logger.info("User %s created %s audit %s (%s)", self.user.id, audit.schedule_type, audit.id, audit.timezone)
        return self._audit_response(audit)

    async def list_schedules(self) -> List[ScheduledAuditResponse]:
        return [self._audit_response(a) for a in await self.audits.list_for_owner(self.user.id)]

    async def cancel_schedule(self, audit_id: int) -> ScheduledAuditResponse:
        audit = await self._owned_audit(audit_id)
        if audit.status == ScheduleStatus.ACTIVE:
            audit.status = ScheduleStatus.CANCELLED
            scheduler_service.unschedule(audit.id)
            logger.info("User %s cancelled audit %s", self.user.id, audit.id)
        return self._audit_response(audit)

    async def run_schedule_now(self, audit_id: int) -> AuditRunResponse:
        audit = await self._owned_audit(audit_id)
        if audit.status != ScheduleStatus.ACTIVE:
            raise ConflictError("Only active schedules can be run.")
        await self.db.commit()
        result, _ = await scheduler_service.run_audit(audit_id)
        if result.error:
            raise UpstreamError(result.error)
        return AuditRunResponse(
            email=EmailLogResponse.model_validate(result.email) if result.email else None,
            slack_ok=result.slack.ok if result.slack else None,
            slack_message=result.slack.message if result.slack else None,
        )
