from datetime import date, datetime
from typing import Dict, List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.constants.limits import CUSTOM_INSTRUCTIONS_MAX_LENGTH, MAX_RECURRING_AUDIT_DAYS, TIME_OF_DAY_PATTERN
from app.enums import EmailStatus, ScheduleStatus, ScheduleType


class BriefingRequest(BaseModel):
    meeting_id: Optional[int] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=CUSTOM_INSTRUCTIONS_MAX_LENGTH)


class SendBriefingRequest(BriefingRequest):
    recipient_email: EmailStr


class BriefingPreview(BaseModel):
    subject: str
    executive_summary: str
    agenda: List[str]
    html: str
    counts: Dict[str, int]
    completion_rate: float
    generated_by: Literal["gemini", "openai", "rules"]
    github_mode: Literal["live", "simulated"]


class EmailLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_email: str
    subject: str
    status: EmailStatus
    error: Optional[str] = None
    meeting_id: Optional[int] = None
    audit_id: Optional[int] = None
    created_at: datetime


class SendBriefingResponse(BaseModel):
    email: EmailLogResponse
    preview: BriefingPreview


class ScheduleAuditRequest(BaseModel):
    # Deliver by email, to Slack, or both.
    recipient_email: Optional[EmailStr] = None
    post_to_slack: bool = False
    schedule_type: ScheduleType = ScheduleType.SINGLE
    timezone: str = "UTC"
    run_at: Optional[datetime] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    daily_time: Optional[str] = Field(default=None, pattern=TIME_OF_DAY_PATTERN)
    meeting_id: Optional[int] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=CUSTOM_INSTRUCTIONS_MAX_LENGTH)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone '{value}'") from exc
        return value

    @model_validator(mode="after")
    def _check_shape(self) -> "ScheduleAuditRequest":
        if not self.recipient_email and not self.post_to_slack:
            raise ValueError("Choose where to deliver the briefing: an email address, Slack, or both")
        if self.schedule_type == ScheduleType.SINGLE:
            if self.run_at is None:
                raise ValueError("run_at is required for a single audit")
        else:
            if not (self.start_date and self.end_date and self.daily_time):
                raise ValueError("start_date, end_date and daily_time are required for a recurring audit")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
            if (self.end_date - self.start_date).days > MAX_RECURRING_AUDIT_DAYS:
                raise ValueError("A recurring audit can span at most one year")
        return self


class ScheduledAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_email: Optional[str] = None
    post_to_slack: bool = False
    schedule_type: ScheduleType
    timezone: str
    run_at: Optional[datetime] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    daily_time: Optional[str] = None
    meeting_id: Optional[int] = None
    custom_instructions: Optional[str] = None
    status: ScheduleStatus
    runs_count: int
    last_run_at: Optional[datetime] = None
    last_error: Optional[str] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime


class AuditRunResponse(BaseModel):
    email: Optional[EmailLogResponse] = None
    slack_ok: Optional[bool] = None
    slack_message: Optional[str] = None
