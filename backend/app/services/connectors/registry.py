"""Which connector handles what, and with whose credentials.

Credentials are resolved per user, in order:
  1. the user's own connection (Settings -> Integrations),
  2. the server-wide default from `.env`,
  3. none: trackers run in labelled simulation mode; notifiers report "not connected".

Adding a tool = one connector class + one entry in CONNECTORS (+ TRACKER_FOR_TARGET for trackers).
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import TargetSystem
from app.models.integration import Integration
from app.models.task import Task
from app.repositories import IntegrationRepository
from app.services.connectors.base import Connector, NotifierConnector, TrackerConnector
from app.services.connectors.github import GitHubConnector
from app.services.connectors.jira import JiraConnector
from app.services.connectors.slack import SlackConnector
from app.utils.security import decrypt_secret

CONNECTORS: Dict[str, Type[Connector]] = {
    GitHubConnector.kind: GitHubConnector,
    JiraConnector.kind: JiraConnector,
    SlackConnector.kind: SlackConnector,
}
TRACKER_KINDS = [k for k, c in CONNECTORS.items() if issubclass(c, TrackerConnector)]
TRACKER_FOR_TARGET: Dict[str, str] = {
    TargetSystem.GITHUB_ISSUE: GitHubConnector.kind,
    TargetSystem.GITHUB_PR: GitHubConnector.kind,
    TargetSystem.JIRA: JiraConnector.kind,
}


def is_available(kind: str) -> bool:
    """Enabled in ENABLED_INTEGRATIONS. Unavailable tools are shown as "Coming soon" and never called."""
    return kind in settings.ENABLED_INTEGRATIONS


def server_config(kind: str) -> Dict[str, Any]:
    """Server-wide credentials from `.env` (empty when not set)."""
    if kind == "github":
        return {"token": settings.GITHUB_PERSONAL_ACCESS_TOKEN, "default_owner": settings.GITHUB_DEFAULT_OWNER}
    if kind == "jira":
        return {
            "base_url": settings.JIRA_BASE_URL,
            "email": settings.JIRA_EMAIL,
            "api_token": settings.JIRA_API_TOKEN,
            "project_key": settings.JIRA_PROJECT_KEY,
            "issue_type": settings.JIRA_ISSUE_TYPE,
        }
    if kind == "slack":
        return {"webhook_url": settings.SLACK_WEBHOOK_URL, "bot_token": settings.SLACK_BOT_TOKEN, "channel": settings.SLACK_CHANNEL}
    return {}


def secret_names(kind: str) -> List[str]:
    return [f.name for f in CONNECTORS[kind].fields if f.secret]


def user_config(integration: Integration) -> Dict[str, Any]:
    """Stored settings + decrypted secrets of a user's connection."""
    secrets = json.loads(decrypt_secret(integration.secrets_encrypted) or "{}")
    return {**(integration.config or {}), **secrets}


def build(kind: str, integration: Optional[Integration] = None) -> Connector:
    connector_class = CONNECTORS[kind]
    if not is_available(kind):
        return connector_class({}, source="none")  # coming soon: never configured, never called
    if integration is not None and integration.enabled:
        user = connector_class(user_config(integration), source="user")
        if user.is_configured():
            return user
    return connector_class(server_config(kind), source="server")


@dataclass
class ConnectorSet:
    """All connectors for one user, resolved once per request or job."""

    by_kind: Dict[str, Connector] = field(default_factory=dict)
    default_tracker: str = "github"

    def tracker_for(self, task: Task) -> TrackerConnector:
        return self.by_kind[TRACKER_FOR_TARGET.get(task.target_system, "github")]  # type: ignore[return-value]

    def tracker(self, kind: str) -> TrackerConnector:
        return self.by_kind[kind]  # type: ignore[return-value]

    @property
    def slack(self) -> NotifierConnector:
        return self.by_kind["slack"]  # type: ignore[return-value]

    def mode(self, kind: str) -> str:
        return self.by_kind[kind].mode


async def load_connectors(db: AsyncSession, owner_id: int, default_tracker: Optional[str] = None) -> ConnectorSet:
    stored = {i.kind: i for i in await IntegrationRepository(db).list_for_owner(owner_id)}
    return ConnectorSet(
        by_kind={kind: build(kind, stored.get(kind)) for kind in CONNECTORS},
        default_tracker=default_tracker if default_tracker in TRACKER_KINDS and is_available(default_tracker) else "github",
    )
