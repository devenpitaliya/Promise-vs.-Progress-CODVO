from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.enums import (
    DEFAULT_PRIORITY,
    ApprovalStatus,
    SpeechStatus,
    SyncStatus,
    TargetSystem,
    TaskStatus,
    VerificationStatus,
)
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Task(TimestampMixin, Base):
    """A spoken commitment, its review state, and what its tracker (GitHub or Jira) says about it."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False)
    # Denormalised from the meeting so every tenant-scoped query is a single indexed filter.
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)

    # Promise (from the transcript)
    assignee: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_quote: Mapped[Optional[str]] = mapped_column(Text)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    speech_status: Mapped[str] = mapped_column(String(30), default=SpeechStatus.PROPOSED, nullable=False)
    # 1 = highest, 3 = lowest.
    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY, server_default="2", index=True, nullable=False)

    # Where it should be tracked
    target_system: Mapped[str] = mapped_column(String(20), default=TargetSystem.GITHUB_ISSUE, nullable=False)
    repository: Mapped[Optional[str]] = mapped_column(String(200))
    external_ref: Mapped[Optional[str]] = mapped_column(String(100))

    # Human-in-the-loop review and self-reported progress
    approval_status: Mapped[str] = mapped_column(String(20), default=ApprovalStatus.PENDING, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.OPEN, index=True, nullable=False)

    # External sync (creating/linking the GitHub entity)
    sync_status: Mapped[str] = mapped_column(String(20), default=SyncStatus.NOT_SYNCED, nullable=False)
    sync_error: Mapped[Optional[str]] = mapped_column(Text)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    github_url: Mapped[Optional[str]] = mapped_column(String(500))
    github_issue_number: Mapped[Optional[int]] = mapped_column(Integer)
    github_pr_number: Mapped[Optional[int]] = mapped_column(Integer)
    # Key of the linked item in trackers that use keys instead of numbers (Jira: "PROJ-142").
    external_key: Mapped[Optional[str]] = mapped_column(String(50))
    # When the app itself closed the ticket: the tracker's timestamp for that close (GitHub closed_at,
    # Jira statuscategorychangedate). A later close by someone in the tracker has a different timestamp.
    app_closed_marker: Mapped[Optional[str]] = mapped_column(String(64))

    # Progress (verified against GitHub)
    verification_status: Mapped[str] = mapped_column(String(30), default=VerificationStatus.NOT_CHECKED, index=True, nullable=False)
    github_state: Mapped[Optional[str]] = mapped_column(String(30))
    verification_note: Mapped[Optional[str]] = mapped_column(Text)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Not stored: set on the instance by a two-way sync edit so the response can say what changed in the tracker.
    tracker_update = None

    meeting: Mapped["Meeting"] = relationship(back_populates="tasks", lazy="selectin")

    @property
    def meeting_title(self) -> Optional[str]:
        return self.meeting.title if self.meeting else None
