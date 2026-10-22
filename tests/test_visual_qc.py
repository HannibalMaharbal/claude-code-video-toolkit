from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import project_init
from tools.visual_qc import check


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    return tmp_path


def _make_video(tmp_path: Path, name: str = "video.mp4") -> Path:
    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_subtitle_layout_returns_pass_on_valid_srt(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = _make_video(env)
    srt = env / "valid.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8")

    result = check(video, {"resolution": {"width": 320, "height": 240}}, subtitles=srt)
    subtitle_check = next(c for c in result if c["name"] == "subtitle_layout")

    assert subtitle_check["status"] == "pass"


def test_subtitle_layout_returns_fail_on_invalid_srt(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = _make_video(env)
    srt = env / "invalid.srt"
    srt.write_text("nicht valides srt format", encoding="utf-8")

    result = check(video, {"resolution": {"width": 320, "height": 240}}, subtitles=srt)
    subtitle_check = next(c for c in result if c["name"] == "subtitle_layout")

    assert subtitle_check["status"] == "fail"
    assert "fehlgeschlagen" in subtitle_check["evidence"].lower() or subtitle_check["evidence"]


def test_subtitle_layout_returns_not_run_when_no_subtitles(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = _make_video(env)

    result = check(video, {"resolution": {"width": 320, "height": 240}})
    subtitle_check = next(c for c in result if c["name"] == "subtitle_layout")

    assert subtitle_check["status"] == "not_run"
