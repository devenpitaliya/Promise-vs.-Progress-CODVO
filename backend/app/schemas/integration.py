from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# One line of printable text: settings are never allowed to smuggle newlines or control characters.
_SAFE_VALUE = r"^[^\x00-\x1f\x7f]*$"


class IntegrationField(BaseModel):
    name: str
    label: str
    secret: bool
    required: bool
    placeholder: str = ""
    help: str = ""


class IntegrationStatus(BaseModel):
    kind: str
    label: str
    category: Literal["tracker", "notifier"]
    # False = not enabled on this server yet (ENABLED_INTEGRATIONS); shown as "Coming soon".
    available: bool = True
    fields: List[IntegrationField]
    # "user": your own connection is active; "server": the server-wide default from .env is used;
    # "none": nothing configured (trackers run in labelled simulation mode).
    source: Literal["user", "server", "none"]
    mode: Literal["live", "simulated"]
    has_user_connection: bool
    # Your saved non-secret settings, and your saved secrets masked (never returned in full).
    config: Dict[str, str] = {}
    secrets_masked: Dict[str, Optional[str]] = {}
    last_tested_at: Optional[datetime] = None
    last_test_ok: Optional[bool] = None
    last_test_message: Optional[str] = None


class IntegrationsResponse(BaseModel):
    integrations: List[IntegrationStatus]
    default_tracker: Literal["github", "jira"]


class SaveIntegrationRequest(BaseModel):
    """Field values by name. A secret left empty keeps the saved one; an empty setting clears it."""

    values: Dict[str, str] = Field(default_factory=dict, max_length=20)

    @field_validator("values")
    @classmethod
    def _check_values(cls, values: Dict[str, str]) -> Dict[str, str]:
        import re

        for name, value in values.items():
            if len(name) > 40 or len(value) > 500 or not re.match(_SAFE_VALUE, value):
                raise ValueError(f"Invalid value for {name}")
        return {k: v.strip() for k, v in values.items()}


class TestIntegrationResponse(BaseModel):
    ok: bool
    message: str
    tested_at: datetime


class DefaultTrackerRequest(BaseModel):
    default_tracker: Literal["github", "jira"]


class SlackPostRequest(BaseModel):
    meeting_id: Optional[int] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=1000)


class SlackPostResponse(BaseModel):
    ok: bool
    message: str
