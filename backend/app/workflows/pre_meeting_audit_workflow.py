"""Workflow: the scheduled pre-meeting audit.

reconcile against the trackers -> build the briefing -> email it and/or post it to Slack -> record the run.
Runs in its own session so it works from the scheduler as well as from "Run now".
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from app.database.session import async_session_maker
from app.enums import ScheduleStatus, ScheduleType
from app.models.audit import EmailLog, ScheduledAudit
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import ScheduledAuditRepository, TaskRepository
from app.services.connectors import ConnectionTest, load_connectors
from app.services.email_service import send_email
from app.services.notification_service import briefing_message
from app.services.reconciliation_service import local_today
from app.utils import tracing
from app.utils.tracing import observe
from app.workflows.briefing_workflow import build_briefing
from app.workflows.reconciliation_workflow import refresh_verification

logger = logging.getLogger(__name__)


@observe("pre-meeting-audit")
@dataclass
class AuditRunResult:
    email: Optional[EmailLog] = None
    slack: Optional[ConnectionTest] = None
    error: Optional[str] = None


async def run_pre_meeting_audit(audit_id: int) -> tuple[AuditRunResult, Optional[ScheduledAudit]]:
    """Returns what was delivered (email log, Slack result, or the error) and the audit after the run."""
    async with async_session_maker() as db:
        audit = await ScheduledAuditRepository(db).get(audit_id)
        if audit is None or audit.status != ScheduleStatus.ACTIVE:
            return AuditRunResult(error="The schedule is not active."), audit
        user = await db.get(User, audit.owner_id)
        meeting = await db.get(Meeting, audit.meeting_id) if audit.meeting_id else None
        result = AuditRunResult()

        try:
            with tracing.trace_attributes(
                user_id=audit.owner_id,
                session_id=f"meeting-{audit.meeting_id}" if audit.meeting_id else None,
                name="pre-meeting-audit",
                tags=["scheduler", "audit"],
                metadata={"audit_id": audit.id},
            ):
                await refresh_verification(
                    db, audit.owner_id, await TaskRepository(db).list_tracked(audit.owner_id, meeting_id=audit.meeting_id)
                )
                preview = await build_briefing(db, user, meeting, audit.custom_instructions)
                if audit.recipient_email:
                    result.email = await send_email(
                        db,
                        owner_id=audit.owner_id,
                        recipient=audit.recipient_email,
                        subject=preview.subject,
                        html=preview.html,
                        meeting_id=audit.meeting_id,
                        audit_id=audit.id,
                    )
                if audit.post_to_slack:
                    result.slack = await (await load_connectors(db, audit.owner_id)).slack.send(briefing_message(preview))
            errors = [
                e
                for e in (
                    result.email.error if result.email else None,
                    None if not result.slack or result.slack.ok else result.slack.message,
                )
                if e
            ]
            audit.last_error = "; ".join(errors) or None
        except Exception as exc:  # a failed run must be recorded, not crash the scheduler
            logger.exception("Scheduled audit %s failed", audit_id)
            audit.last_error = f"{exc.__class__.__name__}: {exc}"[:500]
            result.error = audit.last_error
            if audit.schedule_type == ScheduleType.SINGLE:
                audit.status = ScheduleStatus.FAILED

        audit.runs_count += 1
        audit.last_run_at = datetime.now(UTC)
        if audit.status == ScheduleStatus.ACTIVE and (
            audit.schedule_type == ScheduleType.SINGLE or local_today(audit.timezone) >= audit.end_date
        ):
            audit.status = ScheduleStatus.COMPLETED
        await db.commit()
        logger.info(
            "Audit %s run #%s finished: status=%s%s",
            audit.id,
            audit.runs_count,
            audit.status,
            f", error={audit.last_error}" if audit.last_error else "",
        )
        tracing.update_span(output={"audit_id": audit.id, "status": str(audit.status), "error": audit.last_error})
        await tracing.flush()  # scheduled runs are short-lived; do not wait for the next batch
        return result, audit
