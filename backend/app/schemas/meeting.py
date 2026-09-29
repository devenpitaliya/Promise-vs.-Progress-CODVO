from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.config import settings
from app.constants.limits import NAME_MAX_LENGTH, TIME_OF_DAY_PATTERN, TITLE_MAX_LENGTH
from app.schemas.task import TaskResponse
from app.utils import tracing


class Participant(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    role: Optional[str] = Field(default=None, max_length=80)


class TranscriptUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    meeting_type: Optional[str] = Field(default=None, max_length=50)
    meeting_date: Optional[date] = None
    meeting_time: Optional[str] = Field(default=None, pattern=TIME_OF_DAY_PATTERN)
    participants: List[Participant] = Field(default_factory=list, max_length=settings.MAX_PARTICIPANTS)
    transcript: str = Field(min_length=1, max_length=settings.MAX_TRANSCRIPT_CHARS)


class MeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    meeting_type: Optional[str] = None
    meeting_date: date
    meeting_time: Optional[str] = None
    participants: List[Participant] = []
    transcript: str
    summary: Optional[str] = None
    extraction_source: str
    langfuse_trace_id: Optional[str] = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trace_url(self) -> Optional[str]:
        """Link to the extraction trace in Langfuse, when tracing is on."""
        return tracing.trace_url(self.langfuse_trace_id)

    created_at: datetime
    tasks: List[TaskResponse] = []


class MeetingListItem(BaseModel):
    id: int
    title: str
    meeting_type: Optional[str] = None
    meeting_date: date
    meeting_time: Optional[str] = None
    participants: List[Participant] = []
    created_at: datetime
    task_count: int
    pending_count: int
    approved_count: int
    verified_count: int


class SampleTranscript(BaseModel):
    title: str
    description: str
    meeting_type: str
    participants: List[Participant]
    transcript: str


class ConvertTranscriptRequest(BaseModel):
    # Caption files are larger than the text they contain (timestamps, cue ids), so allow more than the transcript limit.
    text: str = Field(min_length=1, max_length=settings.MAX_TRANSCRIPT_CHARS * 5)


class ConvertTranscriptResponse(BaseModel):
    transcript: str
    format: Literal["vtt", "srt", "text"]
    speakers: List[str]
    lines: int
    too_long: bool
