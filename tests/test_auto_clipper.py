from __future__ import annotations

import pytest
from tools import auto_clipper

SAMPLE_SRT = """1
00:00:00,000 --> 00:00:15,000
Hallo und herzlich willkommen zu diesem Video über Mehrfamilienhäuser.

2
00:00:15,000 --> 00:00:45,000
Warum verschenken Eigentümer Millionen Euro Gewinn? Das größte Problem ist die falsche Sanierungsstrategie. Wer das Mietpotenzial nicht hebt, erleidet massiven Verlust bei der Bank.

3
00:00:45,000 --> 00:01:15,000
In diesem Abschnitt erklären wir die steuerlichen Aspekte bei der Denkmal-Afa und warum man vorsichtig sein muss.

4
00:01:15,000 --> 00:01:50,000
Hier ist das Fazit unseres Videos: Prüfen Sie Ihre Rendite und handeln Sie rechtzeitig. Vielen Dank fürs Zusehen!
"""


def test_parse_srt_extracts_segments() -> None:
    segs = auto_clipper.parse_srt_or_segments(SAMPLE_SRT)
    assert len(segs) == 4
    assert segs[1]["start"] == 15.0
    assert segs[1]["end"] == 45.0
    assert "Millionen" in segs[1]["text"]


def test_score_segment_prioritizes_high_retention_keywords() -> None:
    high_text = "Warum verschenken Eigentümer Millionen Euro Gewinn? Das größte Problem ist die falsche Sanierungsstrategie."
    low_text = "Heute ist das Wetter ganz schön und wir machen einen kleinen Spaziergang durch den Garten."

    score_high = auto_clipper.score_segment(high_text, 30.0)
    score_low = auto_clipper.score_segment(low_text, 30.0)

    assert score_high > score_low
    assert score_high >= 50.0


def test_find_top_clips_selects_best_non_overlapping_intervals() -> None:
    segs = auto_clipper.parse_srt_or_segments(SAMPLE_SRT)
    clips = auto_clipper.find_top_clips(segs, target_duration=30.0, max_clips=2)

    assert len(clips) >= 1
    assert clips[0].retention_score > 40.0
    assert "Millionen" in clips[0].full_transcript
