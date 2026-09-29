"""GitHub tracker: create or link issues and PRs, and verify their real state."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.config import settings
from app.constants.github import GITHUB_API_VERSION, GITHUB_USER_AGENT, SIMULATED_STATES
from app.enums import TargetSystem, VerificationStatus
from app.models.task import Task
from app.services.connectors.base import (
    CLOSED_STATUSES,
    OPEN_STATUSES,
    ConnectionTest,
    ConnectorConfigError,
    FieldSpec,
    PushOutcome,
    SyncOutcome,
    TrackerConnector,
    VerifyOutcome,
    change_lines,
    describe_http_error,
)
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

_NUMBER = re.compile(r"#?\s*(\d+)")
# GitHub user and organisation names: letters, digits and single hyphens, at most 39 characters.
_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def parse_ref_number(external_ref: Optional[str]) -> Optional[int]:
    if not external_ref or re.search(r"\b[A-Z][A-Z0-9_]{1,9}-\d+\b", external_ref):
        return None  # empty, or another tracker's key (e.g. Jira "SEC-231"), not a GitHub number
    match = _NUMBER.search(external_ref)
    return int(match.group(1)) if match else None


def _describe(response: httpx.Response, what: str) -> str:
    if response.status_code in (401, 403) and response.headers.get("x-ratelimit-remaining") == "0":
        return "GitHub API rate limit reached; try again later."
    return describe_http_error("GitHub", response, what)


def verify_simulated(task: Task) -> VerifyOutcome:
    """Shared by every tracker in simulated mode: the state is whatever the simulation endpoint set."""
    state = task.github_state or "open"
    is_pr = task.target_system == TargetSystem.GITHUB_PR
    if state == "merged" or (state == "closed" and not is_pr):
        return VerifyOutcome(VerificationStatus.VERIFIED_DONE, state, f"Simulated: item is {state}.")
    if state in ("closed", "closed_not_planned"):
        label = "closed without merging" if is_pr else "closed as not planned"
        return VerifyOutcome(VerificationStatus.CLOSED_NOT_COMPLETED, state, f"Simulated: item was {label}.")
    return VerifyOutcome(VerificationStatus.OPEN, "open", "Simulated: item is still open.")


class GitHubConnector(TrackerConnector):
    kind = "github"
    label = "GitHub"
    fields = [
        FieldSpec(
            "token",
            "Personal access token",
            secret=True,
            required=True,
            placeholder="github_pat_...",
            help="Fine-grained token with Issues read/write and Pull requests read on the repositories you track.",
        ),
        FieldSpec("default_owner", "Default owner", placeholder="acme", help="Used when a commitment names a repository without 'owner/'."),
    ]

    @staticmethod
    def validate(config: Dict[str, Any]) -> Dict[str, Any]:
        owner = (config.get("default_owner") or "").strip()
        if owner:
            if "/" in owner:
                raise ConnectorConfigError("Default owner is just the user or organisation (e.g. 'acme'), not 'owner/repo'.")
            if not _OWNER.match(owner):
                raise ConnectorConfigError("Default owner must be a GitHub user or organisation name (letters, digits and hyphens).")
            config["default_owner"] = owner
        return config

    def is_configured(self) -> bool:
        return bool(self.config.get("token"))

    def _client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.config['token']}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": GITHUB_USER_AGENT,
        }
        return httpx.AsyncClient(base_url=settings.GITHUB_API_URL, headers=headers, timeout=settings.GITHUB_TIMEOUT_SECONDS)

    def resolve_repository(self, repository: Optional[str]) -> Optional[Tuple[str, str]]:
        """'org/repo' -> (org, repo); 'repo' -> (default owner, repo); otherwise None."""
        if not repository:
            return None
        parts = repository.strip().strip("/").split("/")
        if len(parts) == 2 and all(parts):
            return parts[0], parts[1]
        owner = self.config.get("default_owner")
        if len(parts) == 1 and parts[0] and owner:
            return owner, parts[0]
        return None

    async def test(self) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(False, "Add a personal access token first.")
        try:
            async with self.session():
                response = await self.http.get("/user")
        except httpx.HTTPError as exc:
            return ConnectionTest(False, f"Could not reach GitHub ({exc.__class__.__name__}).")
        if response.status_code != 200:
            return ConnectionTest(False, _describe(response, "the token's user"))
        login = response.json().get("login", "unknown")
        remaining = response.headers.get("x-ratelimit-remaining", "?")
        message = f"Connected as {login} (API calls left this hour: {remaining})."

        owner = self.config.get("default_owner")
        if owner:
            # A wrong default owner (e.g. a repository name) makes every "repo"-only commitment fail later.
            try:
                async with self.session():
                    found = await self.http.get(f"/users/{quote(owner, safe='')}")
            except httpx.HTTPError as exc:
                return ConnectionTest(False, f"{message} Could not check default owner '{owner}' ({exc.__class__.__name__}).")
            if found.status_code == 404:
                return ConnectionTest(
                    False,
                    f"The token works (connected as {login}), but default owner '{owner}' is not a GitHub user or organisation. "
                    f"It should be the account that owns your repositories, e.g. '{login}', not a repository name.",
                )
            if found.status_code == 200:
                kind = "organisation" if found.json().get("type") == "Organization" else "user"
                message += f" Default owner '{owner}' is a GitHub {kind}."
        return ConnectionTest(True, message)

    @observe("github-sync", as_type="tool", capture_output=True)
    async def sync(self, task: Task) -> SyncOutcome:
        tracing.update_span(metadata={"task_id": task.id, "target_system": str(task.target_system), "mode": self.mode})
        number = parse_ref_number(task.external_ref)
        is_pr = task.target_system == TargetSystem.GITHUB_PR

        if self.mode != "live":
            return SyncOutcome(
                ok=True,
                is_simulated=True,
                issue_number=None if is_pr else (number or task.id),
                pr_number=(number or task.id) if is_pr else None,
                state=task.github_state if task.github_state in SIMULATED_STATES else "open",
            )

        repo = self.resolve_repository(task.repository)
        if repo is None:
            return SyncOutcome(ok=False, error="No GitHub repository: set it as 'owner/repo' (or a default owner in Settings).")
        owner, name = repo

        try:
            if is_pr:
                if not number:
                    return SyncOutcome(ok=False, error="A pull request number is required to track a PR (e.g. 'PR #123').")
                response = await self.http.get(f"/repos/{owner}/{name}/pulls/{number}")
                if response.status_code != 200:
                    return SyncOutcome(ok=False, error=_describe(response, f"PR #{number} in {owner}/{name}"))
                data = response.json()
                return SyncOutcome(
                    ok=True,
                    url=data.get("html_url"),
                    pr_number=data.get("number"),
                    state="merged" if data.get("merged") else data.get("state"),
                )

            if number:
                response = await self.http.get(f"/repos/{owner}/{name}/issues/{number}")
                if response.status_code != 200:
                    return SyncOutcome(ok=False, error=_describe(response, f"issue #{number} in {owner}/{name}"))
                data = response.json()
                return SyncOutcome(ok=True, url=data.get("html_url"), issue_number=data.get("number"), state=data.get("state"))

            body = (
                f"**Committed by:** {task.assignee}\n\n"
                f"{task.description}\n\n"
                + (f"> {task.source_quote}\n\n" if task.source_quote else "")
                + f"**Priority:** P{task.priority}\n\n"
                + (f"**Target date:** {task.target_date.isoformat()}\n\n" if task.target_date else "")
                + "_Created from a meeting commitment by the Promise vs. Progress engine._"
            )
            response = await self.http.post(f"/repos/{owner}/{name}/issues", json={"title": task.description[:240], "body": body})
            if response.status_code not in (200, 201):
                return SyncOutcome(ok=False, error=_describe(response, f"creating an issue in {owner}/{name}"))
            data = response.json()
            return SyncOutcome(ok=True, url=data.get("html_url"), issue_number=data.get("number"), state=data.get("state"))
        except httpx.HTTPError as exc:
            logger.warning("GitHub sync failed for task %s: %s", task.id, exc)
            return SyncOutcome(ok=False, error=f"Could not reach GitHub ({exc.__class__.__name__}).")

    @observe("github-verify", as_type="tool", capture_output=True)
    async def verify(self, task: Task) -> VerifyOutcome:
        tracing.update_span(metadata={"task_id": task.id, "target_system": str(task.target_system), "mode": self.mode})
        if task.is_simulated or self.mode != "live":
            return verify_simulated(task)

        repo = self.resolve_repository(task.repository)
        is_pr = task.target_system == TargetSystem.GITHUB_PR
        number = task.github_pr_number if is_pr else task.github_issue_number
        if repo is None or number is None:
            return VerifyOutcome(VerificationStatus.NOT_TRACKABLE, None, "No linked GitHub item to verify.")
        owner, name = repo

        try:
            if is_pr:
                response = await self.http.get(f"/repos/{owner}/{name}/pulls/{number}")
                if response.status_code != 200:
                    return VerifyOutcome(VerificationStatus.CHECK_FAILED, task.github_state, _describe(response, f"PR #{number}"))
                data = response.json()
                if data.get("merged"):
                    return VerifyOutcome(VerificationStatus.VERIFIED_DONE, "merged", f"PR #{number} is merged in {owner}/{name}.")
                if data.get("state") == "closed":
                    return VerifyOutcome(VerificationStatus.CLOSED_NOT_COMPLETED, "closed", f"PR #{number} was closed without merging.")
                draft = " (draft)" if data.get("draft") else ""
                return VerifyOutcome(VerificationStatus.OPEN, "open", f"PR #{number} is open{draft}.")

            response = await self.http.get(f"/repos/{owner}/{name}/issues/{number}")
            if response.status_code != 200:
                return VerifyOutcome(VerificationStatus.CHECK_FAILED, task.github_state, _describe(response, f"issue #{number}"))
            data = response.json()
            if data.get("state") == "closed":
                if data.get("state_reason") in (None, "completed"):
                    if task.app_closed_marker and data.get("closed_at") == task.app_closed_marker:
                        return VerifyOutcome(
                            VerificationStatus.CLOSED_FROM_APP,
                            "closed",
                            f"Issue #{number} was closed from this app, not in GitHub; it counts as claimed until confirmed in GitHub.",
                        )
                    return VerifyOutcome(VerificationStatus.VERIFIED_DONE, "closed", f"Issue #{number} was closed as completed.")
                return VerifyOutcome(
                    VerificationStatus.CLOSED_NOT_COMPLETED,
                    "closed_not_planned",
                    f"Issue #{number} was closed as {data.get('state_reason')}.",
                )
            return VerifyOutcome(VerificationStatus.OPEN, "open", f"Issue #{number} is open.")
        except httpx.HTTPError as exc:
            logger.warning("GitHub verification failed for task %s: %s", task.id, exc)
            return VerifyOutcome(VerificationStatus.CHECK_FAILED, task.github_state, f"Could not reach GitHub ({exc.__class__.__name__}).")

    @observe("github-push", as_type="tool", capture_output=True)
    async def push_update(
        self, task: Task, status_change: Optional[Tuple[str, str]], edits: Dict[str, Any], actor: str
    ) -> Optional[PushOutcome]:
        """Mirror an in-app change: comment on the item, retitle it, and close or reopen issues.

        PRs are never closed or merged from here (closing a PR means "not merged"); they only get the comment.
        """
        if task.is_simulated or self.mode != "live":
            return None
        repo = self.resolve_repository(task.repository)
        is_pr = task.target_system == TargetSystem.GITHUB_PR
        number = task.github_pr_number if is_pr else task.github_issue_number
        if repo is None or number is None:
            return PushOutcome(False, "Not updated in GitHub: the commitment has no linked item.")
        owner, name = repo
        item = f"{'PR' if is_pr else 'issue'} #{number}"
        path = f"/repos/{owner}/{name}/issues/{number}"  # PRs are issues for comments and titles
        done: List[str] = []
        marker: Optional[str] = None
        try:
            lines = change_lines(status_change, edits, actor)
            if lines:
                response = await self.http.post(f"{path}/comments", json={"body": "\n\n".join(lines)})
                if response.status_code not in (200, 201):
                    return PushOutcome(False, f"Not updated in GitHub: {_describe(response, item)}")
                done.append("added a comment")

            patch: Dict[str, Any] = {}
            if "description" in edits and not is_pr:
                patch["title"] = task.description[:240]
            if status_change and not is_pr:
                old, new = status_change
                if new == "DONE":
                    patch.update(state="closed", state_reason="completed")
                elif new == "CANCELLED":
                    patch.update(state="closed", state_reason="not_planned")
                elif new in OPEN_STATUSES and old in CLOSED_STATUSES:
                    patch.update(state="open", state_reason="reopened")
            if patch:
                response = await self.http.patch(path, json=patch)
                if response.status_code != 200:
                    return PushOutcome(False, f"Comment added, but {item} was not updated: {_describe(response, item)}")
                data = response.json()
                if patch.get("state") == "closed":
                    marker = data.get("closed_at") if patch["state_reason"] == "completed" else ""
                    done.append("closed it as completed" if patch["state_reason"] == "completed" else "closed it as not planned")
                elif patch.get("state") == "open":
                    marker = ""
                    done.append("reopened it")
                if "title" in patch:
                    done.append("updated the title")
        except httpx.HTTPError as exc:
            return PushOutcome(False, f"Not updated in GitHub: could not reach GitHub ({exc.__class__.__name__}).")
        if not done:
            return None
        note = " It counts as claimed until it is confirmed in GitHub." if marker else ""
        if is_pr and status_change and status_change[1] in CLOSED_STATUSES:
            note = " Pull requests are never closed or merged from the app; merge it in GitHub to verify it."
        return PushOutcome(True, f"GitHub {item}: {', '.join(done)}.{note}", closed_marker=marker)
