from sqlalchemy import select

from app.config import ENV_FILE
from app.database.session import async_session_maker
from app.models.user import User
from tests.conftest import register

GEMINI_KEY = "AIzaSyTESTKEY1234567890abcdef"


async def test_keys_are_per_user_encrypted_and_masked(client):
    alice = await register(client, "alice@example.com", "Alice")
    bob = await register(client, "bob@example.com", "Bob")

    saved = await client.put("/api/v1/settings/ai", json={"gemini_api_key": GEMINI_KEY, "preferred_provider": "gemini"}, headers=alice)
    assert saved.status_code == 200
    assert saved.json()["active_provider"] == "gemini"
    assert GEMINI_KEY not in saved.text
    assert saved.json()["gemini_key_masked"].startswith("AIza")

    async with async_session_maker() as db:
        user = (await db.execute(select(User).where(User.email == "alice@example.com"))).scalar_one()
        assert user.gemini_api_key_encrypted and GEMINI_KEY not in user.gemini_api_key_encrypted

    assert (await client.get("/api/v1/settings/ai", headers=bob)).json()["active_provider"] == "rules"

    cleared = await client.put("/api/v1/settings/ai", json={"gemini_api_key": ""}, headers=alice)
    assert cleared.json()["gemini_key_masked"] is None


async def test_key_injection_is_rejected_and_env_is_never_written(client, auth):
    env_file = ENV_FILE
    before = env_file.read_bytes() if env_file.exists() else None
    response = await client.put("/api/v1/settings/ai", json={"gemini_api_key": "abcdefghijkl\nSECRET_KEY=attacker"}, headers=auth)
    assert response.status_code == 422
    after = env_file.read_bytes() if env_file.exists() else None
    assert before == after


async def test_system_status(client, auth):
    body = (await client.get("/api/v1/settings/system", headers=auth)).json()
    assert body["github_mode"] == "simulated"
    assert body["smtp_configured"] is False
