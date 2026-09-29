"""Agent / chain behaviour with a scripted fake LLM (no network)."""

from datetime import date

import pytest

from app.agents import CommitmentExtractionAgent
from app.chains import BriefingChain, ExtractionChain, MeetingContext
from app.config import settings
from app.enums import LLMProvider
from app.llms import GenerationOptions, LLMClient, LLMCredentials, LLMError
from app.llms.base import reset_model_cooldowns
from app.schemas.meeting import Participant
from app.services.reconciliation_service import build_report


class FakeLLM(LLMClient):
    """Returns scripted responses in order; an Exception entry is raised instead."""

    def __init__(self, responses, fallback_model=None):
        super().__init__(
            LLMCredentials(provider=LLMProvider.GEMINI, api_key="fake-key-123456", model="fake", fallback_model=fallback_model)
        )
        self.responses = list(responses)
        self.calls: list[tuple[str, GenerationOptions]] = []
        self.models: list[str] = []

    async def _complete(self, system_prompt, user_prompt, options, model):
        self.calls.append((user_prompt, options))
        self.models.append(model)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


CONTEXT = MeetingContext(
    transcript="Maya: I will merge PR #12 in acme/api by Friday.",
    title="Standup",
    meeting_type="Standup",
    meeting_date=date(2026, 9, 21),  # Monday
    participants=[Participant(name="Maya Chen")],
)

VALID = '{"summary": "One commitment.", "commitments": [{"assignee": "Maya", "description": "Merge PR #12", "source_quote": "Maya: I will merge PR #12 in acme/api by Friday.", "target_system": "github_pr", "external_ref": "PR #12"}]}'


async def test_agent_uses_llm_and_grounds_the_result():
    llm = FakeLLM([VALID])
    outcome = await CommitmentExtractionAgent(llm).run(CONTEXT)
    [item] = outcome.result.commitments
    assert outcome.source == "gemini"
    assert item.assignee == "Maya Chen"  # mapped to the roster by the assignee tool
    assert item.target_date == date(2026, 9, 25)  # deadline the model missed, filled by the date tool
    assert any("missing deadline" in step for step in outcome.trace)


async def test_agent_repairs_invalid_output_before_giving_up():
    llm = FakeLLM(['{"summary": "x", "commitments": [{"description": "no owner"}]}', VALID])
    outcome = await CommitmentExtractionAgent(llm, max_repair_attempts=1).run(CONTEXT)
    assert outcome.source == "gemini"
    assert len(llm.calls) == 2
    assert "did not match the required JSON schema" in llm.calls[1][0]


async def test_agent_falls_back_to_rules_when_llm_keeps_failing():
    llm = FakeLLM(["not json", "still not json"])
    outcome = await CommitmentExtractionAgent(llm, max_repair_attempts=1).run(CONTEXT)
    assert outcome.source == "rules"
    assert outcome.result.commitments[0].external_ref == "PR #12"
    assert outcome.trace[-1].startswith("Rule-based extractor found")


async def test_agent_does_not_retry_non_repairable_errors():
    llm = FakeLLM([LLMError("gemini request failed: AuthenticationError"), VALID])
    outcome = await CommitmentExtractionAgent(llm, max_repair_attempts=2).run(CONTEXT)
    assert outcome.source == "rules"
    assert len(llm.calls) == 1


async def test_agent_without_llm_uses_rules():
    outcome = await CommitmentExtractionAgent(None).run(CONTEXT)
    assert outcome.source == "rules"


@pytest.mark.parametrize("override", [None, 0.7])
async def test_chain_temperature_comes_from_settings(monkeypatch, override):
    monkeypatch.setattr(settings, "LLM_TEMPERATURE", 0.2)
    monkeypatch.setattr(settings, "EXTRACTION_TEMPERATURE", override)
    llm = FakeLLM([VALID])
    await ExtractionChain(llm).run(CONTEXT)
    assert llm.calls[0][1].temperature == (0.2 if override is None else 0.7)


async def test_briefing_chain_uses_briefing_temperature_and_falls_back_on_bad_output(monkeypatch):
    monkeypatch.setattr(settings, "BRIEFING_TEMPERATURE", 0.4)
    llm = FakeLLM(['{"agenda": []}'])  # missing executive_summary
    narrative = await BriefingChain(llm).run(build_report([]))
    assert narrative is None
    assert llm.calls[0][1].temperature == 0.4


class ProviderError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


async def test_transient_provider_errors_are_retried():
    llm = FakeLLM([ProviderError(503, "high demand"), ProviderError(429, "rate limited"), VALID])
    data = await llm.generate_json("s", "p")
    assert data["summary"] == "One commitment."
    assert len(llm.calls) == 3


async def test_permanent_provider_errors_fail_fast_with_details():
    llm = FakeLLM([ProviderError(404, "model models/old-model is no longer available"), VALID])
    with pytest.raises(LLMError, match="HTTP 404 - model models/old-model is no longer available"):
        await llm.generate_json("s", "p")
    assert len(llm.calls) == 1


async def test_error_details_never_contain_the_api_key():
    llm = FakeLLM([ProviderError(400, "invalid key fake-key-123456 supplied")])
    with pytest.raises(LLMError) as info:
        await llm.generate_json("s", "p")
    assert "fake-key-123456" not in str(info.value)


async def test_overloaded_model_switches_to_fallback_model():
    busy = ProviderError(503, "high demand")
    llm = FakeLLM([busy, busy, busy, VALID], fallback_model="fake-lite")  # 2 retries exhausted on the primary
    data = await llm.generate_json("s", "p")
    assert data["summary"] == "One commitment."
    assert llm.models == ["fake", "fake", "fake", "fake-lite"]
    assert llm.last_model == "fake-lite"


async def test_permanent_errors_do_not_use_the_fallback_model():
    llm = FakeLLM([ProviderError(404, "model not found"), VALID], fallback_model="fake-lite")
    with pytest.raises(LLMError, match="HTTP 404"):
        await llm.generate_json("s", "p")
    assert llm.models == ["fake"]


async def test_both_models_overloaded_raises_llm_error():
    busy = ProviderError(503, "high demand")
    llm = FakeLLM([busy] * 6, fallback_model="fake-lite")
    with pytest.raises(LLMError, match="HTTP 503"):
        await llm.generate_json("s", "p")
    assert llm.models == ["fake"] * 3 + ["fake-lite"] * 3


async def test_quota_exhaustion_skips_retries_and_cools_the_model_down():
    reset_model_cooldowns()
    quota = ProviderError(429, "You exceeded your current quota, please check your plan")
    llm = FakeLLM([quota, VALID, VALID], fallback_model="fake-lite")
    await llm.generate_json("s", "p")
    assert llm.models == ["fake", "fake-lite"]  # no retries on the exhausted model

    await llm.generate_json("s", "p")  # next call skips the cooled-down model entirely
    assert llm.models == ["fake", "fake-lite", "fake-lite"]
    reset_model_cooldowns()


async def test_plain_rate_limits_are_still_retried():
    reset_model_cooldowns()
    llm = FakeLLM([ProviderError(429, "Too many requests"), VALID], fallback_model="fake-lite")
    await llm.generate_json("s", "p")
    assert llm.models == ["fake", "fake"]
