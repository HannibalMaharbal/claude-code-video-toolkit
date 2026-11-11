"""Unit tests for tools/remotion_social.py."""

from __future__ import annotations

import json
from pathlib import Path

from tools.remotion_social import (
    WordTiming,
    build_caption_chunks,
    generate_remotion_social_props,
    parse_whisper_words,
)


def test_parse_whisper_words_segments():
    sample_transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Das ist Paris 1920",
                "words": [
                    {"word": "Das", "start": 0.0, "end": 0.4},
                    {"word": "ist", "start": 0.5, "end": 0.8},
                    {"word": "Paris", "start": 0.9, "end": 1.4},
                    {"word": "1920", "start": 1.5, "end": 2.0},
                ],
            }
        ]
    }
    words = parse_whisper_words(sample_transcript)
    assert len(words) == 4
    assert words[2].word == "Paris"
    assert words[2].start == 0.9


def test_build_caption_chunks_chunking():
    words = [
        WordTiming(word="Schritt", start=0.0, end=0.3),
        WordTiming(word="eins", start=0.3, end=0.6),
        WordTiming(word="ist", start=0.6, end=0.9),
        WordTiming(word="Kaffee", start=1.0, end=1.5),
        WordTiming(word="bestellen", start=1.5, end=2.0),
    ]
    chunks = build_caption_chunks(words, max_words_per_chunk=3, fps=30)
    assert len(chunks) == 2
    assert chunks[0].text == "Schritt eins ist"
    assert chunks[0].start_frame == 0
    assert chunks[0].end_frame == 27  # 0.9s * 30fps
    assert chunks[1].text == "Kaffee bestellen"


def test_generate_remotion_social_props(tmp_path: Path):
    t_file = tmp_path / "transcript.json"
    t_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.5,
                        "text": "Willkommen im Café",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    v_file = tmp_path / "video.mp4"
    v_file.write_bytes(b"dummy_video")
    out_props = tmp_path / "social_props.json"

    res = generate_remotion_social_props(
        video_path=v_file,
        transcript_json_path=t_file,
        output_props_path=out_props,
        fps=30,
        video_duration_sec=30.0,
    )

    assert res.is_file()
    data = json.loads(res.read_text(encoding="utf-8"))
    assert data["width"] == 1080
    assert data["height"] == 1920
    assert data["safe_zone"]["top"] == 150
    assert data["safe_zone"]["bottom"] == 280
    assert len(data["chunks"]) >= 1


def test_word_captions_logic_pauses_and_end_window() -> None:
    tsx_path = Path("templates/b2b-reel-remotion/src/components/WordCaptions.tsx")
    assert tsx_path.is_file()
    content = tsx_path.read_text(encoding="utf-8")

    # 1. Pure function getActiveCaptionWindow must be exported
    assert "export function getActiveCaptionWindow" in content

    # 2. In pauses and after the last word, it must not jump unconditionally to index 0
    assert "const activeIdx = currentIndex !== -1 ? currentIndex : 0;" not in content

    # 3. After last word ends, it must return null (ausblenden)
    assert "timeMs > captions[captions.length - 1].endMs" in content

    # 4. In pause between words, it must find the last spoken word
    assert "lastSpokenIdx" in content


def test_b2b_reel_cta_duration_scales_with_fps() -> None:
    tsx_path = Path("templates/b2b-reel-remotion/src/B2BReel.tsx")
    assert tsx_path.is_file()
    content = tsx_path.read_text(encoding="utf-8")

    # CTA duration must scale with fps (3.5 * fps)
    assert "Math.round(3.5 * fps)" in content
    assert "ctaStartFrame = durationInFrames - 100" not in content
    assert "durationInFrames={100}" not in content


def test_sample_data_json_uwg_compliance_and_placeholders() -> None:
    import re
    sample_file = Path("templates/b2b-reel-remotion/sample-data.json")
    assert sample_file.is_file()
    content = sample_file.read_text(encoding="utf-8")
    data = json.loads(content)

    assert "_hinweis" in data
    assert "BEISPIELDATEN" in data["_hinweis"]

    # No concrete digits followed by %
    digits_with_pct = re.findall(r"\d+\s*%", content)
    assert not digits_with_pct, f"sample-data.json contains unverified percentages: {digits_with_pct}"

    assert "[XX" in content


