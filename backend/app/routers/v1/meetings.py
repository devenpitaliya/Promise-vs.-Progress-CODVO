from typing import List

from fastapi import APIRouter, status

from app.dependencies.controllers import MeetingCtl
from app.models.meeting import Meeting
from app.schemas.meeting import (
    ConvertTranscriptRequest,
    ConvertTranscriptResponse,
    MeetingListItem,
    MeetingResponse,
    Participant,
    SampleTranscript,
    TranscriptUploadRequest,
)

router = APIRouter(prefix="/meetings", tags=["Meetings"])


@router.get("/samples", response_model=List[SampleTranscript])
async def list_samples(controller: MeetingCtl) -> List[SampleTranscript]:
    return controller.samples()


@router.get("/participants", response_model=List[Participant])
async def recent_participants(controller: MeetingCtl) -> List[Participant]:
    """People from this user's previous meetings, for quick selection in the next one."""
    return await controller.recent_participants()


@router.post("/transcript/convert", response_model=ConvertTranscriptResponse)
async def convert_transcript_file(payload: ConvertTranscriptRequest, controller: MeetingCtl) -> ConvertTranscriptResponse:
    """Turn a Teams/Zoom .vtt or .srt caption file into "Name: text" lines (nothing is saved)."""
    return controller.convert(payload)


@router.post("/", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(payload: TranscriptUploadRequest, controller: MeetingCtl) -> Meeting:
    """Store a transcript and extract commitments for human review. Nothing is synced yet."""
    return await controller.create(payload)


@router.get("/", response_model=List[MeetingListItem])
async def list_meetings(controller: MeetingCtl) -> List[MeetingListItem]:
    return await controller.list()


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(meeting_id: int, controller: MeetingCtl) -> Meeting:
    return await controller.get_owned(meeting_id)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: int, controller: MeetingCtl) -> None:
    await controller.delete(meeting_id)
