"""Tool: deterministic commitment extraction.

Used when no LLM is configured, or as the agent's fallback. It only reports what the transcript
literally contains; it never fills gaps with invented people, tickets or repositories.
"""

import re
from datetime import date
from typing import List, Optional, Sequence

from app.enums import SpeechStatus, TargetSystem
from app.schemas.meeting import Participant
from app.schemas.task import ExtractedCommitment, ExtractionResult
from app.tools.assignee_resolver import resolve_assignee
from app.tools.date_resolver import resolve_relative_date
from app.utils.tracing import observe

_SPEAKER_LINE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)?([A-Z][\w .'-]{0,40}?)\s*:\s*(.+)$")
_COMMITMENT = re.compile(
    r"\b(i will|i'll|i am going to|i'm going to|i can take|let me take|i commit to|i promise to|"
    r"i'm on it|i am on it|will (?:merge|fix|deploy|ship|review|finish|resolve|patch|update|write|add|"
    r"implement|land|push|release|investigate|migrate|provision))\b",
    re.IGNORECASE,
)
_DONE_ALREADY = re.compile(
    r"\b(i (?:already )?(?:merged|shipped|deployed|fixed|closed|finished|released)|already (?:merged|done|shipped|fixed))\b",
    re.IGNORECASE,
)
_BLOCKED = re.compile(r"\b(blocked|waiting on|waiting for|depends on)\b", re.IGNORECASE)
_PR_REF = re.compile(r"\b(?:pr|pull request)\s*(?:#|no\.?\s*)?(\d+)\b", re.IGNORECASE)
_ISSUE_REF = re.compile(r"\b(?:issue|ticket|bug)\s*(?:#|no\.?\s*)?(\d+)\b", re.IGNORECASE)
_JIRA_REF = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
_MERGE = re.compile(r"\bmerg(?:e|ing)\b", re.IGNORECASE)
_EXPLICIT_REPO = re.compile(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b")
_SERVICE_REPO = re.compile(
    r"\b([a-z0-9]+(?:-[a-z0-9]+)*-(?:service|core|web|api|app|gateway|worker|infra|ui|backend|frontend|"
    r"migrations|lib|sdk|cli|portal))\b",
    re.IGNORECASE,
)
_LEADING_FILLER = re.compile(
    r"^(?:(?:ok(?:ay)?|so|yeah|yes|sure|got it|awesome|great|sounds good|perfect|team|on my end|"
    r"and|also|then)[,.!]?\s+)*(?:i will|i'll|i am going to|i'm going to|i can take|let me take|"
    r"i commit to|i promise to)?\s*",
    re.IGNORECASE,
)
_MAX_TITLE = 160


def _clean_description(sentence: str) -> str:
    text = _LEADING_FILLER.sub("", sentence.strip()).strip(" .")
    # "I already merged PR #204" -> "Merged PR #204"
    text = re.sub(r"^i\s+(?:already\s+)?(?=[a-z]+ed\b)", "", text, flags=re.IGNORECASE)
    if not text:
        text = sentence.strip(" .")
    text = text[0].upper() + text[1:] if text else text
    return text if len(text) <= _MAX_TITLE else text[: _MAX_TITLE - 3].rstrip() + "..."


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _classify(sentence: str) -> tuple[TargetSystem, Optional[str]]:
    pr, issue, jira = _PR_REF.search(sentence), _ISSUE_REF.search(sentence), _JIRA_REF.search(sentence)
    if pr or (_MERGE.search(sentence) and not issue):
        system = TargetSystem.GITHUB_PR
    elif jira and not issue:
        system = TargetSystem.JIRA
    else:
        system = TargetSystem.GITHUB_ISSUE

    if pr:
        return system, f"PR #{pr.group(1)}"
    if issue:
        return system, f"Issue #{issue.group(1)}"
    if jira:
        return system, jira.group(1)
    return system, None


@observe("rule-based-extractor", as_type="tool")
def extract_with_rules(transcript: str, participants: Sequence[Participant], meeting_date: date) -> ExtractionResult:
    commitments: List[ExtractedCommitment] = []
    speaker: Optional[str] = None
    speakers_seen = set()

    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            speaker, content = match.group(1).strip(), match.group(2).strip()
        else:
            content = line
        if not speaker:
            continue  # commitments without an identifiable owner are not trackable

        for sentence in _split_sentences(content):
            if sentence.endswith("?"):
                continue
            done = bool(_DONE_ALREADY.search(sentence))
            if not (_COMMITMENT.search(sentence) or done):
                continue

            target_system, external_ref = _classify(sentence)
            repo_match = _EXPLICIT_REPO.search(sentence) or _SERVICE_REPO.search(sentence)
            if done:
                speech_status = SpeechStatus.COMPLETED_IN_SPEECH
            elif _BLOCKED.search(content):  # a blocker mentioned anywhere in the same turn
                speech_status = SpeechStatus.BLOCKED
            else:
                speech_status = SpeechStatus.PROPOSED

            assignee = resolve_assignee(speaker, participants)
            speakers_seen.add(assignee)
            commitments.append(
                ExtractedCommitment(
                    assignee=assignee,
                    description=_clean_description(sentence),
                    source_quote=f"{speaker}: {sentence}",
                    target_date=resolve_relative_date(sentence, meeting_date),
                    target_system=target_system,
                    repository=repo_match.group(1) if repo_match else None,
                    external_ref=external_ref,
                    speech_status=speech_status,
                )
            )

    if commitments:
        summary = (
            f"Rule-based extraction found {len(commitments)} commitment(s) from {len(speakers_seen)} speaker(s). "
            "Configure an AI key for richer summaries and ticket titles."
        )
    else:
        summary = "No explicit commitments were detected in this transcript."
    return ExtractionResult(summary=summary, commitments=commitments)
