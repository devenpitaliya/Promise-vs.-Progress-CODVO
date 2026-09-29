import pytest
from pydantic import ValidationError

from app.config import Settings, settings


def make(**env):
    return Settings(_env_file=None, **env)


def test_values_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("APP_PORT", "9100")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.35")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "2048")
    monkeypatch.setenv("FRONTEND_URL", "https://pvp.example.com/")
    monkeypatch.setenv("CORS_ORIGINS", "https://admin.example.com, https://pvp.example.com")
    config = Settings(_env_file=None)
    assert config.APP_PORT == 9100
    assert config.LLM_TEMPERATURE == 0.35
    assert config.LLM_MAX_OUTPUT_TOKENS == 2048
    assert config.allowed_origins == ["https://pvp.example.com", "https://admin.example.com"]


def test_task_temperatures_default_to_the_shared_value():
    config = make(LLM_TEMPERATURE=0.3, EXTRACTION_TEMPERATURE="", BRIEFING_TEMPERATURE=0.6)
    assert config.extraction_temperature == 0.3
    assert config.briefing_temperature == 0.6


@pytest.mark.parametrize(
    "env",
    [
        {"LLM_TEMPERATURE": 3},
        {"APP_PORT": 70000},
        {"ENVIRONMENT": "production", "SECRET_KEY": "short"},
        {"EMBEDDING_PROVIDER": "gemini", "GEMINI_API_KEY": ""},
    ],
)
def test_invalid_configuration_fails_fast(env):
    with pytest.raises(ValidationError):
        make(**env)


def test_api_prefix_is_normalised():
    assert make(API_PREFIX="api/v2/").API_PREFIX == "/api/v2"


async def test_public_config_endpoint_exposes_limits_without_auth(client):
    body = (await client.get(f"{settings.API_PREFIX}/config")).json()
    assert body["max_transcript_chars"] == settings.MAX_TRANSCRIPT_CHARS
    assert body["password_min_length"] == settings.PASSWORD_MIN_LENGTH
    assert "SECRET_KEY" not in str(body)
