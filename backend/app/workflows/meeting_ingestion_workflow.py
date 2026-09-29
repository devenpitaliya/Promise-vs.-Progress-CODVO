"""Workflow: transcript -> extraction agent -> persisted meeting + pending commitments -> search index.

Nothing is synced to GitHub here; commitments wait for human review.
"""

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.commitment_extraction_agent import CommitmentExtractionAgent
from app.chains.extraction_chain import MeetingContext
from app.enums import TargetSystem
from app.llms import get_llm_for_user
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.user import User
from app.repositories import MeetingRepository, TaskRepository
from app.schemas.meeting import TranscriptUploadRequest
from app.services.connectors import is_available
from app.services.connectors.jira import parse_issue_key
from app.services.reconciliation_service import local_today
from app.services.vector_store_service import vector_store
from app.tools.transcript_converter import convert_transcript
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)


def route_to_tracker(item, default_tracker: Optional[str]) -> None:
    """A mentioned Jira key always means Jira; brand-new tickets follow the user's default tracker.

    While Jira is not enabled (ENABLED_INTEGRATIONS), everything is tracked as a GitHub issue.
    """
    if not is_available("jira"):
        if item.target_system == TargetSystem.JIRA:
            item.target_system = TargetSystem.GITHUB_ISSUE
        return
    if parse_issue_key(item.external_ref) and item.target_system != TargetSystem.GITHUB_PR:
        item.target_system = TargetSystem.JIRA
    elif default_tracker == "jira" and item.target_system == TargetSystem.GITHUB_ISSUE and not item.external_ref:
        item.target_system = TargetSystem.JIRA


@dataclass
class IngestionResult:
    meeting: Meeting
    trace: List[str]


@observe("meeting-ingestion", as_type="chain")
async def ingest_meeting(db: AsyncSession, user: User, payload: TranscriptUploadRequest) -> IngestionResult:
    with tracing.trace_attributes(
        user_id=user.id,
        name="meeting-ingestion",
        tags=["extraction", payload.meeting_type or "meeting"],
        metadata={"transcript_chars": len(payload.transcript), "participants": len(payload.participants)},
    ):
        return await _ingest_meeting(db, user, payload)


async def _ingest_meeting(db: AsyncSession, user: User, payload: TranscriptUploadRequest) -> IngestionResult:
    # Raw Teams/Zoom captions pasted or sent via the API become "Name: text" lines; plain text is unchanged.
    transcript = convert_transcript(payload.transcript).text
    meeting_date = payload.meeting_date or local_today()
    context = MeetingContext(
        transcript=transcript,
        title=payload.title,
        meeting_type=payload.meeting_type,
        meeting_date=meeting_date,
        participants=payload.participants,
    )
    started = time.perf_counter()
    outcome = await CommitmentExtractionAgent(get_llm_for_user(user)).run(context)
    latency_ms = int((time.perf_counter() - started) * 1000)
    trace_id = tracing.current_trace_id()
    logger.info(
        "Extraction for user %s via %s in %sms%s: %s",
        user.id,
        outcome.source,
        latency_ms,
        f" (trace {trace_id})" if trace_id else "",
        " | ".join(outcome.trace),
    )

    meeting = await MeetingRepository(db).add(
        Meeting(
            owner_id=user.id,
            title=payload.title.strip(),
            meeting_type=payload.meeting_type,
            meeting_date=meeting_date,
            meeting_time=payload.meeting_time,
            participants=[p.model_dump() for p in payload.participants],
            transcript=transcript,
            summary=outcome.result.summary,
            extraction_source=outcome.source,
            langfuse_trace_id=trace_id,
        )
    )
    for item in outcome.result.commitments:
        route_to_tracker(item, user.default_tracker)
    tasks = await TaskRepository(db).add_all(
        Task(
            meeting_id=meeting.id,
            owner_id=user.id,
            assignee=item.assignee,
            description=item.description,
            source_quote=item.source_quote,
            target_date=item.target_date,
            speech_status=item.speech_status,
            priority=item.priority,
            target_system=item.target_system,
            repository=item.repository,
            external_ref=item.external_ref,
        )
        for item in outcome.result.commitments
    )
    await vector_store.index_tasks(tasks)
    await db.refresh(meeting, attribute_names=["tasks"])
    tracing.update_span(
        output={"meeting_id": meeting.id, "commitments": len(tasks), "source": outcome.source},
        metadata={"meeting_id": meeting.id, "latency_ms": latency_ms},
    )
    return IngestionResult(meeting=meeting, trace=outcome.trace)
