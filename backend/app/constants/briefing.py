from app.enums import Verdict

# (label, badge background, badge foreground) used in the briefing email.
VERDICT_STYLE = {
    Verdict.VERIFIED_DONE: ("Verified done", "#dcfce7", "#166534"),
    Verdict.CLAIMED_UNVERIFIED: ("Claimed, unverified", "#fef3c7", "#92400e"),
    Verdict.OVERDUE: ("Overdue", "#fee2e2", "#991b1b"),
    Verdict.DUE_TODAY: ("Due today", "#ffedd5", "#9a3412"),
    Verdict.BLOCKED: ("Blocked", "#fee2e2", "#991b1b"),
    Verdict.AT_RISK: ("At risk", "#fef3c7", "#92400e"),
    Verdict.ON_TRACK: ("On track", "#dbeafe", "#1e40af"),
    Verdict.NO_DEADLINE: ("No deadline", "#f1f5f9", "#475569"),
    Verdict.CANCELLED: ("Cancelled", "#f1f5f9", "#64748b"),
}

# Verdicts that belong on the meeting agenda, most urgent first.
AGENDA_VERDICTS = (Verdict.BLOCKED, Verdict.OVERDUE, Verdict.DUE_TODAY, Verdict.CLAIMED_UNVERIFIED, Verdict.AT_RISK)
MAX_AGENDA_ITEMS = 5
# Commitments sent to the LLM for the narrative (the email table always lists all of them).
MAX_NARRATIVE_ITEMS = 60
