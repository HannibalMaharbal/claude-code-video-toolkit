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


def test_build_focus_spec_cx_clamp_derived_from_crop_width_keeps_face_at_095(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import reframe

    img_path = tmp_path / "dummy.jpg"
    img_path.write_bytes(b"dummy")

    # Mock face detection at far right: cx = 0.95, cy = 0.5
    monkeypatch.setattr(smart_autocrop, "_detect_faces_vision_swift", lambda paths: [{"cx": 0.95, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}}])

    sampled = [(0.0, img_path)]
    keyframes = smart_autocrop.build_focus_spec(sampled)

    assert len(keyframes) == 1
    # Clamping must not truncate to arbitrary 0.8; it must be derived from crop width (~0.8418 for 16:9 -> 9:16)
    assert keyframes[0]["cx"] > 0.8
    assert keyframes[0]["cx"] == pytest.approx(0.8418, abs=0.005)

    # Prove face at 0.95 remains inside the crop window
    x, y, crop_w, crop_h = reframe.compute_crop_window(
        source_w=1920, source_h=1080, target_w=1080, target_h=1920,
        cx=keyframes[0]["cx"], cy=keyframes[0]["cy"]
    )
    face_x = 0.95 * 1920
    assert x <= face_x <= x + crop_w


def test_cy_preserves_measured_value_and_reports_safe_zone_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "input_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    # Mock face detection near top edge: cy = 0.10 (violates safe zone for youtube_short)
    monkeypatch.setattr(smart_autocrop, "_detect_faces_vision_swift", lambda paths: [{"cx": 0.5, "cy": 0.10, "box": {"width": 0.1, "height": 0.1}} for _ in paths])

    result = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=export_dir,
        profile_name="youtube_short",
        sample_interval=1.0,
        render_video=False,
    )

    assert result["status"] == "success_with_warnings"
    # cy must NOT be artificially forced to 0.25
    spec_data = json.loads(Path(result["spec_file"]).read_text(encoding="utf-8"))
    assert spec_data["keyframes"][0]["cy"] <= 0.15

    # Safe-zone violation must be reported as a warning in result
    assert "warnings" in result
    assert len(result["warnings"]) > 0
    assert any("Safe-Zone" in w or "safe" in w.lower() for w in result["warnings"])


def test_smart_autocrop_safe_zone_clean_returns_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "clean_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [{"cx": 0.5, "cy": 0.4, "box": {"width": 0.1, "height": 0.1}} for _ in paths],
    )

    result = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=export_dir,
        profile_name="youtube_short",
        sample_interval=1.0,
        render_video=False,
    )

    assert result["status"] == "success"
    assert result["warnings"] == []


def test_smart_autocrop_strict_safe_zone_blocks_render_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "violating_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [{"cx": 0.5, "cy": 0.05, "box": {"width": 0.1, "height": 0.1}} for _ in paths],
    )

    render_called = False

    def fake_render(*args, **kwargs):
        nonlocal render_called
        render_called = True

    from tools import reframe

    monkeypatch.setattr(reframe, "render", fake_render)

    with pytest.raises(smart_autocrop.AutoCropError, match="Safe-Zone"):
        smart_autocrop.smart_autocrop_video(
            input_video=video_path,
            output_dir=export_dir,
            profile_name="youtube_short",
            sample_interval=1.0,
            render_video=True,
            strict_safe_zone=True,
        )

    assert not render_called


def test_smart_autocrop_cli_strict_safe_zone_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    video_path = _create_synthetic_test_video(tmp_path / "cli_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [{"cx": 0.5, "cy": 0.05, "box": {"width": 0.1, "height": 0.1}} for _ in paths],
    )

    test_args = [
        "smart_autocrop.py",
        "--input",
        str(video_path),
        "--output-dir",
        str(export_dir),
        "--strict-safe-zone",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    ret = smart_autocrop.main()
    assert ret == 1


def test_smart_autocrop_non_16x9_source_detects_dimensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1:1 video (360x360)
    video_path = tmp_path / "square.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=360x360:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    # Face at cx=0.95: in 1:1 video reframed to 9:16 (target ratio 1080/1920 = 0.5625),
    # crop fraction is 0.5625 / 1.0 = 0.5625, half crop is 0.28125.
    # cx must be clamped to 1.0 - 0.28125 = 0.71875 (~0.7188).
    # If 16:9 fallback was used, max cx would be ~0.8418!
    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [{"cx": 0.95, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}} for _ in paths],
    )

    res = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=tmp_path / "out",
        profile_name="youtube_short",
        sample_interval=1.0,
        render_video=False,
    )

    spec = json.loads(Path(res["spec_file"]).read_text(encoding="utf-8"))
    cx = spec["keyframes"][0]["cx"]
    assert cx == pytest.approx(0.7188, abs=0.01)
    assert cx < 0.75


def test_smart_autocrop_raises_on_invalid_metadata(tmp_path: Path) -> None:
    video_path = tmp_path / "corrupt.mp4"
    video_path.write_bytes(b"not a valid video content")
    with pytest.raises(smart_autocrop.AutoCropError):
        smart_autocrop.smart_autocrop_video(
            input_video=video_path,
            output_dir=tmp_path / "out",
            render_video=False,
        )


def test_smart_autocrop_renders_despite_safe_zone_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = _create_synthetic_test_video(tmp_path / "input_16x9.mp4", duration=1)
    export_dir = tmp_path / "export"

    # Mock face near top edge: cy = 0.05 (violates safe zone for youtube_short)
    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [{"cx": 0.5, "cy": 0.05, "box": {"width": 0.1, "height": 0.1}} for _ in paths],
    )

    result = smart_autocrop.smart_autocrop_video(
        input_video=video_path,
        output_dir=export_dir,
        profile_name="youtube_short",
        sample_interval=1.0,
        render_video=True,
    )

    assert result["status"] == "success_with_warnings"
    assert result["output_video"] is not None
    out_video = Path(result["output_video"])
    assert out_video.is_file() and out_video.stat().st_size > 0
    assert len(result["warnings"]) > 0


def test_scene_jump_face_in_crop_within_two_keyframes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import reframe

    img_path = tmp_path / "dummy.jpg"
    img_path.write_bytes(b"dummy")

    # t=0.0: face at left (0.2), t=1.0: jump to right (0.8), t=2.0: stays right (0.8)
    detections = [
        {"cx": 0.2, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}},
        {"cx": 0.8, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}},
        {"cx": 0.8, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}},
    ]
    det_iter = iter(detections)
    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [next(det_iter) for _ in paths],
    )

    sampled = [(0.0, img_path), (1.0, img_path), (2.0, img_path)]
    spec_keyframes = smart_autocrop.build_focus_spec(sampled)

    # In reframe.render(), keyframes are smoothed once
    rendered_keyframes = reframe.smooth_keyframes(spec_keyframes)

    # At keyframe 2 (t=2.0), face at 0.8 must be inside the 9:16 crop of 16:9 source
    source_w, source_h = 1920, 1080
    target_w, target_h = 1080, 1920
    kf2 = rendered_keyframes[2]
    x, y, crop_w, crop_h = reframe.compute_crop_window(
        source_w, source_h, target_w, target_h, kf2["cx"], kf2["cy"]
    )
    face_x = 0.8 * source_w
    assert x <= face_x <= x + crop_w, (
        f"Face at {face_x} is outside crop window [{x}, {x + crop_w}] "
        f"at keyframe 2 (cx={kf2['cx']})"
    )


def test_scene_jump_first_keyframe_focus_within_half_crop_width(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import reframe

    img_path = tmp_path / "dummy.jpg"
    img_path.write_bytes(b"dummy")

    # t=0.0: face at left (0.2), t=1.0: jump to right (0.8)
    detections = [
        {"cx": 0.2, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}},
        {"cx": 0.8, "cy": 0.5, "box": {"width": 0.1, "height": 0.1}},
    ]
    det_iter = iter(detections)
    monkeypatch.setattr(
        smart_autocrop,
        "_detect_faces_vision_swift",
        lambda paths: [next(det_iter) for _ in paths],
    )

    sampled = [(0.0, img_path), (1.0, img_path)]
    spec_keyframes = smart_autocrop.build_focus_spec(sampled)

    source_w, source_h = 1920, 1080
    target_w, target_h = 1080, 1920
    crop_w_rel = (target_w / target_h) / (source_w / source_h)
    half_crop_w = crop_w_rel / 2.0

    rendered_keyframes = reframe.smooth_keyframes(spec_keyframes, cut_threshold=half_crop_w)

    kf1 = rendered_keyframes[1]
    # Focus at first keyframe after jump must be within +-half_crop_w of the new face (0.8)
    assert abs(kf1["cx"] - 0.8) <= half_crop_w, (
        f"Focus cx={kf1['cx']} is not within +-half_crop_w ({half_crop_w}) of face at 0.8"
    )

    x, y, crop_w, crop_h = reframe.compute_crop_window(
        source_w, source_h, target_w, target_h, kf1["cx"], kf1["cy"]
    )
    face_x = 0.8 * source_w
    assert x <= face_x <= x + crop_w, f"Face at {face_x} is outside crop window [{x}, {x + crop_w}]"





