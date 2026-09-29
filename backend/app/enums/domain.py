from enum import IntEnum, StrEnum


class Priority(IntEnum):
    """1 = highest. Judged from the discussion by the extraction agent; editable by people."""

    P1 = 1
    P2 = 2
    P3 = 3


DEFAULT_PRIORITY = Priority.P2


class TargetSystem(StrEnum):
    GITHUB_ISSUE = "github_issue"
    GITHUB_PR = "github_pr"
    JIRA = "jira"


class SpeechStatus(StrEnum):
    """What the speaker said about the work during the meeting."""

    PROPOSED = "PROPOSED"
    COMPLETED_IN_SPEECH = "COMPLETED_IN_SPEECH"
    BLOCKED = "BLOCKED"


class ApprovalStatus(StrEnum):
    """Human-in-the-loop review state. Nothing reaches GitHub until it is APPROVED."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TaskStatus(StrEnum):
    """Self-reported lifecycle, editable by people. Never treated as proof of delivery."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class SyncStatus(StrEnum):
    NOT_SYNCED = "NOT_SYNCED"
    SYNCED = "SYNCED"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    """What the external system (GitHub) says. The only source of 'verified done'."""

    NOT_CHECKED = "NOT_CHECKED"
    VERIFIED_DONE = "VERIFIED_DONE"
    OPEN = "OPEN"
    CLOSED_NOT_COMPLETED = "CLOSED_NOT_COMPLETED"
    # Closed by this app on the owner's say-so. Counts as a claim until the tracker confirms it independently.
    CLOSED_FROM_APP = "CLOSED_FROM_APP"
    NOT_TRACKABLE = "NOT_TRACKABLE"
    CHECK_FAILED = "CHECK_FAILED"


class Verdict(StrEnum):
    """Reconciliation outcome shown in the pre-meeting briefing."""

    VERIFIED_DONE = "VERIFIED_DONE"
    CLAIMED_UNVERIFIED = "CLAIMED_UNVERIFIED"
    OVERDUE = "OVERDUE"
    DUE_TODAY = "DUE_TODAY"
    BLOCKED = "BLOCKED"
    AT_RISK = "AT_RISK"
    ON_TRACK = "ON_TRACK"
    NO_DEADLINE = "NO_DEADLINE"
    CANCELLED = "CANCELLED"


class ScheduleType(StrEnum):
    SINGLE = "single"
    RECURRING = "recurring"


class ScheduleStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EmailStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class LLMProvider(StrEnum):
    GEMINI = "gemini"
    OPENAI = "openai"
