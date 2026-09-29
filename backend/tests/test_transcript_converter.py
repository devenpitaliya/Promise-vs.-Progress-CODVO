"""Caption files (Teams/Zoom .vtt, .srt) become "Name: text" transcripts."""

from app.tools.transcript_converter import convert_transcript, detect_format

TEAMS_VTT = """﻿WEBVTT

0f6d1c5e-1b2a-4a2d-9d1e-1a2b3c4d5e6f/12-0
00:00:01.200 --> 00:00:04.580
<v Maya Chen>Okay, I think everyone's here.</v>

0f6d1c5e-1b2a-4a2d-9d1e-1a2b3c4d5e6f/12-1
00:00:04.580 --> 00:00:07.010
<v Maya Chen>Let's start with the audit work.</v>

0f6d1c5e-1b2a-4a2d-9d1e-1a2b3c4d5e6f/13-0
00:00:07.500 --> 00:00:12.000
<v Alex Moreno>I will deploy issue #78 to staging
by Wednesday &amp; share the logs.</v>

0f6d1c5e-1b2a-4a2d-9d1e-1a2b3c4d5e6f/14-0
00:00:12.100 --> 00:00:15.000
<v Maya Chen>Great, thanks.</v>
"""

ZOOM_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.500
Priya Raman: I'll fix issue #45 by tomorrow.

2
00:00:03.600 --> 00:00:05.000
Sam Okafor: I already merged PR #204 yesterday.
"""

SRT = """1
00:00:01,000 --> 00:00:03,000
Vikram Iyer: I'll resolve the Redis timeouts in 3 days.

2
00:00:03,100 --> 00:00:06,000
Elena Petrova: I will patch the base images by Friday.
"""


def test_teams_voice_tags_merge_split_cues_and_decode_entities():
    result = convert_transcript(TEAMS_VTT)
    assert result.format == "vtt"
    assert result.speakers == ["Maya Chen", "Alex Moreno"]
    assert result.text.splitlines() == [
        "Maya Chen: Okay, I think everyone's here. Let's start with the audit work.",
        "Alex Moreno: I will deploy issue #78 to staging by Wednesday & share the logs.",
        "Maya Chen: Great, thanks.",
    ]
    assert "-->" not in result.text and "<v" not in result.text and "0f6d1c5e" not in result.text


def test_zoom_vtt_and_srt_use_the_name_prefix():
    zoom = convert_transcript(ZOOM_VTT)
    assert zoom.speakers == ["Priya Raman", "Sam Okafor"]
    assert zoom.text.splitlines()[1] == "Sam Okafor: I already merged PR #204 yesterday."
    srt = convert_transcript(SRT.replace("\n", "\r\n"))
    assert srt.format == "srt" and srt.speakers == ["Vikram Iyer", "Elena Petrova"]
    assert srt.text.startswith("Vikram Iyer: I'll resolve the Redis timeouts in 3 days.")


def test_metadata_blocks_markup_and_unattributed_captions():
    vtt = """WEBVTT - exported

NOTE This is a comment
spanning two lines

STYLE
::cue { color: yellow }

00:01.000 --> 00:02.000 align:start
<c.loud><b>Hello</b></c> <00:00:01.500>everyone

00:02.100 --> 00:03.000
<v.first Maya Chen>First</v><v Alex Moreno>Second</v>
"""
    result = convert_transcript(vtt)
    assert result.text.splitlines() == ["Hello everyone", "Maya Chen: First", "Alex Moreno: Second"]
    assert "comment" not in result.text and "yellow" not in result.text


def test_plain_text_is_returned_unchanged():
    text = "Maya: I will merge PR #101 today.\nPriya: I'll fix issue #45 by tomorrow."
    result = convert_transcript(text)
    assert result.format == "text" and result.text == text and result.lines == 2
    assert detect_format("Notes from the call --> nothing to see") == "text"


async def test_convert_endpoint_previews_without_saving(client, auth):
    response = await client.post("/api/v1/meetings/transcript/convert", json={"text": TEAMS_VTT}, headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "vtt" and body["speakers"] == ["Maya Chen", "Alex Moreno"]
    assert body["lines"] == 3 and body["too_long"] is False
    assert (await client.get("/api/v1/meetings/", headers=auth)).json() == []
    assert (await client.post("/api/v1/meetings/transcript/convert", json={"text": TEAMS_VTT})).status_code == 401


async def test_raw_captions_sent_to_create_are_converted_before_extraction(client, auth):
    response = await client.post(
        "/api/v1/meetings/",
        json={"title": "Imported from Teams", "meeting_date": "2026-09-21", "participants": [], "transcript": ZOOM_VTT},
        headers=auth,
    )
    meeting = response.json()
    assert meeting["transcript"].startswith("Priya Raman: I'll fix issue #45 by tomorrow.")
    by_ref = {t["external_ref"]: t for t in meeting["tasks"]}
    assert by_ref["Issue #45"]["assignee"] == "Priya Raman"
    assert by_ref["PR #204"]["speech_status"] == "COMPLETED_IN_SPEECH"
