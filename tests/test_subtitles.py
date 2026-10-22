import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.transcribe import (
    build_script_authoritative_cues,
    build_subtitle_cues,
    burn_in_subtitles,
    validate_subtitle_cues,
    validate_subtitle_file,
    write_srt,
    write_vtt,
)


def transcript() -> list[dict[str, object]]:
    return [
        {"text": "Hallo", "start": 0.0, "end": 0.4},
        {"text": "Welt.", "start": 0.45, "end": 0.9},
        {"text": "Dies ist ein lokaler Test.", "start": 1.2, "end": 2.6},
    ]


def test_writes_valid_srt_and_vtt_from_timestamped_transcript(tmp_path: Path) -> None:
    cues = build_subtitle_cues(transcript())
    srt_path = tmp_path / "captions.srt"
    vtt_path = tmp_path / "captions.vtt"

    write_srt(cues, srt_path)
    write_vtt(cues, vtt_path)

    assert validate_subtitle_cues(cues) == []
    assert validate_subtitle_file(srt_path) == []
    assert validate_subtitle_file(vtt_path) == []
    expected_srt = "1\n00:00:00,000 --> 00:00:02,600\nHallo Welt. Dies ist ein lokaler Test."
    assert expected_srt in srt_path.read_text()
    assert vtt_path.read_text().startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.600" in vtt_path.read_text()


@pytest.mark.parametrize(
    ("cues", "message"),
    [
        ([{"text": "", "start": 0, "end": 1}], "leeren Text"),
        ([{"text": "x", "start": 1, "end": 1}], "Startzeit"),
        (
            [
                {"text": "eins", "start": 0, "end": 2},
                {"text": "zwei", "start": 1.5, "end": 3},
            ],
            "überschneidet",
        ),
        ([{"text": "x" * 43, "start": 0, "end": 1}], "Zeile"),
    ],
)
def test_subtitle_qc_rejects_invalid_cues(cues: list[dict[str, object]], message: str) -> None:
    assert any(message in error for error in validate_subtitle_cues(cues))


def test_accepts_mlx_whisper_result_shape() -> None:
    result = {"segments": transcript(), "text": "Hallo Welt. Dies ist ein lokaler Test."}
    cues = build_subtitle_cues(result)
    assert not validate_subtitle_cues(cues)
    assert json.dumps(cues)


def test_known_script_is_authoritative_while_whisper_keeps_timing() -> None:
    timings = [
        {"text": "falsch erkannt", "start": 0.0, "end": 1.2},
        {"text": "noch falsch", "start": 1.2, "end": 2.4},
    ]
    cues = build_script_authoritative_cues(timings, "Künstliche Intelligenz entsteht jetzt.")
    assert " ".join(str(cue["text"]) for cue in cues) == "Künstliche Intelligenz entsteht jetzt."
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] == 2.4


def test_subtitle_file_qc_rejects_invalid_srt_structure(tmp_path: Path) -> None:
    broken = tmp_path / "broken.srt"
    broken.write_text("not-a-number\n00:00:00,000 -> 00:00:01,000\n", encoding="utf-8")
    errors = validate_subtitle_file(broken)
    assert any("Timestamp" in error for error in errors)
    assert any("SRT-Nummerierung" in error for error in errors)


@pytest.mark.parametrize(
    ("cues", "message"),
    [
        ([{"text": "x", "start": -0.1, "end": 1}], "Startzeit"),
        ([{"text": "x", "start": 0, "end": 0.05}], "extrem kurze"),
        ([{"text": "x", "start": 0, "end": 8.1}], "extrem lange"),
    ],
)
def test_subtitle_qc_rejects_remaining_timestamp_and_duration_failures(
    cues: list[dict[str, object]], message: str
) -> None:
    assert any(message in error for error in validate_subtitle_cues(cues))


def test_subtitle_file_qc_checks_srt_timing_order_overlap_and_utf8(tmp_path: Path) -> None:
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nGrüße\n\n"
        "2\n00:00:02,000 --> 00:00:02,050\nWelt\n",
        encoding="utf-8",
    )

    errors = validate_subtitle_file(subtitle)

    assert any("überschneidet" in error for error in errors)
    assert any("extrem kurze" in error for error in errors)


def test_subtitle_file_qc_rejects_empty_and_invalid_vtt(tmp_path: Path) -> None:
    empty_srt = tmp_path / "empty.srt"
    empty_srt.write_text("\n", encoding="utf-8")
    invalid_vtt = tmp_path / "broken.vtt"
    invalid_vtt.write_text("WEBVTT\n\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")

    assert any("keine Cues" in error for error in validate_subtitle_file(empty_srt))
    assert any("Timestamp" in error for error in validate_subtitle_file(invalid_vtt))


def test_writers_preserve_utf8_text(tmp_path: Path) -> None:
    cues = [{"text": "Grüße, Café — 你好", "start": 0.0, "end": 1.0}]
    srt_path = tmp_path / "utf8.srt"
    vtt_path = tmp_path / "utf8.vtt"

    write_srt(cues, srt_path)
    write_vtt(cues, vtt_path)

    assert "Grüße, Café — 你好" in srt_path.read_text(encoding="utf-8")
    assert "Grüße, Café — 你好" in vtt_path.read_text(encoding="utf-8")


def test_burn_in_uses_local_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "-filters" in command:
            return subprocess.CompletedProcess(command, 0, " ... subtitles V->V ", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    input_path = tmp_path / "input.mp4"
    caption_path = tmp_path / "captions.srt"
    input_path.write_bytes(b"fixture")
    caption_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")
    burn_in_subtitles(input_path, caption_path, tmp_path / "output.mp4")

    assert calls[1][0] == "ffmpeg"
    assert "subtitles=" in calls[1][calls[1].index("-vf") + 1]


def test_burn_in_reports_missing_local_ffmpeg_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, "", ""),
    )
    input_path = tmp_path / "input.mp4"
    caption_path = tmp_path / "captions.srt"
    input_path.write_bytes(b"fixture")
    caption_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="subtitles/libass"):
        burn_in_subtitles(input_path, caption_path, tmp_path / "output.mp4")


def test_cli_creates_qc_passed_subtitles_and_burns_them_in(tmp_path: Path) -> None:
    transcript_path = tmp_path / "transcript.json"
    srt_path = tmp_path / "captions.srt"
    vtt_path = tmp_path / "captions.vtt"
    transcript_path.write_text(json.dumps({"segments": transcript()}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/transcribe.py",
            "--transcript-json",
            str(transcript_path),
            "--srt",
            str(srt_path),
            "--vtt",
            str(vtt_path),
            "--subtitle-qc",
        ],
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    assert "Subtitle QC: PASS" in result.stderr
    assert validate_subtitle_file(srt_path) == []
    assert validate_subtitle_file(vtt_path) == []
    for subtitle_path in (srt_path, vtt_path):
        qc = subprocess.run(
            [
                sys.executable,
                "tools/transcribe.py",
                "--subtitle-file",
                str(subtitle_path),
                "--subtitle-qc",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Subtitle QC: PASS" in qc.stderr


def test_cli_rejects_empty_segments_without_writing_files(tmp_path: Path) -> None:
    transcript_path = tmp_path / "empty.json"
    srt_path = tmp_path / "captions.srt"
    vtt_path = tmp_path / "captions.vtt"
    transcript_path.write_text(json.dumps({"segments": []}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/transcribe.py",
            "--transcript-json",
            str(transcript_path),
            "--srt",
            str(srt_path),
            "--vtt",
            str(vtt_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "keine Segmente" in result.stderr
    assert not srt_path.exists()
    assert not vtt_path.exists()


def test_cli_rejects_invalid_json_without_writing_files(tmp_path: Path) -> None:
    transcript_path = tmp_path / "broken.json"
    srt_path = tmp_path / "captions.srt"
    transcript_path.write_text("{not valid json", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/transcribe.py",
            "--transcript-json",
            str(transcript_path),
            "--srt",
            str(srt_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Transcript JSON error" in result.stderr
    assert not srt_path.exists()


@pytest.mark.parametrize(
    "payload",
    [
        [{"text": "x", "end": 1.0}],
        [{"text": "x", "start": 0.0}],
        [{"text": "x", "start": "abc", "end": 1.0}],
        {"segments": {"start": 0.0, "end": 1.0}},
        ["kein Objekt"],
    ],
)
def test_cli_rejects_missing_or_malformed_segment_fields_without_files(
    tmp_path: Path, payload: object
) -> None:
    transcript_path = tmp_path / "bad.json"
    srt_path = tmp_path / "captions.srt"
    transcript_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/transcribe.py",
            "--transcript-json",
            str(transcript_path),
            "--srt",
            str(srt_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Subtitle QC: FAIL" in result.stderr
    assert not srt_path.exists()


def test_cli_json_output_stays_clean_when_mlx_prints_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class StubMlxWhisper:
        @staticmethod
        def transcribe(*_: object, **__: object) -> dict[str, object]:
            print("Detected language: German")
            return {
                "text": "Hallo Welt.",
                "segments": [
                    {"text": "Hallo Welt.", "start": 0.0, "end": 1.0},
                ],
                "language": "de",
            }

    monkeypatch.setitem(sys.modules, "mlx_whisper", StubMlxWhisper)
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"fixture")
    monkeypatch.setattr(
        "sys.argv",
        ["tools/transcribe.py", "--input", str(audio_path), "--model", "tiny", "--json"],
    )

    from tools.transcribe import main

    main()
    captured = capsys.readouterr().out
    parsed = json.loads(captured)
    assert parsed["text"] == "Hallo Welt."


def _word_tokens(*texts: str) -> list[str]:
    tokens = []
    for text in texts:
        tokens.extend(text.split())
    return [token for token in tokens if token]


def _assert_words_preserved(source_text: str, cues: list[dict[str, object]]) -> None:
    expected = _word_tokens(source_text)
    actual = _word_tokens(*(str(cue["text"]) for cue in cues))
    assert actual == expected


def _assert_cue_times(
    cues: list[dict[str, object]], span_start: float, span_end: float
) -> None:
    previous_end: float | None = None
    for cue in cues:
        start = float(cue["start"])
        end = float(cue["end"])
        assert start >= span_start
        assert end <= span_end
        assert start < end
        if previous_end is not None:
            assert start >= previous_end
        previous_end = end
    if cues:
        assert float(cues[0]["start"]) == span_start
        assert float(cues[-1]["end"]) == span_end


def test_split_long_cue_at_43_characters() -> None:
    source = "a" * 20 + " " + "b" * 22
    assert len(source) == 43
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 2.0}])
    assert len(cues) == 2
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 2.0)
    assert validate_subtitle_cues(cues) == []


def test_split_long_text_without_punctuation_on_word_boundaries() -> None:
    source = " ".join(f"wort{index}" for index in range(30))
    assert len(source) > 80
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 10.0}])
    assert len(cues) > 1
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    for cue in cues:
        text = str(cue["text"])
        assert text == text.strip()
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 10.0)
    assert validate_subtitle_cues(cues) == []


def test_split_prefers_sentence_boundaries() -> None:
    source = (
        "Das ist der erste Satz. Und hier kommt der zweite Satz "
        "mit deutlich mehr Wörtern in dem langen Transkript."
    )
    assert len(source) > 42
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 8.0}])
    assert cues[0]["text"].endswith(".")
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 8.0)
    assert validate_subtitle_cues(cues) == []


def test_split_keeps_single_oversized_word_verbatim_and_flags_it() -> None:
    long_word = "Q" * 60
    source = f"kurz {long_word} ende"
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 3.0}])
    texts = [str(cue["text"]) for cue in cues]
    assert any(text == long_word for text in texts)
    assert long_word in [text for text in texts if long_word in text]
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 3.0)
    errors = validate_subtitle_cues(cues)
    assert any("Zeile länger" in error for error in errors)


def test_split_preserves_unicode_and_umlauts() -> None:
    source = (
        "Grüße aus München mit Äpfeln und Öfen. Die Straße führt "
        "über das Märchen und endet an der Tür."
    )
    assert len(source) > 42
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 6.0}])
    combined = " ".join(str(cue["text"]) for cue in cues).replace(" .", ".")
    _assert_words_preserved(source, cues)
    assert "Grüße" in str(cues[0]["text"])
    assert "München" in combined
    assert "Äpfeln" in combined and "Märchen" in combined and "Tür" in combined
    _assert_cue_times(cues, 0.0, 6.0)


def test_split_keeps_decimal_numbers_together() -> None:
    source = "Die Zahl beträgt 3,14 und 42.5 sowie 1.000 Euro auf dem Konto."
    assert len(source) > 42
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 5.0}])
    combined = " ".join(str(cue["text"]) for cue in cues)
    assert "3,14" in combined
    assert "42.5" in combined
    assert "1.000" in combined
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 5.0)


def test_split_very_short_duration_long_text_stays_deterministic() -> None:
    source = " ".join(f"wort{index}" for index in range(20))
    assert len(source) > 80
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 0.2}])
    assert len(cues) > 1
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 0.2)
    errors = validate_subtitle_cues(cues)
    assert any("extrem kurze" in error for error in errors)


def test_split_consecutive_long_segments_preserves_order() -> None:
    first = " ".join(f"eins{index}" for index in range(20))
    second = " ".join(f"zwei{index}" for index in range(20))
    payload = [
        {"text": first, "start": 0.0, "end": 2.0},
        {"text": second, "start": 2.2, "end": 4.0},
    ]
    cues = build_subtitle_cues(payload)
    assert len(cues) > 2
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    _assert_words_preserved(f"{first} {second}", cues)
    _assert_cue_times(cues, 0.0, 4.0)
    assert validate_subtitle_cues(cues) == []


def test_split_mixed_short_and_long_segments_touches_only_long_ones() -> None:
    short = "Kurzer Satz."
    long_text = " ".join(f"lang{index}" for index in range(25))
    cues = build_subtitle_cues(
        [
            {"text": short, "start": 0.0, "end": 1.0},
            {"text": long_text, "start": 1.5, "end": 5.0},
            {"text": short, "start": 5.5, "end": 6.5},
        ]
    )
    texts = [str(cue["text"]) for cue in cues]
    assert texts.count(short) == 2
    long_cues = [text for text in texts if "lang" in text]
    assert len(long_cues) > 1
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    _assert_words_preserved(f"{short} {long_text} {short}", cues)
    _assert_cue_times(cues, 0.0, 6.5)
    assert validate_subtitle_cues(cues) == []


def test_resolution_43_char_source_with_punctuation() -> None:
    source = "Eins zwei drei vier fünf. Sechs sieben acht neun zehn elf."
    assert len(source) > 42
    cues = build_subtitle_cues([{"text": source, "start": 0.0, "end": 9.0}])
    assert len(cues) >= 2
    assert all(len(str(cue["text"])) <= 42 for cue in cues)
    _assert_words_preserved(source, cues)
    _assert_cue_times(cues, 0.0, 9.0)
    assert validate_subtitle_cues(cues) == []


def test_cli_long_segments_pass_srt_vtt_and_subtitle_qc(tmp_path: Path) -> None:
    long_payload = {
        "segments": [
            {
                "text": (
                    "Das ist der erste lange Satz mit wirklich vielen Wörtern "
                    "für die Zeilenlängenprüfung des Untertitels."
                ),
                "start": 0.0,
                "end": 4.0,
            },
            {
                "text": (
                    "Und ein zweiter langer Satz mit noch mehr Inhalt und "
                    "ein paar zusätzlichen Wörtern am Ende."
                ),
                "start": 4.2,
                "end": 8.0,
            },
        ]
    }
    transcript_path = tmp_path / "long.json"
    srt_path = tmp_path / "long.srt"
    vtt_path = tmp_path / "long.vtt"
    transcript_path.write_text(json.dumps(long_payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "tools/transcribe.py",
            "--transcript-json",
            str(transcript_path),
            "--srt",
            str(srt_path),
            "--vtt",
            str(vtt_path),
            "--subtitle-qc",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Subtitle QC: PASS" in result.stderr
    assert validate_subtitle_file(srt_path) == []
    assert validate_subtitle_file(vtt_path) == []
    assert srt_path.read_text(encoding="utf-8").count("\n\n") > 1
