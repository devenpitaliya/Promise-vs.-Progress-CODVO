"""Convert meeting caption files (WebVTT, SRT) into the "Name: text" lines the extractor expects.

Handles the exports people actually have:
- Microsoft Teams .vtt: speakers as voice tags (`<v Maya Chen>text</v>`), GUID cue ids, and one sentence
  often split across several consecutive cues.
- Zoom .vtt / most .srt files: the speaker as a "Name: text" prefix inside each cue.
- Captions without speakers: the text is kept, unattributed.
Timestamps, cue numbers, NOTE/STYLE/REGION blocks and inline markup are dropped, and consecutive cues from the
same speaker are merged into one line. Plain text that is not a caption file is returned unchanged.
"""

import html
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# hh:mm:ss.ttt or mm:ss.ttt (WebVTT), hh:mm:ss,ttt (SRT)
_TIMING = re.compile(r"(?:\d+:)?\d{2}:\d{2}[.,]\d{1,3}\s*-->")
_SRT_START = re.compile(r"^\s*\d+\s*\n\s*\d{1,2}:\d{2}:\d{2},\d{1,3}\s*-->", re.M)
_VOICE = re.compile(r"<v(?:\.[^\s>]+)*\s+([^>]+?)>(.*?)(?:</v>|(?=<v[\s.])|$)", re.S)
_TAG = re.compile(r"<[^>]*>")
_SPEAKER_PREFIX = re.compile(r"^([A-Z][\w.'\-]*(?:\s+[\w.'\-]+){0,3}):\s+(.+)$", re.S)
_SKIP_BLOCKS = ("NOTE", "STYLE", "REGION", "WEBVTT")


@dataclass
class ConvertedTranscript:
    text: str
    format: str  # "vtt" | "srt" | "text"
    speakers: List[str] = field(default_factory=list)
    lines: int = 0


def detect_format(raw: str) -> str:
    head = raw.lstrip("﻿").lstrip()
    if head.startswith("WEBVTT"):
        return "vtt"
    if _SRT_START.search(head[:2000]):
        return "srt"
    return "text"


def _clean(text: str) -> str:
    return " ".join(html.unescape(_TAG.sub("", text)).split())


def _cue_utterances(cue_text: str) -> List[Tuple[Optional[str], str]]:
    """(speaker or None, text) pairs in one cue."""
    voices = _VOICE.findall(cue_text)
    if voices:
        return [(_clean(name), _clean(text)) for name, text in voices if _clean(text)]
    text = _clean(cue_text)
    if not text:
        return []
    match = _SPEAKER_PREFIX.match(text)
    return [(match.group(1).strip(), match.group(2).strip())] if match else [(None, text)]


def convert_transcript(raw: str) -> ConvertedTranscript:
    kind = detect_format(raw)
    if kind == "text":
        return ConvertedTranscript(text=raw, format="text", lines=len([line for line in raw.splitlines() if line.strip()]))

    merged: List[Tuple[Optional[str], str]] = []
    for block in re.split(r"\n\s*\n", raw.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines or lines[0].strip().split(" ")[0] in _SKIP_BLOCKS:
            continue
        timing = next((i for i, line in enumerate(lines) if _TIMING.search(line)), None)
        if timing is None:
            continue  # not a cue (stray metadata)
        for speaker, text in _cue_utterances("\n".join(lines[timing + 1 :])):
            if merged and merged[-1][0] == speaker:
                merged[-1] = (speaker, f"{merged[-1][1]} {text}")
            else:
                merged.append((speaker, text))

    speakers = list(dict.fromkeys(s for s, _ in merged if s))
    text = "\n".join(f"{speaker}: {line}" if speaker else line for speaker, line in merged)
    return ConvertedTranscript(text=text, format=kind, speakers=speakers, lines=len(merged))
