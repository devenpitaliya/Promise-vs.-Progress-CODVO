"""Promise vs. progress: the single source of truth for evaluating commitments.

Everything here is pure (no I/O, no mutation), so read endpoints can never change data.
GitHub verification, which does write, lives in app/workflows/reconciliation_workflow.py.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, Optional, Sequence
from zoneinfo import ZoneInfo

from app.config import settings
from app.enums import SpeechStatus, TaskStatus, Verdict, VerificationStatus
from app.models.task import Task
from app.schemas.reconciliation import ReconciliationItem, ReconciliationReport

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def local_today(tz_name: Optional[str] = None) -> date:
    return datetime.now(ZoneInfo(tz_name or settings.APP_TIMEZONE)).date()


@dataclass(frozen=True)
class Evaluation:
    verdict: Verdict
    days_overdue: Optional[int]
    days_remaining: Optional[int]
    risk_score: int
    risk_level: RiskLevel
    risk_reason: str
    note: str


def _level(score: int) -> RiskLevel:
    if score >= 85:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def evaluate(task: Task, today: date) -> Evaluation:
    """Classify one commitment. Heuristic risk scores always come with the reason behind them."""
    days_overdue = days_remaining = None
    if task.target_date:
        delta = (today - task.target_date).days
        days_overdue = delta if delta > 0 else None
        days_remaining = -delta if delta <= 0 else None

    verification = VerificationStatus(task.verification_status)
    check_note = f" Last GitHub check failed: {task.verification_note}" if verification == VerificationStatus.CHECK_FAILED else ""

    def result(verdict: Verdict, score: int, reason: str, note: str) -> Evaluation:
        return Evaluation(verdict, days_overdue, days_remaining, score, _level(score), reason, note + check_note)

    if task.status == TaskStatus.CANCELLED:
        return result(Verdict.CANCELLED, 0, "Cancelled.", "Commitment was cancelled.")

    if verification == VerificationStatus.VERIFIED_DONE:
        return result(Verdict.VERIFIED_DONE, 0, "Verified in GitHub.", task.verification_note or "Verified in GitHub.")

    claims_done = task.status == TaskStatus.DONE or task.speech_status == SpeechStatus.COMPLETED_IN_SPEECH
    if verification == VerificationStatus.CLOSED_FROM_APP:
        return result(
            Verdict.CLAIMED_UNVERIFIED,
            40,
            "Closed from this app, not in GitHub, so it is still only a claim.",
            task.verification_note or "Ask for the PR or proof, then close it in GitHub to verify it.",
        )
    if claims_done:
        if verification == VerificationStatus.CLOSED_NOT_COMPLETED:
            return result(
                Verdict.CLAIMED_UNVERIFIED,
                80,
                "Reported done, but the GitHub item was closed without being completed.",
                task.verification_note or "GitHub contradicts the reported status.",
            )
        return result(
            Verdict.CLAIMED_UNVERIFIED,
            45,
            "Reported done, but GitHub has not confirmed it yet.",
            "Ask for the PR or issue that proves delivery, or run reconciliation.",
        )

    if verification == VerificationStatus.CLOSED_NOT_COMPLETED:
        return result(
            Verdict.AT_RISK,
            80,
            "The linked GitHub item was closed without being completed.",
            task.verification_note or "Linked item closed without completion.",
        )

    if task.status == TaskStatus.BLOCKED or task.speech_status == SpeechStatus.BLOCKED:
        score = 95 if days_overdue else 85
        return result(Verdict.BLOCKED, score, "Owner reported a blocker.", "Blocked: needs a decision or unblocking owner.")

    if task.target_date is None:
        return result(
            Verdict.NO_DEADLINE,
            30,
            "No target date was committed, so slippage cannot be measured.",
            "Agree a target date in the meeting.",
        )

    if days_overdue:
        score = min(98, 70 + 5 * days_overdue)
        plural = "s" if days_overdue > 1 else ""
        return result(
            Verdict.OVERDUE,
            score,
            f"Past its target date by {days_overdue} day{plural} and not verified done.",
            f"Was due {task.target_date.isoformat()}; {days_overdue} day{plural} overdue.",
        )

    if days_remaining == 0:
        return result(Verdict.DUE_TODAY, 65, "Due today and not verified done.", "Due today.")

    if days_remaining is not None and days_remaining <= settings.AT_RISK_WINDOW_DAYS and task.status == TaskStatus.OPEN:
        return result(
            Verdict.AT_RISK,
            50,
            f"Due in {days_remaining} day(s) and no progress has been reported.",
            f"Due {task.target_date.isoformat()}; still marked open.",
        )

    return result(
        Verdict.ON_TRACK,
        15,
        f"{days_remaining} day(s) of runway left.",
        f"Due {task.target_date.isoformat()}.",
    )


def to_item(task: Task, evaluation: Evaluation) -> ReconciliationItem:
    return ReconciliationItem(
        task_id=task.id,
        meeting_id=task.meeting_id,
        meeting_title=task.meeting_title,
        assignee=task.assignee,
        description=task.description,
        repository=task.repository,
        external_ref=task.external_ref,
        external_key=task.external_key,
        target_system=task.target_system,
        github_url=task.github_url,
        is_simulated=task.is_simulated,
        sync_status=task.sync_status,
        sync_error=task.sync_error,
        target_date=task.target_date,
        priority=task.priority,
        status=task.status,
        verification_status=task.verification_status,
        github_state=task.github_state,
        last_checked_at=task.last_checked_at,
        verdict=evaluation.verdict,
        days_overdue=evaluation.days_overdue,
        days_remaining=evaluation.days_remaining,
        risk_score=evaluation.risk_score,
        risk_level=evaluation.risk_level,
        risk_reason=evaluation.risk_reason,
        note=evaluation.note,
    )


def build_report(
    tasks: Sequence[Task], meeting_id: Optional[int] = None, today: Optional[date] = None, github_mode: Optional[str] = None
) -> ReconciliationReport:
    today = today or local_today()
    items = [to_item(t, evaluate(t, today)) for t in tasks]
    items.sort(key=lambda i: (-i.risk_score, i.priority, i.target_date or date.max, i.task_id))
    counts = Counter(str(i.verdict) for i in items)
    active = [i for i in items if i.verdict != Verdict.CANCELLED]
    verified = sum(1 for i in active if i.verdict == Verdict.VERIFIED_DONE)
    return ReconciliationReport(
        generated_at=datetime.now(UTC),
        today=today,
        timezone=settings.APP_TIMEZONE,
        github_mode=github_mode or settings.github_mode,
        meeting_id=meeting_id,
        total=len(items),
        counts={str(v): counts.get(str(v), 0) for v in Verdict},
        completion_rate=round(verified / len(active) * 100, 1) if active else 0.0,
        items=items,
    )
