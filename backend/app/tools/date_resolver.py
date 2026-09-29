"""Tool: resolve spoken deadlines ("by Friday", "tomorrow", "in 3 days") against the meeting date."""

import re
from datetime import date, timedelta
from typing import Optional

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_SAME_DAY = re.compile(r"\b(today|tonight|this (?:morning|afternoon|evening)|by eod|end of (?:the )?day|by \d{1,2}\s*(?:am|pm))\b")


def resolve_relative_date(text: str, anchor: date) -> Optional[date]:
    lower = text.lower()

    iso = _ISO_DATE.search(lower)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            pass

    if _SAME_DAY.search(lower):
        return anchor
    if re.search(r"\btomorrow\b", lower):
        return anchor + timedelta(days=1)
    if re.search(r"\b(?:end of (?:the )?week|this week)\b", lower):
        return anchor + timedelta(days=(4 - anchor.weekday()) % 7)
    if re.search(r"\bnext week\b", lower):
        return anchor + timedelta(days=7 - anchor.weekday())

    in_days = re.search(r"\bin (\d{1,2}) days?\b", lower)
    if in_days:
        return anchor + timedelta(days=int(in_days.group(1)))

    for index, name in enumerate(_WEEKDAYS):
        match = re.search(rf"\b(by|on|this|next|before)\s+{name}\b", lower)
        if match:
            days_ahead = (index - anchor.weekday()) % 7 or 7
            if match.group(1) == "next" and days_ahead < 7:
                days_ahead += 7
            return anchor + timedelta(days=days_ahead)
    return None
