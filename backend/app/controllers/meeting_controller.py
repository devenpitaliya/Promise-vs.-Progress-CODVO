from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants.sample_transcripts import sample_transcripts
from app.enums import ApprovalStatus, VerificationStatus
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import MeetingRepository
from app.schemas.meeting import (
    ConvertTranscriptRequest,
    ConvertTranscriptResponse,
    MeetingListItem,
    Participant,
    SampleTranscript,
    TranscriptUploadRequest,
)
from app.services.vector_store_service import vector_store
from app.tools.transcript_converter import convert_transcript
from app.utils.exceptions import NotFoundError
from app.workflows.meeting_ingestion_workflow import ingest_meeting


class MeetingController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.meetings = MeetingRepository(db)

    async def get_owned(self, meeting_id: int) -> Meeting:
        """404 (not 403) for other users' meetings, so IDs cannot be probed."""
        meeting = await self.meetings.get_owned(self.user.id, meeting_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        return meeting

    @staticmethod
    def samples() -> List[SampleTranscript]:
        return sample_transcripts()

    async def recent_participants(self) -> List[Participant]:
        seen: Dict[str, Participant] = {}
        for participants in await self.meetings.recent_participant_lists(self.user.id):
            for raw in participants:
                person = Participant.model_validate(raw)
                seen.setdefault(person.name.lower(), person)
        return sorted(seen.values(), key=lambda p: p.name.lower())

    @staticmethod
    def convert(payload: ConvertTranscriptRequest) -> ConvertTranscriptResponse:
        """Caption file (Teams/Zoom .vtt, .srt) -> "Name: text" lines, for preview before saving."""
        result = convert_transcript(payload.text)
        return ConvertTranscriptResponse(
            transcript=result.text,
            format=result.format,
            speakers=result.speakers,
            lines=result.lines,
            too_long=len(result.text) > settings.MAX_TRANSCRIPT_CHARS,
        )

    async def create(self, payload: TranscriptUploadRequest) -> Meeting:
        return (await ingest_meeting(self.db, self.user, payload)).meeting

    async def list(self) -> List[MeetingListItem]:
        items = []
        for meeting in await self.meetings.list_for_owner(self.user.id):
            tasks = [t for t in meeting.tasks if t.approval_status != ApprovalStatus.REJECTED]
            items.append(
                MeetingListItem(
                    id=meeting.id,
                    title=meeting.title,
                    meeting_type=meeting.meeting_type,
                    meeting_date=meeting.meeting_date,
                    meeting_time=meeting.meeting_time,
                    participants=meeting.participants or [],
                    created_at=meeting.created_at,
                    task_count=len(tasks),
                    pending_count=sum(t.approval_status == ApprovalStatus.PENDING for t in tasks),
                    approved_count=sum(t.approval_status == ApprovalStatus.APPROVED for t in tasks),
                    verified_count=sum(t.verification_status == VerificationStatus.VERIFIED_DONE for t in tasks),
                )
            )
        return items

    async def delete(self, meeting_id: int) -> None:
        meeting = await self.get_owned(meeting_id)
        task_ids = [t.id for t in meeting.tasks]
        await self.meetings.delete(meeting)
        await vector_store.delete_tasks(task_ids)
