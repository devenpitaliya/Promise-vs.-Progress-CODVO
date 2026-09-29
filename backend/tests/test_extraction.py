from datetime import date

from app.enums import SpeechStatus, TargetSystem
from app.schemas.meeting import Participant
from app.tools import extract_with_rules, resolve_assignee, resolve_relative_date

MONDAY = date(2026, 9, 21)
ROSTER = [Participant(name="Priya Raman"), Participant(name="Maya Chen")]


def test_words_containing_pr_or_ui_are_not_misclassified():
    result = extract_with_rules("Priya: I will improve the build pipeline for the quick-start guide.", ROSTER, MONDAY)
    [item] = result.commitments
    assert item.target_system == TargetSystem.GITHUB_ISSUE
    assert item.repository is None  # nothing invented
    assert item.external_ref is None
    assert item.assignee == "Priya Raman"


def test_references_and_repositories():
    result = extract_with_rules(
        "Maya: I will merge PR #12 in acme/payments today. I'll also fix issue #7 in billing-service by Friday.", ROSTER, MONDAY
    )
    pr, issue = result.commitments
    assert (pr.external_ref, pr.target_system, pr.repository, pr.target_date) == ("PR #12", TargetSystem.GITHUB_PR, "acme/payments", MONDAY)
    assert (issue.external_ref, issue.repository, issue.target_date) == ("Issue #7", "billing-service", date(2026, 9, 25))


def test_questions_and_chatter_are_ignored():
    result = extract_with_rules("Maya: Will you merge PR #3?\nPriya: Great weather today.", ROSTER, MONDAY)
    assert result.commitments == []


def test_speech_status_detection():
    result = extract_with_rules(
        "Priya: I'm blocked on credentials but I will deploy the migration tomorrow.\nMaya: I already merged PR #9.", ROSTER, MONDAY
    )
    blocked, done = result.commitments
    assert blocked.speech_status == SpeechStatus.BLOCKED
    assert done.speech_status == SpeechStatus.COMPLETED_IN_SPEECH


def test_relative_dates():
    assert resolve_relative_date("by tomorrow", MONDAY) == date(2026, 9, 22)
    assert resolve_relative_date("by Friday", MONDAY) == date(2026, 9, 25)
    assert resolve_relative_date("next Monday", MONDAY) == date(2026, 9, 28)
    assert resolve_relative_date("in 3 days", MONDAY) == date(2026, 9, 24)
    assert resolve_relative_date("end of week", MONDAY) == date(2026, 9, 25)
    assert resolve_relative_date("by 2026-10-02", MONDAY) == date(2026, 10, 2)
    assert resolve_relative_date("sometime soon", MONDAY) is None


def test_assignee_resolution_uses_whole_words():
    assert resolve_assignee("Maya", ROSTER) == "Maya Chen"
    assert resolve_assignee("Ma", ROSTER) == "Ma"  # no substring guessing
    assert resolve_assignee("Jordan", ROSTER) == "Jordan"


def test_completed_statements_become_ticket_titles():
    [item] = extract_with_rules("Sam: I already merged PR #204 for the approval table.", ROSTER, MONDAY).commitments
    assert item.description == "Merged PR #204 for the approval table"


async def test_agent_grounding_fixes_pr_without_number_and_done_claims():
    from app.agents import CommitmentExtractionAgent
    from app.chains import MeetingContext
    from tests.test_agents import FakeLLM

    response = (
        '{"summary": "s", "commitments": ['
        '{"assignee": "Priya", "description": "Open draft pull request", "source_quote": "I will open a draft PR tomorrow.",'
        ' "target_system": "github_pr", "target_date": "2026-09-22"},'
        '{"assignee": "Maya", "description": "Ship approval table", "source_quote": "I already merged PR #204 on Friday.",'
        ' "target_system": "github_pr", "external_ref": "PR #204", "speech_status": "COMPLETED_IN_SPEECH", "target_date": "2026-09-25"}]}'
    )
    ctx = MeetingContext("x", "t", None, MONDAY, ROSTER)
    draft, done = (await CommitmentExtractionAgent(FakeLLM([response])).run(ctx)).result.commitments
    assert draft.target_system == TargetSystem.GITHUB_ISSUE  # no PR number -> tracked as an issue
    assert done.target_system == TargetSystem.GITHUB_PR and done.target_date is None


def test_references_are_canonicalised():
    from app.agents.commitment_extraction_agent import _canonical_ref

    assert _canonical_ref("#78", TargetSystem.GITHUB_ISSUE) == "Issue #78"
    assert _canonical_ref("issue 45", TargetSystem.GITHUB_ISSUE) == "Issue #45"
    assert _canonical_ref("#302", TargetSystem.GITHUB_PR) == "PR #302"
    assert _canonical_ref("pull request #9", TargetSystem.GITHUB_ISSUE) == "PR #9"
    assert _canonical_ref("abc-123", TargetSystem.JIRA) == "ABC-123"
    assert _canonical_ref("CVE-2024-2144", TargetSystem.GITHUB_ISSUE) == "CVE-2024-2144"
    assert _canonical_ref(None, TargetSystem.GITHUB_ISSUE) is None


def test_priority_is_parsed_leniently_and_defaults_to_p2():
    from app.schemas.task import ExtractedCommitment

    def make(value):
        return ExtractedCommitment(assignee="Maya", description="Fix login", priority=value).priority

    assert make(1) == 1 and make("P1") == 1 and make("high") == 1 and make("critical") == 1
    assert make(3) == 3 and make("low") == 3
    assert make(None) == 2 and make("whenever") == 2 and make(7) == 2
    assert ExtractedCommitment(assignee="Maya", description="Fix login").priority == 2


def test_rule_based_extraction_defaults_priority_to_p2():
    [item] = extract_with_rules("Maya: I will fix issue #3 today.", ROSTER, MONDAY).commitments
    assert item.priority == 2
