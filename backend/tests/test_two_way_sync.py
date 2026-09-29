"""Two-way GitHub sync (status, edits, comments) and Jira/Slack shown as "coming soon"."""

import json
import re
from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.services.connectors.github import GitHubConnector, parse_ref_number
from tests.conftest import create_meeting

TOKEN = "github_pat_test_token_123"


@pytest.fixture
def github(monkeypatch):
    """A stateful fake GitHub: account 'acme', repository pvp-demo, open PR #7."""
    state = SimpleNamespace(issues={}, comments=[], closes=0, fail_patch=False)

    def issue_json(number):
        issue = state.issues[number]
        return {"number": number, "html_url": f"https://github.com/acme/pvp-demo/issues/{number}", **issue}

    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}
        if path == "/user":
            return httpx.Response(200, json={"login": "acme"})
        if path == "/users/acme":
            return httpx.Response(200, json={"login": "acme", "type": "User"})
        if method == "POST" and path == "/repos/acme/pvp-demo/issues":
            number = len(state.issues) + 1
            state.issues[number] = {"title": body["title"], "state": "open", "state_reason": None, "closed_at": None}
            return httpx.Response(201, json=issue_json(number))
        if path == "/repos/acme/pvp-demo/pulls/7":
            return httpx.Response(
                200, json={"number": 7, "state": "open", "merged": False, "html_url": "https://github.com/acme/pvp-demo/pull/7"}
            )
        match = re.fullmatch(r"/repos/acme/pvp-demo/issues/(\d+)(/comments)?", path)
        if match:
            number = int(match.group(1))
            if match.group(2):
                state.comments.append((number, body["body"]))
                return httpx.Response(201, json={"id": len(state.comments)})
            if method == "PATCH":
                if state.fail_patch:
                    return httpx.Response(403, json={"message": "Resource not accessible by personal access token"})
                issue = state.issues.setdefault(number, {"title": "PR", "state": "open", "state_reason": None, "closed_at": None})
                if "title" in body:
                    issue["title"] = body["title"]
                if body.get("state") == "closed":
                    state.closes += 1
                    issue.update(state="closed", state_reason=body.get("state_reason"), closed_at=f"2026-09-29T10:00:{state.closes:02d}Z")
                elif body.get("state") == "open":
                    issue.update(state="open", state_reason="reopened", closed_at=None)
            if number in state.issues:
                return httpx.Response(200, json=issue_json(number))
        return httpx.Response(404, json={"message": "Not Found"})

    monkeypatch.setattr(
        GitHubConnector,
        "_client",
        lambda self: httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)),
    )
    return state


async def tracked_issue(client, auth, github) -> dict:
    """Connect GitHub, extract a meeting and approve one commitment as a new issue in pvp-demo."""
    await client.put("/api/v1/integrations/github", json={"values": {"token": TOKEN, "default_owner": "acme"}}, headers=auth)
    meeting = await create_meeting(client, auth)
    task = next(t for t in meeting["tasks"] if t["external_ref"] == "Issue #45")
    await client.patch(f"/api/v1/commitments/{task['id']}", json={"repository": "pvp-demo", "external_ref": ""}, headers=auth)
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [task["id"]]}, headers=auth)
    synced = (await client.get(f"/api/v1/commitments/{task['id']}", headers=auth)).json()
    assert synced["sync_status"] == "SYNCED" and synced["github_issue_number"] == 1
    return synced


async def verdict(client, auth, task_id: int) -> str:
    report = (await client.post("/api/v1/reconciliation/run", json={}, headers=auth)).json()
    return next(i["verdict"] for i in report["items"] if i["task_id"] == task_id)


async def test_done_in_the_app_closes_the_issue_but_only_counts_as_claimed(client, auth, github):
    task = await tracked_issue(client, auth, github)

    done = (await client.patch(f"/api/v1/commitments/{task['id']}", json={"status": "DONE"}, headers=auth)).json()
    assert github.issues[1]["state"] == "closed" and github.issues[1]["state_reason"] == "completed"
    assert "closed it as completed" in done["tracker_update"] and "claimed" in done["tracker_update"]
    assert done["verification_status"] == "CLOSED_FROM_APP"
    number, comment = github.comments[-1]
    assert number == 1 and "Maya Chen changed the status to Done" in comment and "claimed, not verified" in comment
    assert await verdict(client, auth, task["id"]) == "CLAIMED_UNVERIFIED"

    # Someone reopens it and closes it again in GitHub itself: a different close event, so it is verified.
    github.closes += 1
    github.issues[1]["closed_at"] = "2026-09-30T09:00:00Z"
    assert await verdict(client, auth, task["id"]) == "VERIFIED_DONE"


async def test_reopening_cancelling_and_title_edits_are_mirrored(client, auth, github):
    task = await tracked_issue(client, auth, github)
    url = f"/api/v1/commitments/{task['id']}"

    await client.patch(url, json={"status": "DONE"}, headers=auth)
    reopened = (await client.patch(url, json={"status": "IN_PROGRESS"}, headers=auth)).json()
    assert github.issues[1]["state"] == "open" and "reopened it" in reopened["tracker_update"]
    assert reopened["verification_status"] == "OPEN"

    retitled = (await client.patch(url, json={"description": "Fix worker crash on empty payload", "priority": 1}, headers=auth)).json()
    assert github.issues[1]["title"] == "Fix worker crash on empty payload"
    assert "updated the title" in retitled["tracker_update"]
    assert "changed the priority to P1" in github.comments[-1][1]

    cancelled = (await client.patch(url, json={"status": "CANCELLED"}, headers=auth)).json()
    assert github.issues[1]["state_reason"] == "not_planned" and "not planned" in cancelled["tracker_update"]

    unchanged = (await client.patch(url, json={"status": "CANCELLED"}, headers=auth)).json()
    assert unchanged["tracker_update"] is None  # nothing changed, nothing sent


async def test_pull_requests_are_never_closed_from_the_app(client, auth, github):
    await client.put("/api/v1/integrations/github", json={"values": {"token": TOKEN, "default_owner": "acme"}}, headers=auth)
    meeting = await create_meeting(client, auth)
    pr = next(t for t in meeting["tasks"] if t["target_system"] == "github_pr" and t["speech_status"] != "COMPLETED_IN_SPEECH")
    await client.patch(f"/api/v1/commitments/{pr['id']}", json={"repository": "pvp-demo", "external_ref": "PR #7"}, headers=auth)
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [pr["id"]]}, headers=auth)

    done = (await client.patch(f"/api/v1/commitments/{pr['id']}", json={"status": "DONE"}, headers=auth)).json()
    assert github.closes == 0 and github.comments[-1][0] == 7
    assert "never closed or merged from the app" in done["tracker_update"]
    assert await verdict(client, auth, pr["id"]) == "CLAIMED_UNVERIFIED"


async def test_github_errors_never_lose_the_local_change(client, auth, github):
    task = await tracked_issue(client, auth, github)
    github.fail_patch = True
    response = (await client.patch(f"/api/v1/commitments/{task['id']}", json={"status": "DONE"}, headers=auth)).json()
    assert response["status"] == "DONE"
    assert response["tracker_update"] == "Comment added, but issue #1 was not updated: GitHub denied access to issue #1 (HTTP 403)."
    assert github.issues[1]["state"] == "open"


# ---- Jira and Slack are "coming soon" by default ---------------------------------------------


@pytest.fixture
def github_only(monkeypatch):
    monkeypatch.setattr(settings, "ENABLED_INTEGRATIONS", ["github"])


async def test_jira_and_slack_are_coming_soon(client, auth, github_only):
    listed = {i["kind"]: i for i in (await client.get("/api/v1/integrations/", headers=auth)).json()["integrations"]}
    assert listed["github"]["available"] and not listed["jira"]["available"] and not listed["slack"]["available"]
    assert (await client.put("/api/v1/integrations/jira", json={"values": {}}, headers=auth)).status_code == 409
    assert (await client.post("/api/v1/integrations/slack/test", headers=auth)).status_code == 409
    assert (await client.put("/api/v1/integrations/default-tracker", json={"default_tracker": "jira"}, headers=auth)).status_code == 409
    assert (await client.post("/api/v1/reconciliation/reminders/slack", headers=auth)).status_code == 409
    assert (await client.post("/api/v1/briefings/slack", json={}, headers=auth)).status_code == 409
    schedule = {"post_to_slack": True, "run_at": "2099-01-01T09:00:00Z"}
    assert (await client.post("/api/v1/briefings/schedules", json=schedule, headers=auth)).status_code == 422
    status = (await client.get("/api/v1/settings/system", headers=auth)).json()
    assert status["integrations_available"] == ["github"] and status["slack_connected"] is False


async def test_jira_mentions_are_tracked_as_github_issues_while_jira_is_off(client, auth, github_only):
    meeting = await create_meeting(
        client, auth, transcript="Elena: I will finish the audit evidence for SEC-231 by Friday.", participants=[{"name": "Elena Petrova"}]
    )
    assert all(t["target_system"] != "jira" for t in meeting["tasks"])
    task = meeting["tasks"][0]
    rejected = await client.patch(f"/api/v1/commitments/{task['id']}", json={"target_system": "jira"}, headers=auth)
    assert rejected.status_code == 422 and "coming soon" in rejected.text
    assert parse_ref_number("SEC-231") is None and parse_ref_number("Issue #45") == 45
