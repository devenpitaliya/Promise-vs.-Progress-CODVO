from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Bring-your-own LLM keys, Fernet-encrypted at rest.
    gemini_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    openai_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    preferred_llm_provider: Mapped[Optional[str]] = mapped_column(String(20))
    # Tracker for new tickets that name no specific system: "github" (default) or "jira".
    default_tracker: Mapped[Optional[str]] = mapped_column(String(20))

    meetings: Mapped[List["Meeting"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
