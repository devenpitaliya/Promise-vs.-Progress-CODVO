from tests.conftest import create_meeting


async def test_upload_extracts_pending_commitments_without_syncing(client, auth):
    meeting = await create_meeting(client, auth)
    assert meeting["extraction_source"] == "rules"
    assert len(meeting["tasks"]) >= 4
    for task in meeting["tasks"]:
        assert task["approval_status"] == "PENDING"
        assert task["sync_status"] == "NOT_SYNCED"
        assert task["source_quote"]

    by_ref = {t["external_ref"]: t for t in meeting["tasks"] if t["external_ref"]}
    assert by_ref["PR #101"]["assignee"] == "Maya Chen"
    assert by_ref["PR #101"]["target_system"] == "github_pr"
    assert by_ref["PR #101"]["target_date"] == "2026-09-21"
    assert by_ref["Issue #45"]["target_date"] == "2026-09-22"
    assert by_ref["Issue #78"]["speech_status"] == "BLOCKED"
    assert by_ref["PR #204"]["speech_status"] == "COMPLETED_IN_SPEECH"


async def test_transcript_without_commitments_yields_nothing(client, auth):
    meeting = await create_meeting(
        client, auth, transcript="Maya: Morning everyone.\nPriya: Coffee is great today.\nMaya: Thanks all.", participants=[]
    )
    assert meeting["tasks"] == []  # no fabricated fallback commitments


async def test_review_applies_exactly_the_selected_decisions(client, auth):
    meeting = await create_meeting(client, auth)
    ids = [t["id"] for t in meeting["tasks"]]
    approve, reject, untouched = ids[:2], ids[2:3], ids[3:]

    response = await client.post(
        f"/api/v1/commitments/review?meeting_id={meeting['id']}",
        json={"approve_ids": approve, "reject_ids": reject},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(t["id"] for t in body["approved"]) == sorted(approve)
    assert body["rejected_ids"] == reject

    tasks = {t["id"]: t for t in (await client.get(f"/api/v1/commitments/?meeting_id={meeting['id']}", headers=auth)).json()}
    for task_id in approve:
        assert tasks[task_id]["approval_status"] == "APPROVED"
        assert tasks[task_id]["sync_status"] == "SYNCED"
        assert tasks[task_id]["is_simulated"] is True
        assert tasks[task_id]["github_url"] is None  # simulation never invents GitHub links
    for task_id in reject:
        assert tasks[task_id]["approval_status"] == "REJECTED"
    for task_id in untouched:
        assert tasks[task_id]["approval_status"] == "PENDING"


async def test_review_validation(client, auth):
    meeting = await create_meeting(client, auth)
    other = await create_meeting(client, auth, sample_index=1)
    task_id = meeting["tasks"][0]["id"]
    url = f"/api/v1/commitments/review?meeting_id={meeting['id']}"

    overlap = await client.post(url, json={"approve_ids": [task_id], "reject_ids": [task_id]}, headers=auth)
    assert overlap.status_code == 422
    foreign = await client.post(url, json={"approve_ids": [other["tasks"][0]["id"]]}, headers=auth)
    assert foreign.status_code == 422

    assert (await client.post(url, json={"approve_ids": [task_id]}, headers=auth)).status_code == 200
    again = await client.post(url, json={"reject_ids": [task_id]}, headers=auth)
    assert again.status_code == 409


async def test_reviewer_can_edit_and_add_before_approving(client, auth):
    meeting = await create_meeting(client, auth)
    first = meeting["tasks"][0]

    edited = await client.patch(
        f"/api/v1/commitments/{first['id']}",
        json={"description": "Merge token expiry fix", "target_date": "2026-09-30", "repository": "acme/auth-service"},
        headers=auth,
    )
    assert edited.status_code == 200
    assert edited.json()["description"] == "Merge token expiry fix"

    added = await client.post(
        "/api/v1/commitments/",
        json={"meeting_id": meeting["id"], "assignee": "Sam Okafor", "description": "Write runbook for rollout"},
        headers=auth,
    )
    assert added.status_code == 201
    assert added.json()["approval_status"] == "PENDING"

    bad_repo = await client.patch(f"/api/v1/commitments/{first['id']}", json={"repository": "not a repo!"}, headers=auth)
    assert bad_repo.status_code == 422


async def test_priority_can_be_set_edited_and_is_validated(client, auth):
    meeting = await create_meeting(client, auth)
    task = meeting["tasks"][0]
    assert task["priority"] in (1, 2, 3)

    edited = await client.patch(f"/api/v1/commitments/{task['id']}", json={"priority": 1}, headers=auth)
    assert edited.json()["priority"] == 1
    assert (await client.patch(f"/api/v1/commitments/{task['id']}", json={"priority": 4}, headers=auth)).status_code == 422

    added = await client.post(
        "/api/v1/commitments/",
        json={"meeting_id": meeting["id"], "assignee": "Sam Okafor", "description": "Write release notes", "priority": 3},
        headers=auth,
    )
    assert added.json()["priority"] == 3

    await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [task["id"]]}, headers=auth)
    item = next(i for i in (await client.get("/api/v1/reconciliation/report", headers=auth)).json()["items"] if i["task_id"] == task["id"])
    assert item["priority"] == 1
