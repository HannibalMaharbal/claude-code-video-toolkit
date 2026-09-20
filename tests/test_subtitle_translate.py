import subprocess
from pathlib import Path

from tools.subtitle_translate import translate_subtitle_file


def test_keeps_only_marker_content_for_three_cues(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.srt"
    target = tmp_path / "target.srt"
    source.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nGuten Morgen.\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nWie geht es dir?\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\nDas ist ein Test.\n",
        encoding="utf-8",
    )
    replies = iter([
        "Thinking...\n<translation>Good morning.</translation>",
        "<translation>How are you?</translation>\nDone.",
        "analysis\n<translation>This is a test.</translation>",
    ])
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, next(replies), ""),
    )

    translate_subtitle_file(source, target, target_language="English")

    rendered = target.read_text(encoding="utf-8")
    assert "Thinking" not in rendered
    assert "Done." not in rendered
    assert "Good morning." in rendered
    assert "How are you?" in rendered
    assert "This is a test." in rendered
    assert source.read_text(encoding="utf-8").startswith("1\n00:00")


def test_refuses_unmarked_response_without_writing_output(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.srt"
    target = tmp_path / "target.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_: subprocess.CompletedProcess(command, 0, "Thinking only", ""),
    )

    try:
        translate_subtitle_file(source, target, target_language="English")
    except RuntimeError as error:
        assert "marker" in str(error)
    else:
        raise AssertionError("expected marker failure")
    assert not target.exists()
