from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.enums import Priority, TaskStatus, Verdict, VerificationStatus


class ReconcileRequest(BaseModel):
    meeting_id: Optional[int] = None
    task_ids: Optional[List[int]] = Field(default=None, max_length=500)


class ReconciliationItem(BaseModel):
    task_id: int
    meeting_id: int
    meeting_title: Optional[str] = None
    assignee: str
    description: str
    repository: Optional[str] = None
    external_ref: Optional[str] = None
    # Jira key such as PROJ-142 (None for GitHub, which uses numbers).
    external_key: Optional[str] = None
    target_system: str = "github_issue"
    github_url: Optional[str] = None
    is_simulated: bool
    sync_status: str = "SYNCED"
    sync_error: Optional[str] = None
    target_date: Optional[date] = None
    priority: Priority
    status: TaskStatus
    verification_status: VerificationStatus
    github_state: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    verdict: Verdict
    days_overdue: Optional[int] = None
    days_remaining: Optional[int] = None
    # Heuristic, explainable score (0-100); `risk_reason` states exactly why.
    risk_score: int
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    risk_reason: str
    note: str


class ReconciliationReport(BaseModel):
    generated_at: datetime
    today: date
    timezone: str
    github_mode: Literal["live", "simulated"]
    meeting_id: Optional[int] = None
    total: int
    counts: Dict[str, int]
    completion_rate: float
    items: List[ReconciliationItem]
