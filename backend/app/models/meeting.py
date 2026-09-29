from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.task import Task
    from app.models.user import User


class Meeting(TimestampMixin, Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_type: Mapped[Optional[str]] = mapped_column(String(50))
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    meeting_time: Mapped[Optional[str]] = mapped_column(String(5))  # HH:MM
    participants: Mapped[List[dict]] = mapped_column(JSON, default=list, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # Which engine produced the commitments: "gemini", "openai" or "rules".
    extraction_source: Mapped[str] = mapped_column(String(20), default="rules", nullable=False)
    # Quality monitoring: which model and prompt version produced the commitments, and how long it took.
    # Langfuse trace of the extraction; review outcomes are attached to it as scores.
    langfuse_trace_id: Mapped[Optional[str]] = mapped_column(String(64))

    owner: Mapped["User"] = relationship(back_populates="meetings")
    tasks: Mapped[List["Task"]] = relationship(back_populates="meeting", cascade="all, delete-orphan", lazy="selectin", order_by="Task.id")
