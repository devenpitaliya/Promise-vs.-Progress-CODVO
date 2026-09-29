import pytest

from app.config import settings
from tests.conftest import PASSWORD, register


async def test_register_login_and_me(client):
    headers = await register(client)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "lead@example.com"

    login = await client.post("/api/v1/auth/login", json={"email": "LEAD@example.com ", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["full_name"] == "Maya Chen"


@pytest.mark.parametrize(
    "password",
    ["short1", "onlyletterslong", "1234567890123"],
)
async def test_register_rejects_weak_passwords(client, password):
    response = await client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": password, "full_name": "A"})
    assert response.status_code == 422


async def test_duplicate_registration_conflicts(client):
    await register(client)
    response = await client.post("/api/v1/auth/register", json={"email": "lead@example.com", "password": PASSWORD, "full_name": "Other"})
    assert response.status_code == 409


async def test_wrong_password_is_rejected_without_auto_provisioning(client):
    await register(client)
    wrong = await client.post("/api/v1/auth/login", json={"email": "lead@example.com", "password": "Wrong-pass-123"})
    assert wrong.status_code == 401
    unknown = await client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert unknown.status_code == 401


async def test_login_is_rate_limited(client):
    await register(client)
    statuses = [
        (await client.post("/api/v1/auth/login", json={"email": "lead@example.com", "password": "Wrong-pass-123"})).status_code
        for _ in range(settings.LOGIN_ATTEMPTS_PER_MINUTE + 1)
    ]
    assert statuses[-1] == 429


async def test_invalid_tokens_are_rejected(client):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})).status_code == 401


async def test_github_backdoor_is_gone(client):
    assert (await client.post("/api/v1/auth/github")).status_code in (404, 405)


async def test_demo_workspace_only_when_enabled(client, monkeypatch):
    assert (await client.post("/api/v1/auth/demo")).status_code == 404

    monkeypatch.setattr(settings, "DEMO_MODE", True)
    first = await client.post("/api/v1/auth/demo")
    second = await client.post("/api/v1/auth/demo")
    assert first.status_code == second.status_code == 201
    assert first.json()["user"]["is_demo"] is True
    # Each visitor gets an isolated workspace, never a shared account.
    assert first.json()["user"]["id"] != second.json()["user"]["id"]
