import re
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants.limits import (
    DESCRIPTION_MAX_LENGTH,
    MAX_REVIEW_BATCH,
    NAME_MAX_LENGTH,
    QUOTE_MAX_LENGTH,
    REFERENCE_MAX_LENGTH,
    REPOSITORY_MAX_LENGTH,
    REPOSITORY_PATTERN,
)
from app.enums import DEFAULT_PRIORITY, ApprovalStatus, Priority, SpeechStatus, SyncStatus, TargetSystem, TaskStatus, VerificationStatus


def _lenient_date(value):
    """LLMs sometimes return 'next Friday' or ''. Anything that is not an ISO date becomes None."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


_PRIORITY_WORDS = {"p1": 1, "high": 1, "critical": 1, "urgent": 1, "p2": 2, "medium": 2, "normal": 2, "p3": 3, "low": 3}


def _lenient_priority(value):
    """Accept 1/2/3, "P1".."P3" or high/medium/low; anything else falls back to the default (P2)."""
    if isinstance(value, bool) or value in (None, ""):
        return DEFAULT_PRIORITY
    if isinstance(value, int | float) and int(value) in (1, 2, 3):
        return int(value)
    return _PRIORITY_WORDS.get(str(value).strip().lower(), DEFAULT_PRIORITY)


class ExtractedCommitment(BaseModel):
    """One commitment as produced by an extraction engine (LLM or rules)."""

    assignee: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    source_quote: Optional[str] = Field(default=None, max_length=QUOTE_MAX_LENGTH)
    target_date: Optional[date] = None
    target_system: TargetSystem = TargetSystem.GITHUB_ISSUE
    repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH)
    external_ref: Optional[str] = Field(default=None, max_length=REFERENCE_MAX_LENGTH)
    speech_status: SpeechStatus = SpeechStatus.PROPOSED
    priority: Priority = DEFAULT_PRIORITY

    _parse_date = field_validator("target_date", mode="before")(_lenient_date)
    _parse_priority = field_validator("priority", mode="before")(_lenient_priority)

    @field_validator("repository", mode="before")
    @classmethod
    def _clean_repo(cls, value):
        if not value:
            return None
        value = str(value).strip().strip("/")
        return value if re.match(REPOSITORY_PATTERN, value) else None


class ExtractionResult(BaseModel):
    summary: str = ""
    commitments: List[ExtractedCommitment] = []


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: int
    meeting_title: Optional[str] = None
    assignee: str
    description: str
    source_quote: Optional[str] = None
    target_date: Optional[date] = None
    speech_status: SpeechStatus
    priority: Priority
    target_system: TargetSystem
    repository: Optional[str] = None
    external_ref: Optional[str] = None
    approval_status: ApprovalStatus
    status: TaskStatus
    sync_status: SyncStatus
    sync_error: Optional[str] = None
    is_simulated: bool
    github_url: Optional[str] = None
    github_issue_number: Optional[int] = None
    github_pr_number: Optional[int] = None
    external_key: Optional[str] = None
    # What happened in the tracker after an edit (two-way sync); only present in the response to that edit.
    tracker_update: Optional[str] = None
    verification_status: VerificationStatus
    github_state: Optional[str] = None
    verification_note: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    """A commitment the reviewer adds by hand because extraction missed it."""

    meeting_id: int
    assignee: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: str = Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    target_date: Optional[date] = None
    priority: Priority = DEFAULT_PRIORITY
    target_system: TargetSystem = TargetSystem.GITHUB_ISSUE
    repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH, pattern=REPOSITORY_PATTERN)
    external_ref: Optional[str] = Field(default=None, max_length=REFERENCE_MAX_LENGTH)


class TaskUpdate(BaseModel):
    assignee: Optional[str] = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
    target_date: Optional[date] = None
    priority: Optional[Priority] = None
    target_system: Optional[TargetSystem] = None
    repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH, pattern=REPOSITORY_PATTERN)
    external_ref: Optional[str] = Field(default=None, max_length=REFERENCE_MAX_LENGTH)
    status: Optional[TaskStatus] = None


class ReviewRequest(BaseModel):
    """Human-in-the-loop decision for one meeting: exactly these IDs are approved or rejected."""

    approve_ids: List[int] = Field(default_factory=list, max_length=MAX_REVIEW_BATCH)
    reject_ids: List[int] = Field(default_factory=list, max_length=MAX_REVIEW_BATCH)
    default_repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH, pattern=REPOSITORY_PATTERN)


class ReviewFailure(BaseModel):
    task_id: int
    error: str


class ReviewResult(BaseModel):
    approved: List[TaskResponse]
    rejected_ids: List[int]
    sync_failures: List[ReviewFailure]


class SimulateStateRequest(BaseModel):
    state: Literal["open", "merged", "closed", "closed_not_planned"]


class SearchHit(BaseModel):
    score: float
    task: TaskResponse


class SearchResponse(BaseModel):
    available: bool
    results: List[SearchHit]


class SimulatedSyncResult(BaseModel):
    """Result of moving simulated commitments to a now-connected GitHub or Jira."""

    moved: int
    failures: List[ReviewFailure]


class RetryFailedRequest(BaseModel):
    """Retry every approved commitment whose ticket could not be created or linked."""

    meeting_id: Optional[int] = None
    # Applied to every failed GitHub commitment ("repo" uses the default owner, or "owner/repo").
    repository: Optional[str] = Field(default=None, max_length=REPOSITORY_MAX_LENGTH, pattern=REPOSITORY_PATTERN)
    # Create new issues instead of linking referenced issues/PRs (for numbers that do not exist in this repository).
    create_missing: bool = False


class RetryFailedResult(BaseModel):
    retried: int
    synced: int
    failures: List[ReviewFailure]
