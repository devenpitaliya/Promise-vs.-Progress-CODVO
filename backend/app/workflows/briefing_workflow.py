"""Workflow: tracked commitments -> verified report -> narrative (LLM chain or rules) -> safe HTML."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.chains.briefing_chain import BriefingChain
from app.llms import get_llm_for_user
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import TaskRepository
from app.schemas.briefing import BriefingPreview
from app.services.briefing_service import deterministic_narrative, render_html
from app.services.connectors import load_connectors
from app.services.reconciliation_service import build_report
from app.utils import tracing
from app.utils.tracing import observe


@observe("briefing")
async def build_briefing(
    db: AsyncSession,
    user: User,
    meeting: Optional[Meeting] = None,
    custom_instructions: Optional[str] = None,
) -> BriefingPreview:
    session_id = f"meeting-{meeting.id}" if meeting else None
    with tracing.trace_attributes(user_id=user.id, session_id=session_id, name="briefing", tags=["briefing"]):
        return await _build_briefing(db, user, meeting, custom_instructions)


async def _build_briefing(db: AsyncSession, user: User, meeting: Optional[Meeting], custom_instructions: Optional[str]) -> BriefingPreview:
    meeting_id = meeting.id if meeting else None
    tasks = await TaskRepository(db).list_tracked(user.id, meeting_id=meeting_id)
    report = build_report(tasks, meeting_id=meeting_id, github_mode=(await load_connectors(db, user.id)).mode("github"))

    narrative = None
    llm = get_llm_for_user(user)
    if llm is not None and report.total > 0:
        narrative = await BriefingChain(llm).run(report, custom_instructions)

    if narrative:
        summary, agenda, generated_by = narrative.executive_summary, narrative.agenda, narrative.generated_by
    else:
        (summary, agenda), generated_by = deterministic_narrative(report), "rules"

    scope_title = meeting.title if meeting else "All tracked commitments"
    subject = f"Pre-meeting briefing: {scope_title} ({report.today.strftime('%d %b %Y')})"
    html = render_html(
        report,
        subject=subject,
        scope_title=scope_title,
        executive_summary=summary,
        agenda=agenda,
        generated_by=generated_by,
    )
    tracing.update_span(output={"generated_by": generated_by, "tracked": report.total, "agenda_items": len(agenda)})
    return BriefingPreview(
        subject=subject,
        executive_summary=summary,
        agenda=agenda,
        html=html,
        counts=report.counts,
        completion_rate=report.completion_rate,
        generated_by=generated_by,  # type: ignore[arg-type]
        github_mode=report.github_mode,
    )
