"""Jira Cloud tracker (REST API v3): create or link issues, and verify them by status category.

"Done" in Jira is the status *category*, so custom workflows ("Released", "Closed", "Shipped") work
without configuration. A done issue with a resolution such as "Won't Do" counts as closed, not delivered.
"""

import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.enums import VerificationStatus
from app.models.task import Task
from app.services.connectors.base import (
    ConnectionTest,
    ConnectorConfigError,
    FieldSpec,
    SyncOutcome,
    TrackerConnector,
    VerifyOutcome,
    describe_http_error,
    validate_url,
)
from app.services.connectors.github import verify_simulated
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

ISSUE_KEY = re.compile(r"\b([A-Z][A-Z0-9_]{1,9}-\d+)\b")
PROJECT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
# Resolutions that close an issue without delivering it.
NOT_DELIVERED = {"won't do", "won't fix", "duplicate", "cannot reproduce", "declined", "rejected", "abandoned"}
PRIORITY_NAMES = {1: "High", 2: "Medium", 3: "Low"}
JIRA_CLOUD_HOSTS = ["atlassian.net"]


def parse_issue_key(external_ref: Optional[str]) -> Optional[str]:
    match = ISSUE_KEY.search(external_ref or "")
    return match.group(1) if match else None


def _adf(*paragraphs: str) -> Dict[str, Any]:
    """Jira v3 descriptions use the Atlassian Document Format."""
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs if p],
    }


def _state(fields: Dict[str, Any]) -> tuple[str, str]:
    """(normalised state, human status) from an issue's status and resolution."""
    status = fields.get("status") or {}
    name = status.get("name") or "Unknown"
    if (status.get("statusCategory") or {}).get("key") != "done":
        return "open", name
    resolution = ((fields.get("resolution") or {}).get("name") or "").lower()
    return ("closed_not_planned" if resolution in NOT_DELIVERED else "closed"), name


class JiraConnector(TrackerConnector):
    kind = "jira"
    label = "Jira"
    fields = [
        FieldSpec("base_url", "Site URL", required=True, placeholder="https://your-team.atlassian.net"),
        FieldSpec(
            "email", "Account email", required=True, placeholder="you@company.com", help="The Atlassian account that owns the API token."
        ),
        FieldSpec(
            "api_token",
            "API token",
            secret=True,
            required=True,
            placeholder="ATATT...",
            help="Create one at id.atlassian.com > Security > API tokens.",
        ),
        FieldSpec(
            "project_key",
            "Default project key",
            required=True,
            placeholder="PROJ",
            help="New issues go here unless a commitment names another project.",
        ),
        FieldSpec("issue_type", "Issue type", placeholder="Task", help="Issue type for new issues (default Task)."),
    ]

    @staticmethod
    def validate(config: Dict[str, Any]) -> Dict[str, Any]:
        if config.get("base_url"):
            config["base_url"] = validate_url(config["base_url"], allowed_suffixes=JIRA_CLOUD_HOSTS, what="Jira site URL")
        if config.get("project_key"):
            config["project_key"] = config["project_key"].strip().upper()
            if not PROJECT_KEY.match(config["project_key"]):
                raise ConnectorConfigError("Project key must look like PROJ (capital letters and digits).")
        return config

    def is_configured(self) -> bool:
        return all(self.config.get(k) for k in ("base_url", "email", "api_token", "project_key"))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config["base_url"],
            auth=(self.config["email"], self.config["api_token"]),
            headers={"Accept": "application/json"},
            timeout=settings.JIRA_TIMEOUT_SECONDS,
        )

    def browse_url(self, key: str) -> Optional[str]:
        base = self.config.get("base_url")
        return f"{base}/browse/{key}" if base else None

    def _project_for(self, task: Task) -> str:
        override = (task.repository or "").strip().upper()
        return override if PROJECT_KEY.match(override) else self.config.get("project_key", "SIM")

    async def test(self) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(False, "Fill in the site URL, email, API token and project key first.")
        project = self.config["project_key"]
        try:
            async with self.session():
                me = await self.http.get("/rest/api/3/myself")
                if me.status_code != 200:
                    return ConnectionTest(False, describe_http_error("Jira", me, "your account"))
                proj = await self.http.get(f"/rest/api/3/project/{project}")
        except httpx.HTTPError as exc:
            return ConnectionTest(False, f"Could not reach Jira ({exc.__class__.__name__}).")
        if proj.status_code != 200:
            return ConnectionTest(False, describe_http_error("Jira", proj, f"project {project}"))
        who = me.json().get("displayName") or "your account"
        return ConnectionTest(True, f"Connected as {who}; project {project} ({proj.json().get('name', project)}) is reachable.")

    async def _get_issue(self, key: str) -> httpx.Response:
        return await self.http.get(f"/rest/api/3/issue/{key}", params={"fields": "status,resolution,summary"})

    async def _create(self, task: Task) -> httpx.Response:
        fields: Dict[str, Any] = {
            "project": {"key": self._project_for(task)},
            "summary": task.description[:250],
            "issuetype": {"name": self.config.get("issue_type") or "Task"},
            "description": _adf(
                f"Committed by: {task.assignee}",
                f"Quote: “{task.source_quote}”" if task.source_quote else "",
                f"Priority: P{task.priority}",
                "Created from a meeting commitment by the Promise vs. Progress engine.",
            ),
            "labels": ["promise-vs-progress"],
            "priority": {"name": PRIORITY_NAMES.get(task.priority, "Medium")},
        }
        if task.target_date:
            fields["duedate"] = task.target_date.isoformat()
        response = await self.http.post("/rest/api/3/issue", json={"fields": fields})
        if response.status_code == 400:
            # Projects differ in which optional fields are on the create screen; drop the ones Jira rejects once.
            rejected = set((response.json().get("errors") or {}).keys()) & {"priority", "duedate", "labels"}
            if rejected:
                for name in rejected:
                    fields.pop(name, None)
                response = await self.http.post("/rest/api/3/issue", json={"fields": fields})
        return response

    @observe("jira-sync", as_type="tool", capture_output=True)
    async def sync(self, task: Task) -> SyncOutcome:
        tracing.update_span(metadata={"task_id": task.id, "mode": self.mode})
        key = parse_issue_key(task.external_ref)
        if self.mode != "live":
            key = key or f"{self._project_for(task)}-{task.id}"
            return SyncOutcome(ok=True, is_simulated=True, external_key=key, state=task.github_state or "open")
        try:
            if key:
                response = await self._get_issue(key)
                if response.status_code != 200:
                    return SyncOutcome(ok=False, error=describe_http_error("Jira", response, f"issue {key}"))
                state, _ = _state(response.json().get("fields") or {})
                return SyncOutcome(ok=True, url=self.browse_url(key), external_key=key, state=state)
            response = await self._create(task)
            if response.status_code not in (200, 201):
                detail = "; ".join(f"{k}: {v}" for k, v in (response.json().get("errors") or {}).items())[:300] if response.content else ""
                error = describe_http_error("Jira", response, f"creating an issue in {self._project_for(task)}")
                return SyncOutcome(ok=False, error=f"{error} {detail}".strip())
            key = response.json().get("key")
            return SyncOutcome(ok=True, url=self.browse_url(key), external_key=key, state="open")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Jira sync failed for task %s: %s", task.id, exc.__class__.__name__)
            return SyncOutcome(ok=False, error=f"Could not reach Jira ({exc.__class__.__name__}).")

    @observe("jira-verify", as_type="tool", capture_output=True)
    async def verify(self, task: Task) -> VerifyOutcome:
        tracing.update_span(metadata={"task_id": task.id, "mode": self.mode})
        if task.is_simulated or self.mode != "live":
            return verify_simulated(task)
        key = task.external_key or parse_issue_key(task.external_ref)
        if not key:
            return VerifyOutcome(VerificationStatus.NOT_TRACKABLE, None, "No linked Jira issue to verify.")
        try:
            response = await self._get_issue(key)
        except httpx.HTTPError as exc:
            return VerifyOutcome(VerificationStatus.CHECK_FAILED, task.github_state, f"Could not reach Jira ({exc.__class__.__name__}).")
        if response.status_code != 200:
            return VerifyOutcome(VerificationStatus.CHECK_FAILED, task.github_state, describe_http_error("Jira", response, f"issue {key}"))
        fields = response.json().get("fields") or {}
        state, status_name = _state(fields)
        if state == "closed":
            return VerifyOutcome(VerificationStatus.VERIFIED_DONE, state, f"{key} is {status_name}.")
        if state == "closed_not_planned":
            resolution = (fields.get("resolution") or {}).get("name")
            return VerifyOutcome(VerificationStatus.CLOSED_NOT_COMPLETED, state, f"{key} was closed as {resolution}.")
        return VerifyOutcome(VerificationStatus.OPEN, state, f"{key} is {status_name}.")
