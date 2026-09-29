from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.constants.limits import API_KEY_PATTERN
from app.enums import LLMProvider


class PublicConfig(BaseModel):
    """Unauthenticated settings the web app needs before sign-in (no secrets)."""

    app_name: str
    demo_mode: bool
    password_min_length: int
    max_transcript_chars: int
    max_participants: int


class AiSettingsResponse(BaseModel):
    gemini_key_masked: Optional[str] = None
    openai_key_masked: Optional[str] = None
    preferred_provider: Optional[LLMProvider] = None
    server_gemini_available: bool
    server_openai_available: bool
    active_provider: Literal["gemini", "openai", "rules"]
    gemini_model: str
    openai_model: str
    temperature: float


class UpdateAiSettingsRequest(BaseModel):
    """Omitted fields are left unchanged; an empty string removes the stored key."""

    gemini_api_key: Optional[str] = Field(default=None, max_length=256)
    openai_api_key: Optional[str] = Field(default=None, max_length=256)
    preferred_provider: Optional[LLMProvider] = None


class TestAiKeyRequest(BaseModel):
    provider: LLMProvider
    api_key: str = Field(pattern=API_KEY_PATTERN)


class TestAiKeyResponse(BaseModel):
    valid: bool
    message: str


class SystemStatus(BaseModel):
    github_mode: Literal["live", "simulated"]
    jira_mode: Literal["live", "simulated"] = "simulated"
    slack_connected: bool = False
    default_tracker: Literal["github", "jira"] = "github"
    # Tools enabled on this server; the rest are shown as "Coming soon".
    integrations_available: List[str] = []
    smtp_configured: bool
    demo_mode: bool
    scheduler_running: bool
    app_timezone: str
    verification_interval_minutes: int
    semantic_search_enabled: bool
    # Langfuse: whether traces are being sent, where, and why not when off.
    tracing_enabled: bool = False
    tracing_url: Optional[str] = None
    tracing_off_reason: Optional[str] = None
