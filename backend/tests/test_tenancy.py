import pytest

from tests.conftest import approve_all, create_meeting, register

PROTECTED = [
    ("GET", "/api/v1/meetings/"),
    ("POST", "/api/v1/meetings/"),
    ("GET", "/api/v1/meetings/samples"),
    ("GET", "/api/v1/commitments/"),
    ("PATCH", "/api/v1/commitments/1"),
    ("POST", "/api/v1/commitments/review?meeting_id=1"),
    ("GET", "/api/v1/reconciliation/report"),
    ("POST", "/api/v1/reconciliation/run"),
    ("POST", "/api/v1/briefings/send"),
    ("GET", "/api/v1/briefings/schedules"),
    ("GET", "/api/v1/settings/ai"),
    ("PUT", "/api/v1/settings/ai"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
async def test_every_endpoint_requires_authentication(client, method, path):
    response = await client.request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"


async def test_users_cannot_see_or_touch_each_others_data(client):
    alice = await register(client, "alice@example.com", "Alice")
    bob = await register(client, "bob@example.com", "Bob")
    meeting = await create_meeting(client, alice)
    await approve_all(client, alice, meeting)
    task_id = meeting["tasks"][0]["id"]

    assert (await client.get("/api/v1/meetings/", headers=bob)).json() == []
    assert (await client.get(f"/api/v1/meetings/{meeting['id']}", headers=bob)).status_code == 404
    assert (await client.delete(f"/api/v1/meetings/{meeting['id']}", headers=bob)).status_code == 404
    assert (await client.get("/api/v1/commitments/", headers=bob)).json() == []
    assert (await client.patch(f"/api/v1/commitments/{task_id}", json={"status": "DONE"}, headers=bob)).status_code == 404
    assert (
        await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": [task_id]}, headers=bob)
    ).status_code == 404
    assert (await client.get("/api/v1/reconciliation/report", headers=bob)).json()["total"] == 0
    assert (await client.post("/api/v1/briefings/preview", json={"meeting_id": meeting["id"]}, headers=bob)).status_code == 404

    # Alice still sees everything.
    assert len((await client.get("/api/v1/commitments/", headers=alice)).json()) == len(meeting["tasks"])
