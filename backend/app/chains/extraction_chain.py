"""Chain: meeting context -> extraction prompt -> LLM (JSON mode) -> validated ExtractionResult."""

from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from pydantic import ValidationError

from app.config import settings
from app.llms import GenerationOptions, LLMClient, LLMError
from app.prompts.extraction_prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt, build_repair_prompt
from app.schemas.meeting import Participant
from app.schemas.task import ExtractionResult
from app.utils import tracing
from app.utils.tracing import observe


class ExtractionChainError(Exception):
    """The model answered, but not with a usable result. `retryable` means a repair prompt may help."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class MeetingContext:
    transcript: str
    title: str
    meeting_type: Optional[str]
    meeting_date: date
    participants: Sequence[Participant]


class ExtractionChain:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.options = GenerationOptions(temperature=settings.extraction_temperature)

    def build_prompt(self, context: MeetingContext) -> str:
        roster = "\n".join(f"- {p.name}" + (f" ({p.role})" if p.role else "") for p in context.participants)
        return build_extraction_prompt(
            transcript=context.transcript,
            title=context.title,
            meeting_type=context.meeting_type or "Meeting",
            meeting_date=context.meeting_date,
            roster=roster or "(not provided)",
        )

    @observe("extraction-chain", as_type="chain")
    async def run(self, context: MeetingContext, previous_error: Optional[str] = None) -> ExtractionResult:
        tracing.update_span(
            metadata={"repair_attempt": previous_error is not None},
            input=tracing.content(
                {"title": context.title, "meeting_date": context.meeting_date.isoformat(), "transcript": context.transcript}
            ),
        )
        prompt = self.build_prompt(context)
        if previous_error:
            prompt = build_repair_prompt(prompt, previous_error)
        try:
            data = await self.llm.generate_json(EXTRACTION_SYSTEM_PROMPT, prompt, self.options)
        except LLMError as exc:
            # Invalid JSON is worth a repair attempt; timeouts and auth errors are not.
            raise ExtractionChainError(str(exc), retryable="invalid JSON" in str(exc) or "not an object" in str(exc)) from exc
        try:
            result = ExtractionResult.model_validate(data)
        except ValidationError as exc:
            raise ExtractionChainError(str(exc), retryable=True) from exc
        tracing.update_span(output=tracing.content(result.model_dump(mode="json")))
        return result
