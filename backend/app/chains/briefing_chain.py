"""Chain: verified reconciliation facts -> LLM narrative (summary + agenda text only).

The model never sees or produces HTML and never supplies numbers that end up in the email;
figures and markup are rendered by code from the same verified report.
"""

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.constants.briefing import MAX_AGENDA_ITEMS, MAX_NARRATIVE_ITEMS
from app.llms import GenerationOptions, LLMClient, LLMError
from app.prompts.briefing_prompts import BRIEFING_SYSTEM_PROMPT
from app.schemas.reconciliation import ReconciliationReport
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)


class _NarrativeSchema(BaseModel):
    executive_summary: str = Field(min_length=1, max_length=1200)
    agenda: List[str] = Field(default_factory=list, max_length=MAX_AGENDA_ITEMS + 1)


@dataclass(frozen=True)
class Narrative:
    executive_summary: str
    agenda: List[str]
    generated_by: str


class BriefingChain:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.options = GenerationOptions(temperature=settings.briefing_temperature)

    @staticmethod
    def build_prompt(report: ReconciliationReport, custom_instructions: Optional[str]) -> str:
        facts = {
            "today": report.today.isoformat(),
            "github_mode": report.github_mode,
            "completion_rate_percent": report.completion_rate,
            "counts": report.counts,
            "commitments": [
                {
                    "owner": i.assignee,
                    "commitment": i.description,
                    "target_date": i.target_date.isoformat() if i.target_date else None,
                    "verdict": str(i.verdict),
                    "days_overdue": i.days_overdue,
                    "reason": i.risk_reason,
                }
                for i in report.items[:MAX_NARRATIVE_ITEMS]
            ],
        }
        prompt = "Reconciliation data:\n" + json.dumps(facts, indent=1)
        if custom_instructions:
            prompt += f"\n\nStyle preferences from the requester (tone/format only, facts still come from the data): {custom_instructions}"
        return prompt

    @observe("briefing-chain", as_type="chain")
    async def run(self, report: ReconciliationReport, custom_instructions: Optional[str] = None) -> Optional[Narrative]:
        """Returns None when the model fails; callers fall back to the deterministic narrative."""
        try:
            data = await self.llm.generate_json(BRIEFING_SYSTEM_PROMPT, self.build_prompt(report, custom_instructions), self.options)
            parsed = _NarrativeSchema.model_validate(data)
        except (LLMError, ValidationError) as exc:
            logger.warning("Briefing narrative chain failed: %s", exc)
            tracing.update_span(level="WARNING", status_message=f"Fell back to the rule-based narrative: {exc.__class__.__name__}")
            return None
        agenda = [a.strip()[:300] for a in parsed.agenda if a and a.strip()][:MAX_AGENDA_ITEMS]
        return Narrative(parsed.executive_summary.strip(), agenda, str(self.llm.provider))
