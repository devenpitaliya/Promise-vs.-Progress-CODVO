"""Notifier-neutral messages built from verified data: the pre-meeting briefing and due-soon reminders."""

from collections import defaultdict
from typing import Dict, List, Optional

from app.config import settings
from app.enums import Verdict
from app.schemas.briefing import BriefingPreview
from app.schemas.reconciliation import ReconciliationItem, ReconciliationReport
from app.services.connectors import Message
from app.services.connectors.slack import escape

MAX_REMINDER_ITEMS = 25
REMINDER_VERDICTS = (Verdict.OVERDUE, Verdict.DUE_TODAY, Verdict.AT_RISK, Verdict.BLOCKED, Verdict.CLAIMED_UNVERIFIED)
VERDICT_LABEL = {
    Verdict.OVERDUE: ":red_circle: Overdue",
    Verdict.DUE_TODAY: ":large_orange_circle: Due today",
    Verdict.AT_RISK: ":large_yellow_circle: At risk",
    Verdict.BLOCKED: ":no_entry: Blocked",
    Verdict.CLAIMED_UNVERIFIED: ":grey_question: Claimed done, not verified",
}


def _app_link(path: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/{path}"


def _ref(item: ReconciliationItem) -> str:
    ref = item.external_key or item.external_ref
    if not ref:
        return ""
    text = escape(ref)
    return f" (<{item.github_url}|{text}>)" if item.github_url else f" ({text})"


def _timing(item: ReconciliationItem) -> str:
    if item.days_overdue:
        return f"{item.days_overdue}d overdue"
    if item.target_date:
        return f"due {item.target_date.strftime('%d %b')}"
    return "no due date"


def briefing_message(preview: BriefingPreview) -> Message:
    c = preview.counts
    attention = c.get(Verdict.OVERDUE, 0) + c.get(Verdict.DUE_TODAY, 0) + c.get(Verdict.BLOCKED, 0)
    lines = [
        escape(preview.executive_summary),
        "",
        f"*{preview.completion_rate}%* verified done · *{attention}* overdue, due today or blocked · "
        f"*{c.get(Verdict.CLAIMED_UNVERIFIED, 0)}* claimed but not verified",
    ]
    if preview.agenda:
        lines += ["", "*Agenda*"] + [f"{i}. {escape(a)}" for i, a in enumerate(preview.agenda, 1)]
    if preview.github_mode == "simulated":
        lines += ["", "_GitHub is simulated for this workspace; statuses come from simulated events._"]
    return Message(title=preview.subject, lines=lines, link=_app_link("reconciliation"), link_label="Open reconciliation")


def reminder_message(report: ReconciliationReport, scope: str) -> Optional[Message]:
    """Commitments that need attention, grouped by owner, highest risk first. None when nothing is due."""
    items = [i for i in report.items if i.verdict in REMINDER_VERDICTS][:MAX_REMINDER_ITEMS]
    if not items:
        return None
    by_owner: Dict[str, List[ReconciliationItem]] = defaultdict(list)
    for item in items:
        by_owner[item.assignee].append(item)
    lines: List[str] = []
    for owner, owned in by_owner.items():
        lines.append(f"*{escape(owner)}*")
        lines += [f"• {VERDICT_LABEL[i.verdict]} · P{int(i.priority)} · {escape(i.description)}{_ref(i)} · {_timing(i)}" for i in owned]
        lines.append("")
    hidden = sum(1 for i in report.items if i.verdict in REMINDER_VERDICTS) - len(items)
    if hidden > 0:
        lines.append(f"_…and {hidden} more in the app._")
    return Message(
        title=f"Commitments needing attention: {scope}",
        lines=lines,
        link=_app_link("reconciliation"),
        link_label="Open reconciliation",
    )
