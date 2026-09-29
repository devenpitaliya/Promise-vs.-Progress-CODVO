import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants.limits import API_KEY_PATTERN
from app.llms import resolve_credentials, test_api_key
from app.models.user import User
from app.schemas.settings import (
    AiSettingsResponse,
    PublicConfig,
    SystemStatus,
    TestAiKeyRequest,
    TestAiKeyResponse,
    UpdateAiSettingsRequest,
)
from app.services.connectors import load_connectors
from app.services.scheduler_service import scheduler_service
from app.utils import tracing
from app.utils.exceptions import InvalidRequestError, RateLimitedError
from app.utils.rate_limit import SlidingWindowLimiter
from app.utils.security import decrypt_secret, encrypt_secret, mask_secret

key_test_limiter = SlidingWindowLimiter(max_events=10, window_seconds=300)


def public_config() -> PublicConfig:
    return PublicConfig(
        app_name=settings.APP_NAME,
        demo_mode=settings.DEMO_MODE,
        password_min_length=settings.PASSWORD_MIN_LENGTH,
        max_transcript_chars=settings.MAX_TRANSCRIPT_CHARS,
        max_participants=settings.MAX_PARTICIPANTS,
    )


async def system_status(db: AsyncSession, user: User) -> SystemStatus:
    connectors = await load_connectors(db, user.id, user.default_tracker)
    return SystemStatus(
        github_mode=connectors.mode("github"),
        jira_mode=connectors.mode("jira"),
        slack_connected=connectors.slack.is_configured(),
        default_tracker=connectors.default_tracker,
        integrations_available=list(settings.ENABLED_INTEGRATIONS),
        smtp_configured=settings.smtp_configured,
        demo_mode=settings.DEMO_MODE,
        scheduler_running=scheduler_service.running,
        app_timezone=settings.APP_TIMEZONE,
        verification_interval_minutes=settings.VERIFICATION_INTERVAL_MINUTES,
        semantic_search_enabled=settings.SEMANTIC_SEARCH_ENABLED,
        tracing_enabled=tracing.is_enabled(),
        tracing_url=settings.LANGFUSE_BASE_URL if tracing.is_enabled() else None,
        tracing_off_reason=tracing.off_reason(),
    )


def _encrypted_or_none(raw: str) -> Optional[str]:
    value = raw.strip()
    if not value:
        return None
    if not re.match(API_KEY_PATTERN, value):
        raise InvalidRequestError("That does not look like a valid API key.")
    return encrypt_secret(value)


class SettingsController:
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user

    def ai_settings(self) -> AiSettingsResponse:
        credentials = resolve_credentials(self.user)
        return AiSettingsResponse(
            gemini_key_masked=mask_secret(decrypt_secret(self.user.gemini_api_key_encrypted)),
            openai_key_masked=mask_secret(decrypt_secret(self.user.openai_api_key_encrypted)),
            preferred_provider=self.user.preferred_llm_provider,
            server_gemini_available=bool(settings.GEMINI_API_KEY),
            server_openai_available=bool(settings.OPENAI_API_KEY),
            active_provider=str(credentials.provider) if credentials else "rules",
            gemini_model=settings.GEMINI_MODEL,
            openai_model=settings.OPENAI_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        )

    async def update_ai_settings(self, payload: UpdateAiSettingsRequest) -> AiSettingsResponse:
        """Keys belong to the signed-in user, are encrypted at rest and never returned in full."""
        changes = payload.model_dump(exclude_unset=True)
        if "gemini_api_key" in changes:
            self.user.gemini_api_key_encrypted = _encrypted_or_none(payload.gemini_api_key or "")
        if "openai_api_key" in changes:
            self.user.openai_api_key_encrypted = _encrypted_or_none(payload.openai_api_key or "")
        if "preferred_provider" in changes:
            self.user.preferred_llm_provider = payload.preferred_provider
        await self.db.flush()
        return self.ai_settings()

    async def test_key(self, payload: TestAiKeyRequest) -> TestAiKeyResponse:
        if not key_test_limiter.hit(str(self.user.id)):
            raise RateLimitedError("Too many key tests. Try again in a few minutes.")
        valid, message = await test_api_key(payload.provider, payload.api_key)
        return TestAiKeyResponse(valid=valid, message=message)
