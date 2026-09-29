from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.enums import EmailStatus, ScheduleStatus, ScheduleType
from app.models.base import TimestampMixin


class ScheduledAudit(TimestampMixin, Base):
    """A persisted pre-meeting audit schedule. APScheduler jobs are rebuilt from these rows on startup."""

    __tablename__ = "scheduled_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    meeting_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    # Where the briefing goes: email, Slack, or both (at least one).
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255))
    post_to_slack: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), default=ScheduleType.SINGLE, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    daily_time: Mapped[Optional[str]] = mapped_column(String(5))
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ScheduleStatus.ACTIVE, index=True, nullable=False)
    runs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[Optional[str]] = mapped_column(Text)


class EmailLog(TimestampMixin, Base):
    """Audit trail of every briefing email the engine attempted to send."""

    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    audit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scheduled_audits.id", ondelete="SET NULL"))
    meeting_id: Mapped[Optional[int]] = mapped_column(ForeignKey("meetings.id", ondelete="SET NULL"))
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    html_body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=EmailStatus.SENT, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
