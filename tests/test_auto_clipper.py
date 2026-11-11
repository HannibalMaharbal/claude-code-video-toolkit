from __future__ import annotations

from pathlib import Path
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


def test_autocrop_rejects_audio_inputs() -> None:
    for ext in auto_clipper.AUDIO_EXTENSIONS:
        with pytest.raises(ValueError, match="--autocrop.*Video"):
            auto_clipper.validate_autocrop_input(auto_clipper.Path(f"test{ext}"), autocrop=True)

    # Should not raise for video files
    auto_clipper.validate_autocrop_input(auto_clipper.Path("test.mp4"), autocrop=True)
    auto_clipper.validate_autocrop_input(auto_clipper.Path("test.mov"), autocrop=True)
    # Should not raise for audio files if autocrop is False
    auto_clipper.validate_autocrop_input(auto_clipper.Path("test.mp3"), autocrop=False)


def test_b2b_reel_prepare_payload_copies_audio_and_sets_prop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    build_reel_path = Path(__file__).resolve().parents[1] / "templates" / "b2b-reel-remotion" / "build_reel.py"
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    # Mock whisper alignment
    monkeypatch.setattr(build_reel, "align_audio_with_whisper", lambda p: [{"word": "Test", "startMs": 0, "endMs": 500}])
    monkeypatch.setattr(build_reel, "get_audio_duration", lambda p: 10.0)

    audio_file = tmp_path / "speaker.mp3"
    audio_file.write_bytes(b"dummy mp3 data")

    dummy_input = {"brandName": "Licbarska", "fps": 30, "durationInSeconds": 15}
    payload = build_reel.prepare_reel_payload(
        dummy_input,
        audio_path=audio_file,
        template_dir=tmp_path,
    )

    import hashlib
    file_hash = hashlib.sha256(b"dummy mp3 data").hexdigest()[:10]
    expected_name = f"speaker_{file_hash}.mp3"
    assert payload["audioSrc"] == f"_runtime_voiceover/{expected_name}"
    copied_dest = tmp_path / "public" / "_runtime_voiceover" / expected_name
    assert copied_dest.is_file()
    assert copied_dest.read_bytes() == b"dummy mp3 data"
    assert payload["captions"] == [{"word": "Test", "startMs": 0, "endMs": 500}]

    gitignore_path = Path(__file__).resolve().parents[1] / "templates" / "b2b-reel-remotion" / ".gitignore"
    assert gitignore_path.is_file()
    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    assert "public/_runtime_voiceover/" in gitignore_content or "_runtime_voiceover" in gitignore_content


def test_b2b_reel_prepare_payload_expands_duration_for_long_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    build_reel_path = Path(__file__).resolve().parents[1] / "templates" / "b2b-reel-remotion" / "build_reel.py"
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    monkeypatch.setattr(build_reel, "align_audio_with_whisper", lambda p: [])
    monkeypatch.setattr(build_reel, "get_audio_duration", lambda p: 18.0)

    audio_file = tmp_path / "long_speaker.mp3"
    audio_file.write_bytes(b"dummy")

    dummy_input = {"brandName": "Licbarska", "fps": 30, "durationInSeconds": 15}
    payload = build_reel.prepare_reel_payload(
        dummy_input,
        audio_path=audio_file,
        template_dir=tmp_path,
    )

    # 18.0s audio + 3.5s CTA = 21.5s (> 15s)
    assert payload["durationInSeconds"] == 21.5

    # Short audio (5.0s + 3.5s = 8.5s < 15s) -> keeps 15s
    monkeypatch.setattr(build_reel, "get_audio_duration", lambda p: 5.0)
    payload_short = build_reel.prepare_reel_payload(
        dummy_input,
        audio_path=audio_file,
        template_dir=tmp_path,
    )
    assert payload_short["durationInSeconds"] == 15


@pytest.mark.parametrize(
    "invalid_audio_src",
    [
        "https://evil/x.mp3",
        "../x.mp3",
        "/abs.mp3",
    ],
)
def test_b2b_reel_prepare_payload_rejects_unsafe_audio_src(
    invalid_audio_src: str, tmp_path: Path
) -> None:
    import importlib.util

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    with pytest.raises(ValueError, match="audioSrc"):
        build_reel.prepare_reel_payload(
            {"audioSrc": invalid_audio_src},
            template_dir=tmp_path,
        )


def test_b2b_reel_prepare_payload_accepts_valid_audio_src(tmp_path: Path) -> None:
    import importlib.util

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    payload = build_reel.prepare_reel_payload(
        {"audioSrc": "_runtime_voiceover/valid.mp3"},
        template_dir=tmp_path,
    )
    assert payload["audioSrc"] == "_runtime_voiceover/valid.mp3"

    # Filename with '..' inside name should be valid
    payload2 = build_reel.prepare_reel_payload(
        {"audioSrc": "_runtime_voiceover/sprecher..final.mp3"},
        template_dir=tmp_path,
    )
    assert payload2["audioSrc"] == "_runtime_voiceover/sprecher..final.mp3"


@pytest.mark.parametrize(
    "invalid_src",
    [
        "_runtime_voiceover/../x.mp3",
        "_runtime_voiceover/./x.mp3",
        "_runtime_voiceover/sub/../../x.mp3",
        "/_runtime_voiceover/x.mp3",
        "https://cdn.example.com/audio.mp3",
        "invalid_dir/x.mp3",
    ],
)
def test_b2b_reel_prepare_payload_rejects_invalid_audio_src_paths(
    invalid_src: str, tmp_path: Path
) -> None:
    import importlib.util

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    with pytest.raises(ValueError, match="audioSrc"):
        build_reel.prepare_reel_payload(
            {"audioSrc": invalid_src},
            template_dir=tmp_path,
        )


def test_b2b_reel_prepare_payload_normalizes_audio_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    monkeypatch.setattr(build_reel, "get_audio_duration", lambda p: 10.0)
    monkeypatch.setattr(build_reel, "align_audio_with_whisper", lambda p: [])

    import hashlib

    # Test file with special characters
    special_audio = tmp_path / "sprecher final #1 (neu).mp3"
    content = b"dummy audio"
    special_audio.write_bytes(content)
    dummy_hash = hashlib.sha256(content).hexdigest()[:10]

    payload = build_reel.prepare_reel_payload(
        {"brandName": "Licbarska"},
        audio_path=special_audio,
        template_dir=tmp_path,
    )
    expected_special = f"sprecher_final__1__neu__{dummy_hash}.mp3"
    assert payload["audioSrc"] == f"_runtime_voiceover/{expected_special}"
    assert (tmp_path / "public" / "_runtime_voiceover" / expected_special).is_file()

    # Test file with '..' in filename remains allowed and unchanged
    dotdot_audio = tmp_path / "sprecher..final.mp3"
    dotdot_audio.write_bytes(content)
    payload_dotdot = build_reel.prepare_reel_payload(
        {"brandName": "Licbarska"},
        audio_path=dotdot_audio,
        template_dir=tmp_path,
    )
    expected_dotdot = f"sprecher..final_{dummy_hash}.mp3"
    assert payload_dotdot["audioSrc"] == f"_runtime_voiceover/{expected_dotdot}"
    assert (tmp_path / "public" / "_runtime_voiceover" / expected_dotdot).is_file()


def test_b2b_reel_colliding_audio_names_different_content_produce_distinct_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    monkeypatch.setattr(build_reel, "get_audio_duration", lambda p: 10.0)
    monkeypatch.setattr(build_reel, "align_audio_with_whisper", lambda p: [])

    dir1 = tmp_path / "in1"
    dir2 = tmp_path / "in2"
    dir1.mkdir()
    dir2.mkdir()
    audio1 = dir1 / "sprecher #1.mp3"
    audio2 = dir2 / "sprecher ?1.mp3"
    audio1.write_bytes(b"voiceover content 1")
    audio2.write_bytes(b"voiceover content 2")

    payload1 = build_reel.prepare_reel_payload(
        {"brandName": "Licbarska"},
        audio_path=audio1,
        template_dir=tmp_path,
    )
    payload2 = build_reel.prepare_reel_payload(
        {"brandName": "Licbarska"},
        audio_path=audio2,
        template_dir=tmp_path,
    )

    dest1 = payload1["audioSrc"]
    dest2 = payload2["audioSrc"]
    assert dest1 != dest2
    file1 = tmp_path / "public" / dest1
    file2 = tmp_path / "public" / dest2
    assert file1.is_file()
    assert file2.is_file()
    assert file1.read_bytes() == b"voiceover content 1"
    assert file2.read_bytes() == b"voiceover content 2"



def test_b2b_reel_get_audio_duration_raises_on_ffprobe_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import subprocess

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    audio_file = tmp_path / "speaker.mp3"
    audio_file.write_bytes(b"corrupt")

    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffprobe"], stderr="corrupt file")

    monkeypatch.setattr(build_reel.subprocess, "run", mock_run)

    with pytest.raises(RuntimeError, match="ffprobe|Audiodauer"):
        build_reel.get_audio_duration(audio_file)


@pytest.mark.parametrize("invalid_out", ["0", "0.0", "-2.5", "nan", "inf", "corrupted"])
def test_b2b_reel_get_audio_duration_raises_on_non_positive_or_non_finite(
    invalid_out: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    from unittest.mock import MagicMock

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    audio_file = tmp_path / "speaker.mp3"
    audio_file.write_bytes(b"dummy")

    mock_res = MagicMock()
    mock_res.stdout = invalid_out
    monkeypatch.setattr(build_reel.subprocess, "run", lambda *args, **kwargs: mock_res)

    with pytest.raises(RuntimeError, match="Audiodauer"):
        build_reel.get_audio_duration(audio_file)


def test_b2b_reel_prepare_payload_aborts_when_get_audio_duration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import subprocess

    build_reel_path = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "b2b-reel-remotion"
        / "build_reel.py"
    )
    spec = importlib.util.spec_from_file_location("build_reel", build_reel_path)
    assert spec and spec.loader
    build_reel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_reel)

    audio_file = tmp_path / "broken.mp3"
    audio_file.write_bytes(b"not an audio")

    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffprobe"])

    monkeypatch.setattr(build_reel.subprocess, "run", mock_run)

    with pytest.raises(RuntimeError, match="Audiodauer"):
        build_reel.prepare_reel_payload(
            {"brandName": "Licbarska"},
            audio_path=audio_file,
            template_dir=tmp_path,
        )





def test_auto_clipper_docstring_flags_exist_in_parser() -> None:
    import re
    from tools import auto_clipper

    doc = auto_clipper.__doc__ or ""
    # Extract options mentioned in docstring, e.g. --input, --clip-index, etc.
    flags_in_doc = set(re.findall(r"--[a-z0-9-]+", doc))
    assert len(flags_in_doc) > 0

    assert hasattr(auto_clipper, "build_parser"), "auto_clipper must provide build_parser()"
    parser = auto_clipper.build_parser()
    registered_flags: set[str] = set()
    for action in parser._actions:
        for opt in action.option_strings:
            if opt.startswith("--"):
                registered_flags.add(opt)

    for flag in flags_in_doc:
        assert flag in registered_flags, f"Flag {flag} im Docstring existiert nicht im Parser!"


@pytest.mark.parametrize("audio_ext", [".mp3", ".m4a", ".wav", ".aac", ".flac"])
def test_auto_clipper_cut_audio_input_retains_extension_and_marks_type_audio(
    audio_ext: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import io
    from contextlib import redirect_stdout

    audio_file = tmp_path / f"test_audio{audio_ext}"
    audio_file.write_bytes(b"dummy audio")
    srt_file = tmp_path / "test_audio.srt"
    srt_file.write_text(SAMPLE_SRT, encoding="utf-8")

    export_dir = tmp_path / "export"
    monkeypatch.setattr(auto_clipper, "EXPORT_DIR", export_dir)

    cut_calls: list[tuple[Path, Path]] = []

    def mock_cut(inp: Path, start: float, dur: float, out: Path) -> Path:
        cut_calls.append((inp, out))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"cut audio data")
        return out

    monkeypatch.setattr(auto_clipper, "cut_clip_with_ffmpeg", mock_cut)

    test_args = [
        "auto_clipper.py",
        "--input", str(audio_file),
        "--srt", str(srt_file),
        "--cut",
        "--num-clips", "1",
        "--json",
    ]
    monkeypatch.setattr("sys.argv", test_args)

    buf = io.StringIO()
    with redirect_stdout(buf):
        ret = auto_clipper.main()

    assert ret == 0
    assert len(cut_calls) == 1
    src_path, dst_path = cut_calls[0]
    assert dst_path.suffix.lower() == audio_ext
    assert dst_path.name == f"test_audio_clip_01{audio_ext}"

    output_json = json.loads(buf.getvalue())
    assert isinstance(output_json, list) and len(output_json) == 1
    assert output_json[0].get("type") == "audio"



