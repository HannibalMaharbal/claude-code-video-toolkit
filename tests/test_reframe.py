from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tools import asset_record, reframe

# --- Pure geometry / smoothing: no ffmpeg -------------------------------------------


def test_parse_focus_spec_valid(tmp_path: Path) -> None:
    spec = tmp_path / "focus.json"
    keyframes_data = [{"t": 1.0, "cx": 0.6, "cy": 0.4}, {"t": 0.0, "cx": 0.5, "cy": 0.5}]
    spec.write_text(json.dumps({"keyframes": keyframes_data}), encoding="utf-8")
    keyframes = reframe.parse_focus_spec(spec)
    assert [k["t"] for k in keyframes] == [0.0, 1.0]  # sorted


def test_parse_focus_spec_rejects_empty(tmp_path: Path) -> None:
    spec = tmp_path / "focus.json"
    spec.write_text(json.dumps({"keyframes": []}), encoding="utf-8")
    with pytest.raises(reframe.ReframeError, match="Keyframe"):
        reframe.parse_focus_spec(spec)


def test_parse_focus_spec_rejects_out_of_range_center(tmp_path: Path) -> None:
    spec = tmp_path / "focus.json"
    spec.write_text(json.dumps({"keyframes": [{"t": 0.0, "cx": 1.5, "cy": 0.5}]}), encoding="utf-8")
    with pytest.raises(reframe.ReframeError, match=r"\[0,1\]"):
        reframe.parse_focus_spec(spec)


def test_smooth_keyframes_moves_toward_next_point() -> None:
    keyframes = [{"t": 0.0, "cx": 0.0, "cy": 0.0}, {"t": 1.0, "cx": 1.0, "cy": 1.0}]
    smoothed = reframe.smooth_keyframes(keyframes, alpha=0.5)
    assert smoothed[0] == {"t": 0.0, "cx": 0.0, "cy": 0.0}
    assert smoothed[1]["cx"] == pytest.approx(0.5)


def test_focus_at_interpolates_linearly() -> None:
    keyframes = [{"t": 0.0, "cx": 0.0, "cy": 0.0}, {"t": 2.0, "cx": 1.0, "cy": 0.0}]
    assert reframe.focus_at(keyframes, 1.0) == pytest.approx((0.5, 0.0))
    assert reframe.focus_at(keyframes, -1.0) == (0.0, 0.0)
    assert reframe.focus_at(keyframes, 10.0) == (1.0, 0.0)


def test_compute_crop_window_follows_focus_left_vs_right() -> None:
    left = reframe.compute_crop_window(1920, 1080, 1080, 1920, cx=0.2, cy=0.5)
    right = reframe.compute_crop_window(1920, 1080, 1080, 1920, cx=0.8, cy=0.5)
    assert left[0] < right[0]  # x offset differs with focus


def test_compute_crop_window_clamps_to_source_bounds() -> None:
    x, y, w, h = reframe.compute_crop_window(1920, 1080, 1080, 1920, cx=0.0, cy=0.0)
    assert x == 0 and y == 0
    assert x + w <= 1920
    assert y + h <= 1080


def test_check_safe_zone_flags_extreme_focus_for_vertical_profile() -> None:
    profile = {
        "resolution": {"width": 1080, "height": 1920},
        "safe_zone": {"width": 900, "height": 1400, "x": 90, "y": 260},
    }
    centered = reframe.check_safe_zone(
        [{"t": 0.0, "cx": 0.5, "cy": 0.5}], profile, source_w=1920, source_h=1080
    )
    extreme = reframe.check_safe_zone(
        [{"t": 0.0, "cx": 0.02, "cy": 0.5}], profile, source_w=1920, source_h=1080
    )
    assert centered == []
    assert extreme != []


def test_check_safe_zone_skipped_when_profile_has_none() -> None:
    profile = {"resolution": {"width": 1920, "height": 1080}, "safe_zone": None}
    assert reframe.check_safe_zone([{"t": 0.0, "cx": 0.02, "cy": 0.5}], profile, 1920, 1080) == []


# --- render(): real ffmpeg, real rejection paths ------------------------------------


def _make_source(tmp_path: Path, name: str = "master.mp4") -> Path:
    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_render_without_spec_and_without_allow_is_rejected(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    with pytest.raises(reframe.ReframeError, match="needs_human"):
        reframe.render(source, "ad_9x16", tmp_path / "out.mp4")


def test_render_allow_center_crop_without_reason_is_rejected(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    with pytest.raises(reframe.ReframeError, match="Begründung"):
        reframe.render(source, "ad_9x16", tmp_path / "out.mp4", allow_center_crop=True)


def test_render_allow_center_crop_with_reason_succeeds_and_warns(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out.mp4"
    result = reframe.render(
        source,
        "ad_9x16",
        output,
        allow_center_crop=True,
        allow_center_crop_reason="Kein Presenter im Bild",
    )
    assert output.is_file() and output.stat().st_size > 0
    assert result["center_crop"] is True
    assert any("Kein Presenter im Bild" in warning for warning in result["warnings"])


def test_render_with_spec_produces_profile_resolution(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    spec = tmp_path / "focus.json"
    spec.write_text(json.dumps({"keyframes": [{"t": 0.0, "cx": 0.5, "cy": 0.5}]}), encoding="utf-8")
    output = tmp_path / "out.mp4"

    result = reframe.render(source, "ad_9x16", output, focus_spec_path=spec)

    assert result["center_crop"] is False
    assert result["warnings"] == []
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(output)],
        check=True, capture_output=True, text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (1080, 1920)


def test_render_rejects_focus_outside_safe_zone(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    spec = tmp_path / "focus.json"
    keyframes_data = [{"t": 0.0, "cx": 0.02, "cy": 0.5}]
    spec.write_text(json.dumps({"keyframes": keyframes_data}), encoding="utf-8")
    with pytest.raises(reframe.ReframeError, match="Safe-Zone"):
        reframe.render(source, "ad_9x16", tmp_path / "out.mp4", focus_spec_path=spec)


def test_crop_visibly_follows_a_marker_at_different_focus_points(tmp_path: Path) -> None:
    """Burn a red marker at a known horizontal position; prove the reframed output
    centers whatever position the focus spec names, not a fixed center crop."""
    width, height, marker_w, marker_h = 1280, 720, 120, 120
    marker_cx_norm = 0.3  # within the non-clamped crop range for this source/profile pair
    marker_x = int(marker_cx_norm * width - marker_w / 2)
    source = tmp_path / "marked.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d=1",
            "-vf", f"drawbox=x={marker_x}:y={height // 2 - marker_h // 2}:"
            f"w={marker_w}:h={marker_h}:color=red:t=fill",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ],
        check=True, capture_output=True,
    )

    def _render_and_sample(cx: float) -> tuple[int, int, int]:
        spec = tmp_path / f"focus-{cx}.json"
        keyframes_data = [{"t": 0.0, "cx": cx, "cy": 0.5}]
        spec.write_text(json.dumps({"keyframes": keyframes_data}), encoding="utf-8")
        output = tmp_path / f"out-{cx}.mp4"
        reframe.render(source, "ad_1x1", output, focus_spec_path=spec)
        frame = tmp_path / f"frame-{cx}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(output), "-frames:v", "1", str(frame)],
            check=True, capture_output=True,
        )
        with Image.open(frame) as image:
            image = image.convert("RGB")
            return image.getpixel((image.width // 2, image.height // 2))

    on_marker = _render_and_sample(marker_cx_norm)
    off_marker = _render_and_sample(0.7)

    assert on_marker[0] > 150 and on_marker[1] < 100 and on_marker[2] < 100  # red at center
    assert not (off_marker[0] > 150 and off_marker[1] < 100 and off_marker[2] < 100)


# --- registration: real asset_record, real schema validation -----------------------


def test_register_reframe_output_with_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from contracts.validate_contracts import validate

    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _p: {"duration": 1.0, "container": "mp4", "video_codec": "h264"},
    )
    master = tmp_path / "master.mp4"
    master.write_bytes(b"master bytes")
    master_record = asset_record.register_asset(master)
    spec = tmp_path / "focus.json"
    spec.write_text(json.dumps({"keyframes": [{"t": 0.0, "cx": 0.5, "cy": 0.5}]}), encoding="utf-8")
    output = tmp_path / "out.mp4"
    output.write_bytes(b"derived output bytes")

    record = reframe.register_reframe_output(
        str(master_record["asset_id"]), output, focus_spec_path=spec
    )

    assert record["role"] == "VARIANT"
    assert len(record["parent_ids"]) == 2
    assert validate("asset", record) == []
