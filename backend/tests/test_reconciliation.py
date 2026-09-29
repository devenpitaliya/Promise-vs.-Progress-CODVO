from datetime import date
from types import SimpleNamespace

import pytest

from app.config import settings
from app.enums import SpeechStatus, TaskStatus, Verdict, VerificationStatus
from app.services.reconciliation_service import evaluate
from tests.conftest import approve_all, create_meeting

TODAY = date(2026, 9, 27)


def make_task(**overrides):
    fields = dict(
        status=TaskStatus.OPEN,
        speech_status=SpeechStatus.PROPOSED,
        verification_status=VerificationStatus.OPEN,
        verification_note=None,
        target_date=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"verification_status": VerificationStatus.VERIFIED_DONE}, Verdict.VERIFIED_DONE),
        ({"status": TaskStatus.DONE}, Verdict.CLAIMED_UNVERIFIED),
        ({"speech_status": SpeechStatus.COMPLETED_IN_SPEECH}, Verdict.CLAIMED_UNVERIFIED),
        ({"verification_status": VerificationStatus.CLOSED_NOT_COMPLETED}, Verdict.AT_RISK),
        ({"status": TaskStatus.BLOCKED, "target_date": date(2026, 10, 5)}, Verdict.BLOCKED),
        ({"target_date": date(2026, 9, 24)}, Verdict.OVERDUE),
        ({"target_date": TODAY}, Verdict.DUE_TODAY),
        ({"target_date": date(2026, 9, 28)}, Verdict.AT_RISK),
        ({"target_date": date(2026, 10, 10)}, Verdict.ON_TRACK),
        ({}, Verdict.NO_DEADLINE),
        ({"status": TaskStatus.CANCELLED}, Verdict.CANCELLED),
    ],
)
def test_evaluate_verdicts(overrides, expected):
    result = evaluate(make_task(**overrides), TODAY)
    assert result.verdict == expected
    assert result.risk_reason  # every score is explained


def test_overdue_counts_days():
    result = evaluate(make_task(target_date=date(2026, 9, 24)), TODAY)
    assert result.days_overdue == 3
    assert result.risk_level == "CRITICAL"


async def _tracked(client, auth):
    meeting = await create_meeting(client, auth)
    await approve_all(client, auth, meeting)
    return {t["external_ref"]: t for t in meeting["tasks"] if t["external_ref"]}


async def test_report_is_read_only(client, auth):
    await _tracked(client, auth)
    before = (await client.get("/api/v1/commitments/", headers=auth)).json()
    report = (await client.get("/api/v1/reconciliation/report", headers=auth)).json()
    after = (await client.get("/api/v1/commitments/", headers=auth)).json()
    assert before == after
    assert report["github_mode"] == "simulated"
    assert report["total"] == len(before)


async def test_merged_pr_is_verified_but_closed_unmerged_pr_is_not(client, auth):
    refs = await _tracked(client, auth)
    pr_101, pr_204 = refs["PR #101"]["id"], refs["PR #204"]["id"]

    merged = await client.post(f"/api/v1/commitments/{pr_101}/simulate", json={"state": "merged"}, headers=auth)
    assert merged.json()["verification_status"] == "VERIFIED_DONE"
    assert merged.json()["status"] == "DONE"

    closed = await client.post(f"/api/v1/commitments/{pr_204}/simulate", json={"state": "closed"}, headers=auth)
    assert closed.json()["verification_status"] == "CLOSED_NOT_COMPLETED"

    items = {i["task_id"]: i for i in (await client.get("/api/v1/reconciliation/report", headers=auth)).json()["items"]}
    assert items[pr_101]["verdict"] == "VERIFIED_DONE"
    # PR #204 was "already merged" in speech, but GitHub says closed without merge.
    assert items[pr_204]["verdict"] == "CLAIMED_UNVERIFIED"
    assert items[pr_204]["risk_level"] == "HIGH"


async def test_manual_done_is_never_treated_as_verified(client, auth):
    refs = await _tracked(client, auth)
    issue = refs["Issue #45"]["id"]
    await client.patch(f"/api/v1/commitments/{issue}", json={"status": "DONE"}, headers=auth)
    items = {i["task_id"]: i for i in (await client.get("/api/v1/reconciliation/report", headers=auth)).json()["items"]}
    assert items[issue]["verdict"] == "CLAIMED_UNVERIFIED"
    assert items[issue]["verification_status"] != "VERIFIED_DONE"


async def test_run_reconciliation_records_last_check(client, auth):
    await _tracked(client, auth)
    report = (await client.post("/api/v1/reconciliation/run", json={}, headers=auth)).json()
    assert all(item["last_checked_at"] for item in report["items"])


async def test_simulation_refused_in_live_mode(client, auth, monkeypatch):
    refs = await _tracked(client, auth)
    monkeypatch.setattr(settings, "GITHUB_PERSONAL_ACCESS_TOKEN", "ghp_live_token_value")
    response = await client.post(f"/api/v1/commitments/{refs['PR #101']['id']}/simulate", json={"state": "merged"}, headers=auth)
    assert response.status_code == 409
