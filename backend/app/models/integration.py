from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.base import TimestampMixin


class Integration(TimestampMixin, Base):
    """A user's connection to an external tool (one per tool). Secrets are Fernet-encrypted as one JSON blob."""

    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("owner_id", "kind", name="uq_integrations_owner_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Non-secret settings (site URL, project key, channel, ...), safe to return to the client.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secrets_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean)
    last_test_message: Mapped[Optional[str]] = mapped_column(Text)
