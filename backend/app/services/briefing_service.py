"""Briefing rendering: deterministic narrative and autoescaped HTML from a verified report."""

from pathlib import Path
from typing import List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.constants.briefing import AGENDA_VERDICTS, MAX_AGENDA_ITEMS, VERDICT_STYLE
from app.enums import Verdict
from app.schemas.reconciliation import ReconciliationReport

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

_PROVIDER_LABEL = {"gemini": "Gemini", "openai": "OpenAI"}


def deterministic_narrative(report: ReconciliationReport) -> Tuple[str, List[str]]:
    """Summary and agenda built from counts alone; used when no LLM is configured or it fails."""
    c = report.counts
    if report.total == 0:
        return "No approved commitments are being tracked yet.", []

    parts = [f"{c[Verdict.VERIFIED_DONE]} of {report.total} commitments are verified done in GitHub ({report.completion_rate}%)."]
    slipping = c[Verdict.OVERDUE] + c[Verdict.DUE_TODAY] + c[Verdict.BLOCKED]
    if slipping:
        parts.append(
            f"{slipping} need attention: {c[Verdict.OVERDUE]} overdue, {c[Verdict.DUE_TODAY]} due today, {c[Verdict.BLOCKED]} blocked."
        )
    if c[Verdict.CLAIMED_UNVERIFIED]:
        parts.append(f"{c[Verdict.CLAIMED_UNVERIFIED]} are reported done but not yet confirmed by GitHub.")
    if not slipping and not c[Verdict.CLAIMED_UNVERIFIED]:
        parts.append("Nothing is overdue or blocked.")

    agenda = [
        f"{item.assignee}: {item.description} ({VERDICT_STYLE[item.verdict][0].lower()})"
        for item in report.items
        if item.verdict in AGENDA_VERDICTS
    ][: MAX_AGENDA_ITEMS - 1]
    if c[Verdict.NO_DEADLINE]:
        agenda.append(f"Agree target dates for {c[Verdict.NO_DEADLINE]} commitment(s) without one.")
    return " ".join(parts), agenda


def render_html(
    report: ReconciliationReport,
    *,
    subject: str,
    scope_title: str,
    executive_summary: str,
    agenda: List[str],
    generated_by: str,
    recipient_name: Optional[str] = None,
) -> str:
    c = report.counts
    metrics = [
        {"label": "Verified done", "value": c[Verdict.VERIFIED_DONE], "color": "#16a34a"},
        {"label": "Overdue / due today", "value": c[Verdict.OVERDUE] + c[Verdict.DUE_TODAY], "color": "#dc2626"},
        {"label": "Blocked", "value": c[Verdict.BLOCKED], "color": "#dc2626"},
        {"label": "Claimed, unverified", "value": c[Verdict.CLAIMED_UNVERIFIED], "color": "#d97706"},
        {"label": "Completion", "value": f"{report.completion_rate}%", "color": "#1d4ed8"},
    ]
    items = []
    for item in report.items:
        label, bg, fg = VERDICT_STYLE[item.verdict]
        ref = item.external_key or item.external_ref or (item.repository or "—")
        if item.is_simulated:
            ref = f"{ref} (simulated)"
        items.append(
            {
                "verdict_label": label,
                "badge_bg": bg,
                "badge_fg": fg,
                "priority": f"P{item.priority}",
                "priority_color": {1: "#b91c1c", 2: "#b45309", 3: "#475569"}[int(item.priority)],
                "assignee": item.assignee,
                "description": item.description,
                "meeting_title": item.meeting_title,
                "target_display": item.target_date.strftime("%d %b %Y") if item.target_date else "Not set",
                "ref_display": ref,
                "github_url": item.github_url if (item.github_url or "").startswith("https://") else None,
                "risk_reason": item.risk_reason,
            }
        )
    return _templates.get_template("briefing_email.html").render(
        subject=subject,
        scope_title=scope_title,
        today_display=report.today.strftime("%d %b %Y"),
        timezone=report.timezone,
        github_mode=report.github_mode,
        recipient_name=recipient_name,
        executive_summary=executive_summary,
        agenda=agenda,
        metrics=metrics,
        items=items,
        generated_by_label=_PROVIDER_LABEL.get(generated_by, "rules"),
    )
