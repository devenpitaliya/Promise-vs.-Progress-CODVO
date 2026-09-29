"""Email delivery with a persisted audit log and a per-user daily quota."""

import asyncio
import logging
import re
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import EmailStatus
from app.models.audit import EmailLog
from app.repositories import EmailLogRepository
from app.utils.exceptions import RateLimitedError

logger = logging.getLogger(__name__)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</(p|tr|li|div|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _send_smtp(recipient: str, subject: str, html: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = recipient
    message.set_content(_html_to_text(html))
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as server:
        if settings.SMTP_STARTTLS:
            server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)


async def send_email(
    db: AsyncSession,
    *,
    owner_id: int,
    recipient: str,
    subject: str,
    html: str,
    meeting_id: Optional[int] = None,
    audit_id: Optional[int] = None,
) -> EmailLog:
    """Send (or record why we could not send) and persist the attempt."""
    logs = EmailLogRepository(db)
    if await logs.count_since(owner_id, datetime.now(UTC) - timedelta(days=1)) >= settings.EMAILS_PER_USER_PER_DAY:
        raise RateLimitedError(f"Daily limit of {settings.EMAILS_PER_USER_PER_DAY} briefing emails reached.")

    log = EmailLog(
        owner_id=owner_id,
        recipient_email=recipient,
        subject=re.sub(r"[\r\n]+", " ", subject).strip()[:255],  # no header injection
        html_body=html,
        meeting_id=meeting_id,
        audit_id=audit_id,
    )

    if not settings.smtp_configured:
        log.status = EmailStatus.NOT_CONFIGURED
        log.error = "SMTP is not configured on the server; the briefing was saved but not delivered."
    else:
        try:
            await asyncio.to_thread(_send_smtp, recipient, log.subject, html)
            log.status = EmailStatus.SENT
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP delivery for user %s failed: %s", owner_id, exc.__class__.__name__)
            log.status = EmailStatus.FAILED
            log.error = f"SMTP delivery failed: {exc.__class__.__name__}"

    logger.info("Briefing email for user %s: status=%s (log %s)", owner_id, log.status, "audit " + str(audit_id) if audit_id else "manual")
    return await logs.add(log)
