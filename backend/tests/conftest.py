import os
import tempfile

# Isolate every test run from local data and secrets before the app is imported.
_TEST_DIR = tempfile.mkdtemp(prefix="pvp-tests-")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATA_DIR": _TEST_DIR,
        # SQLite by default; set TEST_DATABASE_URL (e.g. postgresql+asyncpg://...) to run the suite on Postgres.
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", ""),
        "SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
        "RUN_MIGRATIONS_ON_STARTUP": "false",
        "ENABLE_SCHEDULER": "false",
        "DEMO_MODE": "false",
        "GEMINI_API_KEY": "",
        "OPENAI_API_KEY": "",
        "GITHUB_PERSONAL_ACCESS_TOKEN": "",
        "GITHUB_DEFAULT_OWNER": "",
        "SMTP_HOST": "",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "APP_TIMEZONE": "UTC",
        "LOG_DIR": os.path.join(_TEST_DIR, "logs"),
        "LOG_TO_CONSOLE": "false",
        "STARTUP_CHECK_LLM": "false",
        "LLM_RETRY_BACKOFF_SECONDS": "0",
        "LANGFUSE_ENABLED": "false",
        # Jira and Slack are "coming soon" by default; the suite still exercises their connectors.
        "ENABLED_INTEGRATIONS": "github,jira,slack",
    }
)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.constants.sample_transcripts import sample_transcripts  # noqa: E402
from app.controllers.auth_controller import login_limiter, signup_limiter  # noqa: E402
from app.controllers.settings_controller import key_test_limiter  # noqa: E402
from app.database.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "Str0ng-password"


@pytest_asyncio.fixture(autouse=True)
async def fresh_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    for limiter in (login_limiter, signup_limiter, key_test_limiter):
        limiter.reset()
    yield
    # Each test runs in its own event loop; pooled connections (asyncpg) must not outlive it.
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def register(client: AsyncClient, email: str = "lead@example.com", name: str = "Maya Chen") -> dict:
    response = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": name})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth(client):
    return await register(client)


async def create_meeting(client: AsyncClient, headers: dict, sample_index: int = 0, **overrides) -> dict:
    sample = sample_transcripts()[sample_index]
    payload = {
        "title": sample.title,
        "meeting_type": sample.meeting_type,
        "meeting_date": "2026-09-21",
        "meeting_time": "10:00",
        "participants": [p.model_dump() for p in sample.participants],
        "transcript": sample.transcript,
    }
    payload.update(overrides)
    response = await client.post("/api/v1/meetings/", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def approve_all(client: AsyncClient, headers: dict, meeting: dict) -> dict:
    ids = [t["id"] for t in meeting["tasks"]]
    response = await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": ids}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def anyio_backend():
    return "asyncio"
