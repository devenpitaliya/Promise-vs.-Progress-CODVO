"""Integrations: per-user connections in Settings, Jira and Slack connectors, routing and safety."""

import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.enums import TargetSystem, VerificationStatus
from app.services.connectors import Message
from app.services.connectors.jira import JiraConnector
from app.services.connectors.slack import SlackConnector
from tests.conftest import create_meeting, register

JIRA = {"base_url": "https://acme.atlassian.net", "email": "lead@acme.com", "api_token": "ATATT-secret-token-123", "project_key": "ENG"}
WEBHOOK = "https://hooks.slack.com/services/T000/B000/secretvalue"


def mock_client(handler, base_url="https://acme.atlassian.net"):
    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler))


@pytest.fixture
def jira_api(monkeypatch):
    """A tiny fake Jira: records requests, answers from `routes` (method, path) -> (status, body)."""
    state = SimpleNamespace(routes={}, requests=[])

    def handler(request: httpx.Request) -> httpx.Response:
        state.requests.append((request.method, request.url.path, request.content.decode() if request.content else ""))
        route = state.routes.get((request.method, request.url.path), (404, {"errorMessages": ["not found"]}))
        status, body = route(request) if callable(route) else route
        return httpx.Response(status, json=body)

    monkeypatch.setattr(JiraConnector, "_client", lambda self: mock_client(handler, self.config["base_url"]))
    return state


@pytest.fixture
def slack_api(monkeypatch):
    state = SimpleNamespace(posts=[], reply=(200, "ok"))

    def handler(request: httpx.Request) -> httpx.Response:
        state.posts.append((str(request.url), json.loads(request.content)))
        status, body = state.reply
        return httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)

    monkeypatch.setattr(SlackConnector, "_client", lambda self: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return state


def task(**overrides):
    fields = dict(
        id=3,
        target_system=TargetSystem.JIRA,
        repository=None,
        external_ref=None,
        external_key=None,
        github_state=None,
        is_simulated=False,
        app_closed_marker=None,
        assignee="Priya Raman",
        description="Write the rollout runbook",
        source_quote="I'll write the rollout runbook by Friday.",
        target_date=date(2026, 10, 2),
        priority=1,
    )
    return SimpleNamespace(**{**fields, **overrides})


# ---- Settings > Integrations API --------------------------------------------------------------


async def test_lists_every_tool_with_simulated_trackers_by_default(client, auth):
    body = (await client.get("/api/v1/integrations/", headers=auth)).json()
    by_kind = {i["kind"]: i for i in body["integrations"]}
    assert set(by_kind) == {"github", "jira", "slack"}
    assert by_kind["jira"]["mode"] == "simulated" and by_kind["jira"]["source"] == "none"
    assert by_kind["slack"]["category"] == "notifier"
    assert body["default_tracker"] == "github"
    assert any(f["secret"] for f in by_kind["jira"]["fields"])


async def test_save_masks_secrets_and_keeps_them_on_partial_update(client, auth):
    saved = await client.put("/api/v1/integrations/jira", json={"values": JIRA}, headers=auth)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["mode"] == "live" and body["source"] == "user"
    assert body["config"]["project_key"] == "ENG"
    assert "ATATT-secret-token-123" not in saved.text
    assert body["secrets_masked"]["api_token"] != JIRA["api_token"]

    # Changing only the project keeps the stored token.
    update = await client.put("/api/v1/integrations/jira", json={"values": {"project_key": "ops", "api_token": ""}}, headers=auth)
    assert update.status_code == 200 and update.json()["config"]["project_key"] == "OPS"
    assert update.json()["secrets_masked"]["api_token"]

    removed = await client.delete("/api/v1/integrations/jira", headers=auth)
    assert removed.json()["mode"] == "simulated" and removed.json()["has_user_connection"] is False


@pytest.mark.parametrize(
    "values,message",
    [
        ({**JIRA, "base_url": "http://acme.atlassian.net"}, "https"),
        ({**JIRA, "base_url": "https://internal.corp.local"}, "atlassian.net"),
        ({**JIRA, "base_url": "https://127.0.0.1"}, "host name"),
        ({**JIRA, "project_key": "not a key"}, "Project key"),
        ({k: v for k, v in JIRA.items() if k != "api_token"}, "API token"),
        ({**JIRA, "api_token": "abc\ndef"}, "Invalid value"),
    ],
)
async def test_unsafe_or_incomplete_settings_are_rejected(client, auth, values, message):
    response = await client.put("/api/v1/integrations/jira", json={"values": values}, headers=auth)
    assert response.status_code == 422
    assert message in response.text


async def test_slack_webhook_must_be_slack(client, auth):
    bad = await client.put("/api/v1/integrations/slack", json={"values": {"webhook_url": "https://evil.example.com/hook"}}, headers=auth)
    assert bad.status_code == 422
    good = await client.put("/api/v1/integrations/slack", json={"values": {"webhook_url": WEBHOOK}}, headers=auth)
    assert good.status_code == 200 and good.json()["mode"] == "live"


async def test_connections_are_private_to_each_user(client, auth):
    await client.put("/api/v1/integrations/jira", json={"values": JIRA}, headers=auth)
    other = await register(client, email="other@example.com", name="Sam Okafor")
    theirs = {i["kind"]: i for i in (await client.get("/api/v1/integrations/", headers=other)).json()["integrations"]}
    assert theirs["jira"]["has_user_connection"] is False and theirs["jira"]["config"] == {}


async def test_test_connection_reports_success_and_failure(client, auth, jira_api):
    await client.put("/api/v1/integrations/jira", json={"values": JIRA}, headers=auth)
    jira_api.routes[("GET", "/rest/api/3/myself")] = (200, {"displayName": "Maya Chen"})
    jira_api.routes[("GET", "/rest/api/3/project/ENG")] = (200, {"name": "Engineering"})
    ok = (await client.post("/api/v1/integrations/jira/test", headers=auth)).json()
    assert ok["ok"] and "Maya Chen" in ok["message"] and "Engineering" in ok["message"]

    jira_api.routes[("GET", "/rest/api/3/myself")] = (401, {})
    failed = (await client.post("/api/v1/integrations/jira/test", headers=auth)).json()
    assert not failed["ok"] and "rejected the credentials" in failed["message"]
    listed = {i["kind"]: i for i in (await client.get("/api/v1/integrations/", headers=auth)).json()["integrations"]}
    assert listed["jira"]["last_test_ok"] is False


async def test_unknown_integration_is_404(client, auth):
    assert (await client.put("/api/v1/integrations/trello", json={"values": {}}, headers=auth)).status_code == 404


# ---- Jira connector ---------------------------------------------------------------------------


async def test_jira_creates_issue_with_priority_due_date_and_adf(jira_api):
    jira_api.routes[("POST", "/rest/api/3/issue")] = (201, {"key": "ENG-7"})
    connector = JiraConnector(JIRA, source="user")
    async with connector.session():
        outcome = await connector.sync(task())
    assert outcome.ok and outcome.external_key == "ENG-7"
    assert outcome.url == "https://acme.atlassian.net/browse/ENG-7"
    fields = json.loads(jira_api.requests[0][2])["fields"]
    assert fields["project"] == {"key": "ENG"} and fields["priority"] == {"name": "High"}
    assert fields["duedate"] == "2026-10-02" and fields["description"]["type"] == "doc"


async def test_jira_retries_without_fields_the_project_does_not_accept(jira_api):
    calls = []

    def create(request):
        calls.append(json.loads(request.content)["fields"])
        if len(calls) == 1:
            return 400, {"errors": {"priority": "Field 'priority' cannot be set."}}
        return 201, {"key": "ENG-8"}

    jira_api.routes[("POST", "/rest/api/3/issue")] = create
    connector = JiraConnector(JIRA)
    async with connector.session():
        outcome = await connector.sync(task())
    assert outcome.ok and outcome.external_key == "ENG-8"
    assert "priority" in calls[0] and "priority" not in calls[1] and calls[1]["duedate"] == "2026-10-02"


async def test_jira_links_a_mentioned_key_instead_of_creating(jira_api):
    jira_api.routes[("GET", "/rest/api/3/issue/OPS-42")] = (
        200,
        {"fields": {"status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}}},
    )
    connector = JiraConnector(JIRA)
    async with connector.session():
        outcome = await connector.sync(task(external_ref="OPS-42"))
    assert outcome.ok and outcome.external_key == "OPS-42" and outcome.state == "open"
    assert all(method == "GET" for method, _, _ in jira_api.requests)


@pytest.mark.parametrize(
    "fields,expected",
    [
        (
            {"status": {"name": "Released", "statusCategory": {"key": "done"}}, "resolution": {"name": "Done"}},
            VerificationStatus.VERIFIED_DONE,
        ),
        (
            {"status": {"name": "Closed", "statusCategory": {"key": "done"}}, "resolution": {"name": "Won't Do"}},
            VerificationStatus.CLOSED_NOT_COMPLETED,
        ),
        ({"status": {"name": "In Review", "statusCategory": {"key": "indeterminate"}}}, VerificationStatus.OPEN),
    ],
)
async def test_jira_verification_uses_status_category_and_resolution(jira_api, fields, expected):
    jira_api.routes[("GET", "/rest/api/3/issue/ENG-7")] = (200, {"fields": fields})
    connector = JiraConnector(JIRA)
    async with connector.session():
        outcome = await connector.verify(task(external_key="ENG-7"))
    assert outcome.status == expected


# ---- Slack connector --------------------------------------------------------------------------


async def test_slack_escapes_meeting_text_so_it_cannot_ping_everyone(slack_api):
    from app.schemas.briefing import BriefingPreview
    from app.services.notification_service import briefing_message

    preview = BriefingPreview(
        subject="Pre-meeting briefing",
        executive_summary="<!channel> ship it & celebrate",
        agenda=["<@U123> owes the runbook"],
        html="",
        counts={},
        completion_rate=50.0,
        generated_by="rules",
        github_mode="live",
    )
    await SlackConnector({"webhook_url": WEBHOOK}).send(briefing_message(preview))
    url, payload = slack_api.posts[0]
    assert url == WEBHOOK
    text = json.dumps(payload)
    assert "<!channel>" not in text and "<@U123>" not in text
    assert "&lt;!channel&gt; ship it &amp; celebrate" in text


async def test_slack_bot_errors_are_explained(slack_api):
    slack_api.reply = (200, {"ok": False, "error": "not_in_channel"})
    result = await SlackConnector({"bot_token": "xoxb-1-2-3", "channel": "#eng"}).send(Message("Hi", ["x"]))
    assert not result.ok and "/invite" in result.message
    assert slack_api.posts[0][1]["channel"] == "#eng"


# ---- Routing and end-to-end flows -------------------------------------------------------------


async def test_default_tracker_jira_routes_new_tickets_and_simulates_keys(client, auth):
    await client.put("/api/v1/integrations/default-tracker", json={"default_tracker": "jira"}, headers=auth)
    meeting = await create_meeting(client, auth)
    systems = {t["target_system"] for t in meeting["tasks"] if not t["external_ref"]}
    assert systems == {"jira"}
    assert any(t["target_system"] == "github_pr" for t in meeting["tasks"])  # PRs stay on GitHub

    jira_task = next(t for t in meeting["tasks"] if t["target_system"] == "jira")
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [jira_task["id"]]}, headers=auth)
    synced = (await client.get(f"/api/v1/commitments/{jira_task['id']}", headers=auth)).json()
    assert synced["is_simulated"] and synced["external_key"] == f"SIM-{jira_task['id']}"

    done = await client.post(f"/api/v1/commitments/{jira_task['id']}/simulate", json={"state": "closed"}, headers=auth)
    assert done.json()["verification_status"] == "VERIFIED_DONE"
    merged = await client.post(f"/api/v1/commitments/{jira_task['id']}/simulate", json={"state": "merged"}, headers=auth)
    assert merged.status_code == 409


async def test_live_jira_sync_from_review(client, auth, jira_api):
    await client.put("/api/v1/integrations/jira", json={"values": JIRA}, headers=auth)
    await client.put("/api/v1/integrations/default-tracker", json={"default_tracker": "jira"}, headers=auth)
    jira_api.routes[("POST", "/rest/api/3/issue")] = (201, {"key": "ENG-101"})
    meeting = await create_meeting(client, auth)
    jira_task = next(t for t in meeting["tasks"] if t["target_system"] == "jira")
    review = await client.post(
        f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [jira_task["id"]]}, headers=auth
    )
    approved = review.json()["approved"][0]
    assert approved["external_key"] == "ENG-101" and approved["is_simulated"] is False
    assert approved["github_url"] == "https://acme.atlassian.net/browse/ENG-101"
    status = (await client.get("/api/v1/settings/system", headers=auth)).json()
    assert status["jira_mode"] == "live" and status["default_tracker"] == "jira"


async def test_slack_reminders_and_briefings(client, auth, slack_api):
    meeting = await create_meeting(client, auth)
    assert (await client.post("/api/v1/reconciliation/reminders/slack", headers=auth)).status_code == 409  # not connected yet

    await client.put("/api/v1/integrations/slack", json={"values": {"webhook_url": WEBHOOK}}, headers=auth)
    ids = [t["id"] for t in meeting["tasks"]]
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": ids}, headers=auth)

    reminder = await client.post("/api/v1/reconciliation/reminders/slack", headers=auth)
    assert reminder.status_code == 200, reminder.text
    briefing = await client.post("/api/v1/briefings/slack", json={"meeting_id": meeting["id"]}, headers=auth)
    assert briefing.status_code == 200, briefing.text
    assert "Pre-meeting briefing" in json.dumps(slack_api.posts[-1][1])

    slack_api.reply = (404, "no_service")
    failed = await client.post("/api/v1/briefings/slack", json={}, headers=auth)
    assert failed.status_code == 502


async def test_schedule_can_deliver_to_slack_only(client, auth, slack_api):
    body = {"post_to_slack": True, "run_at": "2099-01-01T09:00:00Z"}
    assert (await client.post("/api/v1/briefings/schedules", json=body, headers=auth)).status_code == 422  # Slack not connected
    assert (await client.post("/api/v1/briefings/schedules", json={"run_at": "2099-01-01T09:00:00Z"}, headers=auth)).status_code == 422

    await client.put("/api/v1/integrations/slack", json={"values": {"webhook_url": WEBHOOK}}, headers=auth)
    created = await client.post("/api/v1/briefings/schedules", json=body, headers=auth)
    assert created.status_code == 201, created.text
    run = (await client.post(f"/api/v1/briefings/schedules/{created.json()['id']}/run", headers=auth)).json()
    assert run["email"] is None and run["slack_ok"] is True


# ---- Simulated items after connecting the real tool -------------------------------------------


@pytest.fixture
def github_api(monkeypatch):
    """A fake GitHub: every linked item is open; new issues get numbers from 900."""
    import re

    from app.services.connectors.github import GitHubConnector

    state = SimpleNamespace(created=[])

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and re.fullmatch(r"/repos/[^/]+/[^/]+/issues", path):
            number = 900 + len(state.created)
            state.created.append(json.loads(request.content)["title"])
            return httpx.Response(201, json={"number": number, "state": "open", "html_url": f"https://github.com{path}/{number}"})
        match = re.fullmatch(r"/repos/[^/]+/[^/]+/(issues|pulls)/(\d+)", path)
        if match:
            return httpx.Response(
                200, json={"number": int(match.group(2)), "state": "open", "merged": False, "html_url": f"https://github.com{path}"}
            )
        return httpx.Response(404, json={})

    monkeypatch.setattr(
        GitHubConnector,
        "_client",
        lambda self: httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)),
    )
    return state


async def test_simulated_items_move_to_github_once_connected(client, auth, github_api):
    meeting = await create_meeting(client, auth)
    ids = [t["id"] for t in meeting["tasks"]]
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": ids}, headers=auth)
    pr = next(t for t in meeting["tasks"] if t["external_ref"] == "PR #101")
    merged = await client.post(f"/api/v1/commitments/{pr['id']}/simulate", json={"state": "merged"}, headers=auth)
    assert merged.json()["verification_status"] == "VERIFIED_DONE"  # simulated evidence

    await client.put(
        "/api/v1/integrations/github", json={"values": {"token": "github_pat_test_token_123", "default_owner": "acme"}}, headers=auth
    )
    # Stuck before the fix: simulation is refused once GitHub is live.
    assert (await client.post(f"/api/v1/commitments/{pr['id']}/simulate", json={"state": "open"}, headers=auth)).status_code == 409

    result = (await client.post("/api/v1/commitments/sync-simulated", headers=auth)).json()
    assert result["moved"] >= 1
    tasks = {t["id"]: t for t in (await client.get(f"/api/v1/commitments/?meeting_id={meeting['id']}", headers=auth)).json()}
    moved = tasks[pr["id"]]
    assert moved["is_simulated"] is False and moved["github_url"].startswith("https://github.com/repos/acme/")
    assert moved["verification_status"] == "OPEN"  # the real PR is open: simulated "merged" no longer counts
    failed = {f["task_id"] for f in result["failures"]}
    for task_id, task in tasks.items():
        assert task["is_simulated"] is False or task_id in failed
        if task_id in failed:
            assert task["sync_status"] == "FAILED" and task["sync_error"]  # e.g. no repository: shown with Retry sync

    again = (await client.post("/api/v1/commitments/sync-simulated", headers=auth)).json()
    assert again["moved"] == 0  # idempotent: nothing left to move


async def test_single_simulated_item_can_be_synced_to_github(client, auth, github_api):
    meeting = await create_meeting(client, auth)
    issue = next(t for t in meeting["tasks"] if t["external_ref"] == "Issue #45")
    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [issue["id"]]}, headers=auth)
    await client.put(
        "/api/v1/integrations/github", json={"values": {"token": "github_pat_test_token_123", "default_owner": "acme"}}, headers=auth
    )
    synced = (await client.post(f"/api/v1/commitments/{issue['id']}/sync", headers=auth)).json()
    assert synced["is_simulated"] is False and synced["github_issue_number"] == 45
    assert synced["verification_status"] == "OPEN" and synced["last_checked_at"]


@pytest.fixture
def github_with_one_repo(monkeypatch):
    """A fake GitHub account 'acme' with one empty repository, pvp-demo (no existing issues or PRs)."""
    import re

    from app.services.connectors.github import GitHubConnector

    state = SimpleNamespace(created=[])

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/user":
            return httpx.Response(200, json={"login": "acme"}, headers={"x-ratelimit-remaining": "4999"})
        if path == "/users/acme":
            return httpx.Response(200, json={"login": "acme", "type": "User"})
        if request.method == "POST" and path == "/repos/acme/pvp-demo/issues":
            number = len(state.created) + 1
            state.created.append(json.loads(request.content)["title"])
            return httpx.Response(
                201, json={"number": number, "state": "open", "html_url": f"https://github.com/acme/pvp-demo/issues/{number}"}
            )
        match = re.fullmatch(r"/repos/acme/pvp-demo/issues/(\d+)", path)
        if match and int(match.group(1)) <= len(state.created):
            return httpx.Response(200, json={"number": int(match.group(1)), "state": "open"})
        return httpx.Response(404, json={"message": "Not Found"})

    monkeypatch.setattr(
        GitHubConnector,
        "_client",
        lambda self: httpx.AsyncClient(base_url="https://api.github.com", transport=httpx.MockTransport(handler)),
    )
    return state


async def test_github_test_catches_a_wrong_default_owner(client, auth, github_with_one_repo):
    token = "github_pat_test_token_123"
    assert (
        await client.put("/api/v1/integrations/github", json={"values": {"token": token, "default_owner": "acme/pvp-demo"}}, headers=auth)
    ).status_code == 422

    await client.put("/api/v1/integrations/github", json={"values": {"token": token, "default_owner": "pvp-demo"}}, headers=auth)
    wrong = (await client.post("/api/v1/integrations/github/test", headers=auth)).json()
    assert wrong["ok"] is False
    assert "'pvp-demo' is not a GitHub user or organisation" in wrong["message"] and "'acme'" in wrong["message"]

    await client.put("/api/v1/integrations/github", json={"values": {"default_owner": "acme"}}, headers=auth)  # token kept
    right = (await client.post("/api/v1/integrations/github/test", headers=auth)).json()
    assert right["ok"] is True and "Default owner 'acme' is a GitHub user" in right["message"]


async def test_failed_syncs_can_be_fixed_and_retried_in_bulk(client, auth, github_with_one_repo):
    await client.put(
        "/api/v1/integrations/github", json={"values": {"token": "github_pat_test_token_123", "default_owner": "acme"}}, headers=auth
    )
    meeting = await create_meeting(client, auth)
    ids = [t["id"] for t in meeting["tasks"]]
    review = (await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": ids}, headers=auth)).json()
    assert len(review["sync_failures"]) == len(ids)  # sample repos and numbers do not exist in this account
    report = (await client.get("/api/v1/reconciliation/report", headers=auth)).json()
    assert sum(i["sync_status"] == "FAILED" for i in report["items"]) == len(ids)

    url = "/api/v1/commitments/retry-failed"
    only_repo = (await client.post(url, json={"meeting_id": meeting["id"], "repository": "pvp-demo"}, headers=auth)).json()
    assert only_repo["retried"] == len(ids)
    assert only_repo["failures"]  # items referencing issue #45 / PR #101 still cannot be linked

    fixed = (
        await client.post(url, json={"meeting_id": meeting["id"], "repository": "pvp-demo", "create_missing": True}, headers=auth)
    ).json()
    assert fixed["failures"] == [] and fixed["synced"] == fixed["retried"]
    tasks = (await client.get(f"/api/v1/commitments/?meeting_id={meeting['id']}", headers=auth)).json()
    assert all(t["sync_status"] == "SYNCED" and t["repository"] == "pvp-demo" and not t["is_simulated"] for t in tasks)
    assert all(t["target_system"] == "github_issue" for t in tasks)  # PRs that could not be linked are tracked as issues
    assert len(github_with_one_repo.created) == len(ids)  # exactly one new issue each, no duplicates

    assert (await client.post(url, json={}, headers=auth)).json() == {"retried": 0, "synced": 0, "failures": []}
    assert (await client.post(url, json={"repository": "not a repo!"}, headers=auth)).status_code == 422
