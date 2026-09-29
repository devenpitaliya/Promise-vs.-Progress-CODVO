"""Sample meetings offered under "Try a sample" in the New meeting wizard. Clearly labelled as samples in the UI.

The transcripts live as plain text in the project's `samples/` folder (SAMPLES_DIR), so they can be read,
edited and uploaded like any real transcript. Only the metadata (title, type, participants) is defined here.
"""

import logging
from dataclasses import dataclass
from functools import cache
from typing import List

from app.config import settings
from app.schemas.meeting import Participant, SampleTranscript

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Sample:
    file: str
    title: str
    description: str
    meeting_type: str
    participants: tuple[tuple[str, str], ...]


_SAMPLES = (
    _Sample(
        file="sprint-34-standup.txt",
        title="Sprint 34 standup",
        description="Short standup: auth token fix, worker race condition and a blocked migration.",
        meeting_type="Standup",
        participants=(
            ("Maya Chen", "Engineering Lead"),
            ("Priya Raman", "Backend Engineer"),
            ("Alex Moreno", "Platform Engineer"),
            ("Sam Okafor", "Frontend Engineer"),
        ),
    ),
    _Sample(
        file="sprint-35-planning-sync.txt",
        title="Sprint 35 planning sync",
        description="Long, natural planning meeting: release prep, audit work, blockers, parked items and a recap.",
        meeting_type="Sprint Planning",
        participants=(
            ("Maya Chen", "Engineering Lead"),
            ("Priya Raman", "Backend Engineer"),
            ("Alex Moreno", "Platform Engineer"),
            ("Sam Okafor", "Frontend Engineer"),
            ("Vikram Iyer", "Site Reliability Engineer"),
            ("Elena Petrova", "Security Engineer"),
        ),
    ),
    _Sample(
        file="platform-reliability-review.txt",
        title="Platform reliability review",
        description="Post-incident review of a checkout outage: fixes, alerting, a blocked load test, SOC 2 evidence and CVEs.",
        meeting_type="Reliability Review",
        participants=(
            ("Maya Chen", "Engineering Lead"),
            ("Priya Raman", "Backend Engineer"),
            ("Alex Moreno", "Platform Engineer"),
            ("Vikram Iyer", "SRE Lead"),
            ("Elena Petrova", "Security Engineer"),
            ("Grace Liu", "Product Manager"),
        ),
    ),
)


@cache
def sample_transcripts() -> List[SampleTranscript]:
    """Samples whose transcript file exists (a missing file is skipped with a warning, never an error)."""
    samples: List[SampleTranscript] = []
    for sample in _SAMPLES:
        path = settings.samples_dir / sample.file
        try:
            transcript = path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Sample transcript %s not found; it will not be offered", path)
            continue
        samples.append(
            SampleTranscript(
                title=sample.title,
                description=sample.description,
                meeting_type=sample.meeting_type,
                participants=[Participant(name=name, role=role) for name, role in sample.participants],
                transcript=transcript,
            )
        )
    return samples
