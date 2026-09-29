"""Langfuse tracing: off by default, complete when on, and never able to break a request."""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agents.commitment_extraction_agent import CommitmentExtractionAgent
from app.config import settings
from app.utils import tracing
from tests.conftest import create_meeting
from tests.test_agents import CONTEXT, VALID, FakeLLM

EXPORTER = InMemorySpanExporter()
_langfuse = None


def _client():
    """One in-memory Langfuse client for the whole module (OpenTelemetry providers cannot be reset)."""
    global _langfuse
    if _langfuse is None:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key="pk-lf-test", secret_key="sk-lf-test", base_url="http://127.0.0.1:9", span_exporter=EXPORTER, flush_at=1
        )
    return _langfuse


@pytest.fixture
def traced(monkeypatch):
    monkeypatch.setattr(tracing, "_client", _client())
    monkeypatch.setattr(tracing, "_project_id", "proj-1")
    EXPORTER.clear()
    yield EXPORTER
    _client().flush()


def spans():
    _client().flush()
    return {s.name: s for s in EXPORTER.get_finished_spans()}


def test_disabled_by_default():
    assert settings.LANGFUSE_ENABLED is False
    assert tracing.init_tracing() == "disabled (LANGFUSE_ENABLED=false)"
    assert not tracing.is_enabled()
    assert tracing.trace_url("abc") is None
    tracing.record_usage("m", 10, 5)  # no-ops without a client


def test_missing_keys_leave_tracing_off(monkeypatch):
    monkeypatch.setattr(settings, "LANGFUSE_ENABLED", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    assert "required" in tracing.init_tracing()
    assert not tracing.is_enabled()


async def test_app_works_with_tracing_off(client, auth):
    meeting = await create_meeting(client, auth)
    assert meeting["tasks"] and meeting["trace_url"] is None


async def test_ingestion_is_one_trace_with_nested_steps(client, auth, traced):
    meeting = await create_meeting(client, auth)
    found = spans()
    for name in ("meeting-ingestion", "commitment-extraction-agent", "rule-based-extractor", "vector-index"):
        assert name in found, sorted(found)
    root = found["meeting-ingestion"]
    assert {s.context.trace_id for s in found.values()} == {root.context.trace_id}
    assert root.attributes.get("user.id") == "1" or any("1" == v for k, v in root.attributes.items() if "user" in k)
    assert meeting["trace_url"] == f"{settings.LANGFUSE_BASE_URL}/project/proj-1/traces/{format(root.context.trace_id, '032x')}"


async def test_llm_calls_record_model_tokens_and_cost(traced, monkeypatch):
    monkeypatch.setattr(settings, "LLM_PRICING", "fake=1/2")
    settings.__dict__.pop("llm_pricing", None)

    class MeteredLLM(FakeLLM):
        async def _complete(self, system_prompt, user_prompt, options, model):
            text = await super()._complete(system_prompt, user_prompt, options, model)
            tracing.record_usage(model, 1000, 500)
            return text

    await CommitmentExtractionAgent(MeteredLLM([VALID])).run(CONTEXT)
    settings.__dict__.pop("llm_pricing", None)
    generation = spans()["llm-generation"]
    attributes = {k: str(v) for k, v in generation.attributes.items()}
    joined = " ".join(f"{k}={v}" for k, v in attributes.items())
    assert "fake" in joined  # model
    assert '"input": 1000' in joined and '"output": 500' in joined  # tokens
    assert "0.002" in joined  # cost: 1000 * $1/1M + 500 * $2/1M
    assert {"extraction-chain", "llm-call", "grounding"} <= spans().keys()


async def test_a_broken_tracing_backend_never_fails_requests(client, auth, traced, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("langfuse down")

    for method in ("update_current_span", "update_current_generation", "get_current_trace_id"):
        monkeypatch.setattr(_client(), method, boom)
    meeting = await create_meeting(client, auth)
    ids = [t["id"] for t in meeting["tasks"]]
    review = await client.post(f"/api/v1/commitments/review?meeting_id={meeting['id']}", json={"approve_ids": ids[:1]}, headers=auth)
    assert review.status_code == 200


def test_pricing_is_validated():
    from app.config.settings import parse_pricing

    assert parse_pricing("a=1/2, b=0.5/1.5") == {"a": (1.0, 2.0), "b": (0.5, 1.5)}
    with pytest.raises(ValueError):
        parse_pricing("a=1")
