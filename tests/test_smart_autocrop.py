from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tools import smart_autocrop


def _create_synthetic_test_video(output_path: Path, duration: int = 2) -> Path:
    """Create a minimal 16:9 MP4 test clip using ffmpeg lavfi."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def test_saliency_fallback(tmp_path: Path) -> None:
    # Create test image with bright spot in center-right
    img = Image.new("RGB", (200, 100), color=(20, 20, 20))
    for x in range(120, 160):
        for y in range(30, 70):
            img.putpixel((x, y), (240, 240, 240))
    img_path = tmp_path / "test_saliency.jpg"
    img.save(img_path)

    res = smart_autocrop._detect_subject_saliency_fallback(img_path)
    assert "cx" in res and "cy" in res
    assert 0.2 <= res["cx"] <= 0.8
    assert 0.2 <= res["cy"] <= 0.8
    assert res["cx"] > 0.5  # bright block was on the right side


def test_build_focus_spec_smoothing(tmp_path: Path) -> None:
    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img_path = tmp_path / "dummy.jpg"
    img.save(img_path)

    sampled = [(0.0, img_path), (1.0, img_path), (2.0, img_path)]
    keyframes = smart_autocrop.build_focus_spec(sampled)

    assert len(keyframes) == 3
    assert [k["t"] for k in keyframes] == [0.0, 1.0, 2.0]
    for k in keyframes:
        assert 0.0 <= k["cx"] <= 1.0
        assert 0.0 <= k["cy"] <= 1.0
        assert "box" in k


def test_smart_autocrop_spec_only(tmp_path: Path) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "input_16x9.mp4", duration=2)
    export_dir = tmp_path / "export"

    result = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=export_dir,
        profile_name="youtube_short",
        sample_interval=1.0,
        render_video=False,
    )

    assert result["status"] == "success"
    assert result["keyframes_count"] >= 2
    spec_file = Path(result["spec_file"])
    assert spec_file.is_file()

    spec_data = json.loads(spec_file.read_text(encoding="utf-8"))
    assert spec_data["profile"] == "youtube_short"
    assert len(spec_data["keyframes"]) >= 2


def test_smart_autocrop_full_render(tmp_path: Path) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "input_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    result = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=export_dir,
        profile_name="ad_9x16",
        sample_interval=1.0,
        render_video=True,
    )

    assert result["status"] == "success"
    assert result["output_video"] is not None
    out_video = Path(result["output_video"])
    assert out_video.is_file() and out_video.stat().st_size > 0

