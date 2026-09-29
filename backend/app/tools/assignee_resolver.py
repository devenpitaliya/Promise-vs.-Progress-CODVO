"""Tool: map a transcript speaker label ("Priya") to a roster name ("Priya Raman")."""

import re
from typing import Sequence

from app.schemas.meeting import Participant


def resolve_assignee(raw_speaker: str, participants: Sequence[Participant]) -> str:
    """Whole-word match only; unknown speakers keep their label instead of being guessed."""
    label = raw_speaker.strip()
    tokens = {t for t in re.split(r"[\s.]+", label.lower()) if t}
    for person in participants:
        name_tokens = {t for t in re.split(r"[\s.]+", person.name.lower()) if t}
        if label.lower() == person.name.lower() or (tokens and tokens <= name_tokens):
            return person.name
    return label
