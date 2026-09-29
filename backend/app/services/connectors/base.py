"""Connector contracts. Workflows talk to these interfaces, never to a specific tool's API.

Trackers (GitHub, Jira) hold the tickets: create or link one per approved commitment and later
report whether it is really done. Notifiers (Slack) deliver briefings and reminders.

Each connector runs in one of two explicit modes:
- live: credentials are configured (by the user in Settings, or server-wide in `.env`).
- simulated: nothing is sent anywhere; items are flagged `is_simulated` and only change state
  through the simulation endpoint, so the UI can label them honestly.
"""

import ipaddress
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.enums import VerificationStatus
from app.models.task import Task

Mode = Literal["live", "simulated"]
Source = Literal["user", "server", "none"]


@dataclass
class SyncOutcome:
    ok: bool
    is_simulated: bool = False
    url: Optional[str] = None
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    external_key: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


@dataclass
class VerifyOutcome:
    status: VerificationStatus
    state: Optional[str]
    note: str


@dataclass
class PushOutcome:
    """Result of mirroring an in-app change to the ticket (status, title, comment)."""

    ok: bool
    message: str
    # Set when the app closed the ticket (see Task.app_closed_marker); "" when it reopened it.
    closed_marker: Optional[str] = None


@dataclass
class ConnectionTest:
    ok: bool
    message: str


@dataclass(frozen=True)
class FieldSpec:
    """One setting of a connector, rendered as a form field in Settings -> Integrations."""

    name: str
    label: str
    secret: bool = False
    required: bool = False
    placeholder: str = ""
    help: str = ""


class ConnectorConfigError(ValueError):
    """User-supplied connection settings are invalid (shown to the user as a 422)."""


def _host_allowed(host: str, suffixes: List[str]) -> bool:
    host = host.lower().rstrip(".")
    extra = [h.strip().lower() for h in settings.INTEGRATION_ALLOWED_HOSTS if h.strip()]
    return any(host == s or host.endswith("." + s) for s in suffixes + extra)


def validate_url(value: str, *, allowed_suffixes: List[str], what: str) -> str:
    """HTTPS URLs on the tool's own domains only, so user-supplied URLs cannot reach internal services."""
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ConnectorConfigError(f"{what} must be an https:// URL.")
    try:
        ipaddress.ip_address(parsed.hostname)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        raise ConnectorConfigError(f"{what} must use a host name, not an IP address.")
    if not _host_allowed(parsed.hostname, allowed_suffixes):
        allowed = ", ".join(allowed_suffixes + settings.INTEGRATION_ALLOWED_HOSTS)
        raise ConnectorConfigError(f"{what} must be on {allowed} (add self-hosted hosts to INTEGRATION_ALLOWED_HOSTS).")
    return url


class Connector(ABC):
    kind: str
    label: str
    fields: List[FieldSpec] = []

    def __init__(self, config: Optional[Dict[str, Any]] = None, source: Source = "none", http: Optional[httpx.AsyncClient] = None):
        self.config = {k: v for k, v in (config or {}).items() if v not in (None, "")}
        self.source: Source = source if self.config else "none"
        self._http = http  # injected in tests; otherwise opened by session()

    @property
    def mode(self) -> Mode:
        return "live" if self.is_configured() else "simulated"

    @abstractmethod
    def is_configured(self) -> bool:
        """True when every required credential is present."""

    @abstractmethod
    def _client(self) -> httpx.AsyncClient:
        """A client with base URL, auth and timeout for this tool."""

    @asynccontextmanager
    async def session(self) -> AsyncIterator["Connector"]:
        """Open one HTTP client for a batch of calls (no client in simulated mode)."""
        if self._http is not None or self.mode != "live":
            yield self
            return
        async with self._client() as client:
            self._http = client
            try:
                yield self
            finally:
                self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("Use `async with connector.session():` before calling the API")
        return self._http

    @abstractmethod
    async def test(self) -> ConnectionTest:
        """Make a real, harmless API call to prove the credentials and settings work."""


class TrackerConnector(Connector):
    """A ticket system: GitHub, Jira, ..."""

    @abstractmethod
    async def sync(self, task: Task) -> SyncOutcome:
        """Link the commitment to an existing ticket, or create one."""

    @abstractmethod
    async def verify(self, task: Task) -> VerifyOutcome:
        """Ask the tool whether the linked ticket is actually done."""

    async def push_update(
        self, task: Task, status_change: Optional[Tuple[str, str]], edits: Dict[str, Any], actor: str
    ) -> Optional[PushOutcome]:
        """Mirror an in-app change to the ticket. None when this tracker does not support it."""
        return None


@dataclass
class Message:
    """A notifier-neutral message: title, short text lines and an optional link."""

    title: str
    lines: List[str]
    link: Optional[str] = None
    link_label: Optional[str] = None


class NotifierConnector(Connector):
    """A place people read: Slack, Teams, ..."""

    @abstractmethod
    async def send(self, message: Message) -> ConnectionTest:
        """Deliver the message; returns whether it was accepted."""


STATUS_LABELS = {
    "OPEN": "Open",
    "IN_PROGRESS": "In progress",
    "IN_REVIEW": "In review",
    "BLOCKED": "Blocked",
    "DONE": "Done",
    "CANCELLED": "Cancelled",
}
OPEN_STATUSES = {"OPEN", "IN_PROGRESS", "IN_REVIEW", "BLOCKED"}
CLOSED_STATUSES = {"DONE", "CANCELLED"}
EDIT_LABELS = {"description": "title", "assignee": "owner", "target_date": "target date", "priority": "priority"}


def change_lines(status_change: Optional[Tuple[str, str]], edits: Dict[str, Any], actor: str) -> List[str]:
    """Human-readable audit lines for the comment posted on the ticket."""
    lines: List[str] = []
    if status_change:
        lines.append(f"{actor} changed the status to {STATUS_LABELS.get(status_change[1], status_change[1])} in Promise vs. Progress.")
        if status_change[1] == "DONE":
            lines.append("Closed from the app: this counts as claimed, not verified, until the work is confirmed here.")
    for name, value in edits.items():
        shown = (
            f"P{int(value)}" if name == "priority" and value is not None else (value.isoformat() if hasattr(value, "isoformat") else value)
        )
        lines.append(f"{actor} changed the {EDIT_LABELS.get(name, name)} to {shown if shown not in (None, '') else '(none)'}.")
    return lines


def describe_http_error(tool: str, response: httpx.Response, what: str) -> str:
    if response.status_code == 404:
        return f"{what} was not found in {tool}, or the credentials have no access to it."
    if response.status_code == 401:
        return f"{tool} rejected the credentials (HTTP 401)."
    if response.status_code == 403:
        return f"{tool} denied access to {what} (HTTP 403)."
    if response.status_code == 429:
        return f"{tool} rate limit reached; try again later."
    return f"{tool} returned HTTP {response.status_code} for {what}."
