"""Agent: turn a transcript into commitments, choosing and correcting its own strategy.

Loop:
1. If an LLM is available, run the extraction chain.
2. If the output fails validation, feed the error back and retry (LLM_MAX_REPAIR_ATTEMPTS).
3. Ground the result with deterministic tools: map speakers to the roster and fill deadlines the
   model missed from the quoted sentence.
4. If the LLM is unavailable or keeps failing, fall back to the rule-based extraction tool.

Every step is recorded in `trace`, so the outcome is explainable and never silently degraded.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.chains.extraction_chain import ExtractionChain, ExtractionChainError, MeetingContext
from app.config import settings
from app.enums import SpeechStatus, TargetSystem
from app.llms import LLMClient
from app.schemas.task import ExtractionResult
from app.tools.assignee_resolver import resolve_assignee
from app.tools.date_resolver import resolve_relative_date
from app.tools.rule_based_extractor import extract_with_rules
from app.utils import tracing
from app.utils.tracing import observe

logger = logging.getLogger(__name__)

_PR_NUMBER = re.compile(r"\b(?:pr|pull request)\s*#?\s*\d+", re.IGNORECASE)


def _canonical_ref(ref: Optional[str], target_system: TargetSystem) -> Optional[str]:
    """'#78' / 'issue #78' / 'pr 302' -> 'Issue #78' / 'PR #302'; Jira keys are upper-cased."""
    if not ref:
        return None
    ref = ref.strip()
    jira = re.fullmatch(r"([A-Za-z][A-Za-z0-9]{1,9})-(\d+)", ref)
    if jira:
        return f"{jira.group(1).upper()}-{jira.group(2)}"
    number = re.fullmatch(r"(?i)(pr|pull request|issue|ticket|bug)?\s*#?\s*(\d+)", ref)
    if not number:
        return ref
    kind = (number.group(1) or "").lower()
    is_pr = kind in ("pr", "pull request") or (not kind and target_system == TargetSystem.GITHUB_PR)
    return f"{'PR' if is_pr else 'Issue'} #{number.group(2)}"


@dataclass
class AgentOutcome:
    result: ExtractionResult
    source: str  # "gemini" | "openai" | "rules"
    trace: List[str] = field(default_factory=list)


class CommitmentExtractionAgent:
    def __init__(self, llm: Optional[LLMClient], max_repair_attempts: Optional[int] = None):
        self.llm = llm
        self.max_repair_attempts = settings.LLM_MAX_REPAIR_ATTEMPTS if max_repair_attempts is None else max_repair_attempts

    @observe("commitment-extraction-agent", as_type="agent")
    async def run(self, context: MeetingContext) -> AgentOutcome:
        outcome = await self._run(context)
        tracing.update_span(
            output={"source": outcome.source, "commitments": len(outcome.result.commitments)},
            metadata={"steps": outcome.trace},
            level="WARNING" if self.llm is not None and outcome.source == "rules" else None,
            status_message="LLM failed; used the rule-based extractor" if self.llm is not None and outcome.source == "rules" else None,
        )
        return outcome

    async def _run(self, context: MeetingContext) -> AgentOutcome:
        trace: List[str] = []
        if self.llm is not None:
            result = await self._run_llm(context, trace)
            if result is not None:
                return AgentOutcome(self._ground(result, context, trace), str(self.llm.provider), trace)
        else:
            trace.append("No LLM configured; using the rule-based extractor.")

        result = extract_with_rules(context.transcript, context.participants, context.meeting_date)
        trace.append(f"Rule-based extractor found {len(result.commitments)} commitment(s).")
        return AgentOutcome(result, "rules", trace)

    async def _run_llm(self, context: MeetingContext, trace: List[str]) -> Optional[ExtractionResult]:
        chain = ExtractionChain(self.llm)
        error: Optional[str] = None
        for attempt in range(self.max_repair_attempts + 1):
            try:
                result = await chain.run(context, previous_error=error)
                engine = f"{self.llm.provider} ({self.llm.last_model})"
                trace.append(f"{engine} extracted {len(result.commitments)} commitment(s) on attempt {attempt + 1}.")
                return result
            except ExtractionChainError as exc:
                error = str(exc)
                trace.append(f"{self.llm.provider} attempt {attempt + 1} failed: {error.splitlines()[0][:200]}")
                logger.warning("Extraction attempt %s failed: %s", attempt + 1, error.splitlines()[0])
                if not exc.retryable:
                    break
        trace.append("Falling back to the rule-based extractor.")
        return None

    @staticmethod
    @observe("grounding", as_type="tool")
    def _ground(result: ExtractionResult, context: MeetingContext, trace: List[str]) -> ExtractionResult:
        """Deterministic corrections so ticket correctness never depends on the model obeying every rule."""
        filled = downgraded = 0
        for item in result.commitments:
            item.assignee = resolve_assignee(item.assignee, context.participants)

            if item.speech_status == SpeechStatus.COMPLETED_IN_SPEECH:
                # A claim about finished work has no deadline ("merged on Friday" is in the past).
                item.target_date = None
            elif item.target_date is None and item.source_quote:
                item.target_date = resolve_relative_date(item.source_quote, context.meeting_date)
                filled += item.target_date is not None

            item.external_ref = _canonical_ref(item.external_ref, item.target_system)

            # A PR can only be tracked by number; without one, track the work as an issue.
            if item.target_system == TargetSystem.GITHUB_PR and not _PR_NUMBER.search(item.external_ref or ""):
                item.target_system = TargetSystem.GITHUB_ISSUE
                downgraded += 1

        tracing.update_span(output={"deadlines_filled": filled, "prs_tracked_as_issues": downgraded})
        if filled:
            trace.append(f"Resolved {filled} missing deadline(s) from the quoted sentences.")
        if downgraded:
            trace.append(f"Tracked {downgraded} PR commitment(s) without a PR number as issues.")
        return result
