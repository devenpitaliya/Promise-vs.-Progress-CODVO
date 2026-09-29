"""Live-mode GitHub connector behaviour against a mocked HTTP transport."""

from types import SimpleNamespace

import httpx
import pytest

from app.enums import TargetSystem, VerificationStatus
from app.services.connectors.github import GitHubConnector


def task(**overrides):
    fields = dict(
        id=7,
        target_system=TargetSystem.GITHUB_PR,
        repository="acme/api",
        external_ref="PR #12",
        github_pr_number=12,
        github_issue_number=None,
        github_state="open",
        is_simulated=False,
        app_closed_marker=None,
        assignee="Maya",
        description="Merge fix",
        source_quote=None,
        target_date=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def client_returning(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"message": "Not Found"})
        status, body = routes[key]
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(base_url="https://api.github.test", transport=httpx.MockTransport(handler))


def github(client: httpx.AsyncClient) -> GitHubConnector:
    return GitHubConnector({"token": "ghp_test"}, source="user", http=client)


async def test_closed_unmerged_pr_is_not_done():
    async with client_returning({("GET", "/repos/acme/api/pulls/12"): (200, {"state": "closed", "merged": False})}) as c:
        outcome = await github(c).verify(task())
    assert outcome.status == VerificationStatus.CLOSED_NOT_COMPLETED


async def test_merged_pr_is_done():
    async with client_returning({("GET", "/repos/acme/api/pulls/12"): (200, {"state": "closed", "merged": True})}) as c:
        outcome = await github(c).verify(task())
    assert outcome.status == VerificationStatus.VERIFIED_DONE


@pytest.mark.parametrize(
    "reason,expected",
    [("completed", VerificationStatus.VERIFIED_DONE), ("not_planned", VerificationStatus.CLOSED_NOT_COMPLETED)],
)
async def test_issue_close_reason_is_respected(reason, expected):
    issue = task(target_system=TargetSystem.GITHUB_ISSUE, external_ref="Issue #5", github_issue_number=5, github_pr_number=None)
    async with client_returning({("GET", "/repos/acme/api/issues/5"): (200, {"state": "closed", "state_reason": reason})}) as c:
        outcome = await github(c).verify(issue)
    assert outcome.status == expected


async def test_sync_failure_is_reported_not_simulated():
    async with client_returning({}) as c:
        outcome = await github(c).sync(task())
    assert outcome.ok is False
    assert outcome.is_simulated is False
    assert "not found" in outcome.error


async def test_sync_requires_a_resolvable_repository():
    async with client_returning({}) as c:
        outcome = await github(c).sync(task(repository="api"))
    assert outcome.ok is False
    assert "repository" in outcome.error.lower()


async def test_existing_issue_is_linked_instead_of_duplicated():
    issue = task(target_system=TargetSystem.GITHUB_ISSUE, external_ref="Issue #5")
    routes = {
        ("GET", "/repos/acme/api/issues/5"): (200, {"number": 5, "state": "open", "html_url": "https://github.com/acme/api/issues/5"})
    }
    async with client_returning(routes) as c:
        outcome = await github(c).sync(issue)
    assert outcome.ok and outcome.issue_number == 5
    assert outcome.url == "https://github.com/acme/api/issues/5"


async def test_rate_limit_is_explained():
    def handler(_request):
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})

    async with httpx.AsyncClient(base_url="https://api.github.test", transport=httpx.MockTransport(handler)) as c:
        outcome = await github(c).verify(task())
    assert outcome.status == VerificationStatus.CHECK_FAILED
    assert "rate limit" in outcome.note


async def test_new_issue_body_includes_priority():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read().decode()
        return httpx.Response(201, json={"number": 9, "state": "open", "html_url": "https://github.com/acme/api/issues/9"})

    new_issue = task(target_system=TargetSystem.GITHUB_ISSUE, external_ref=None, priority=1)
    async with httpx.AsyncClient(base_url="https://api.github.test", transport=httpx.MockTransport(handler)) as c:
        outcome = await github(c).sync(new_issue)
    assert outcome.ok and "Priority:** P1" in captured["body"]
