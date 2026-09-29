from datetime import UTC, datetime, timedelta

from app.config import settings
from tests.conftest import approve_all, create_meeting


async def test_briefing_html_escapes_transcript_content(client, auth):
    meeting = await create_meeting(
        client,
        auth,
        participants=[],
        transcript="Mallory: I will fix <script>alert(document.cookie)</script> issue #9 today.",
    )
    await approve_all(client, auth, meeting)
    preview = (await client.post("/api/v1/briefings/preview", json={}, headers=auth)).json()
    assert "<script>" not in preview["html"]
    assert "&lt;script&gt;" in preview["html"]
    assert preview["generated_by"] == "rules"
    assert "simulation mode" in preview["html"]


async def test_send_ignores_client_html_and_logs_without_smtp(client, auth):
    meeting = await create_meeting(client, auth)
    await approve_all(client, auth, meeting)
    response = await client.post(
        "/api/v1/briefings/send",
        json={"recipient_email": "team@example.com", "meeting_id": meeting["id"], "html_content": "<h1>phish</h1>"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"]["status"] == "not_configured"  # never pretends to have sent
    assert "phish" not in body["preview"]["html"]

    history = (await client.get("/api/v1/briefings/emails", headers=auth)).json()
    assert len(history) == 1 and history[0]["recipient_email"] == "team@example.com"


async def test_send_rejects_invalid_recipient(client, auth):
    response = await client.post("/api/v1/briefings/send", json={"recipient_email": "not-an-email"}, headers=auth)
    assert response.status_code == 422


async def test_daily_email_quota(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "EMAILS_PER_USER_PER_DAY", 1)
    first = await client.post("/api/v1/briefings/send", json={"recipient_email": "a@example.com"}, headers=auth)
    second = await client.post("/api/v1/briefings/send", json={"recipient_email": "a@example.com"}, headers=auth)
    assert first.status_code == 200
    assert second.status_code == 429


async def test_scheduled_audit_persists_and_runs(client, auth):
    meeting = await create_meeting(client, auth)
    await approve_all(client, auth, meeting)
    run_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    created = await client.post(
        "/api/v1/briefings/schedules",
        json={"recipient_email": "lead@example.com", "run_at": run_at, "meeting_id": meeting["id"], "timezone": "Asia/Kolkata"},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    audit_id = created.json()["id"]

    # Regression: this used to crash with "too many values to unpack" on every run.
    run = await client.post(f"/api/v1/briefings/schedules/{audit_id}/run", headers=auth)
    assert run.status_code == 200, run.text
    assert run.json()["email"]["audit_id"] == audit_id
    assert run.json()["slack_ok"] is None  # not asked to post to Slack

    schedules = (await client.get("/api/v1/briefings/schedules", headers=auth)).json()
    assert schedules[0]["runs_count"] == 1
    assert schedules[0]["status"] == "completed"


async def test_recurring_audit_and_cancel(client, auth):
    created = await client.post(
        "/api/v1/briefings/schedules",
        json={
            "recipient_email": "lead@example.com",
            "schedule_type": "recurring",
            "start_date": "2026-10-01",
            "end_date": "2026-10-10",
            "daily_time": "09:30",
            "timezone": "Europe/London",
        },
        headers=auth,
    )
    assert created.status_code == 201, created.text
    cancelled = await client.delete(f"/api/v1/briefings/schedules/{created.json()['id']}", headers=auth)
    assert cancelled.json()["status"] == "cancelled"


async def test_schedule_validation(client, auth):
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert (
        await client.post("/api/v1/briefings/schedules", json={"recipient_email": "a@example.com", "run_at": past}, headers=auth)
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/briefings/schedules",
            json={"recipient_email": "a@example.com", "run_at": past, "timezone": "Mars/Olympus"},
            headers=auth,
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/briefings/schedules",
            json={
                "recipient_email": "a@example.com",
                "schedule_type": "recurring",
                "start_date": "2026-10-10",
                "end_date": "2026-10-01",
                "daily_time": "09:00",
            },
            headers=auth,
        )
    ).status_code == 422
