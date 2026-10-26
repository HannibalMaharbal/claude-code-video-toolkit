"""Regressionen aus dem Claude-Audit vom 26.10.2026 (Argon-Presets, M2)."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "ltx25_mlx_adapter.py"
SPEC = importlib.util.spec_from_file_location("ltx25_mlx_adapter_presets", MODULE_PATH)
ltx = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ltx)


def _settings(argv):
    parser = ltx.build_parser()
    return ltx.resolve_settings(parser.parse_args(argv))


def test_explicit_frames_are_not_overridden_by_preset():
    s = _settings(["--prompt", "x", "--output", "o.mp4", "--preset", "MAXIMAL", "--frames", "49"])
    assert (s.width, s.height, s.frames) == (1024, 576, 49)


def test_preset_supplies_defaults_when_not_given():
    s = _settings(["--prompt", "x", "--output", "o.mp4", "--preset", "ENTWURF"])
    assert (s.width, s.height, s.frames, s.cas) == (640, 384, 49, 0.35)


def test_no_preset_defaults_to_standard_grid():
    s = _settings(["--prompt", "x", "--output", "o.mp4"])
    assert (s.width, s.height) == (768, 448)


def test_every_preset_is_on_the_64px_grid_and_8k_plus_1():
    for name, cfg in ltx.VIDEO_QUALITY_PRESETS.items():
        assert cfg["width"] % 64 == 0 and cfg["height"] % 64 == 0, name
        assert (cfg["frames"] - 1) % 8 == 0, name


def test_generate_video_default_resolution_is_on_64px_grid():
    import inspect
    sig = inspect.signature(ltx.generate_video)
    assert sig.parameters["width"].default % 64 == 0
    assert sig.parameters["height"].default % 64 == 0


@pytest.mark.parametrize("w,h", [(704, 480), (480, 704), (512, 288)])
def test_existing_32px_grid_consumers_remain_supported(tmp_path, w, h):
    cmd, _ = _cmd_for(tmp_path, width=w, height=h)
    assert "--width" in cmd and str(w) in cmd
    assert "--height" in cmd and str(h) in cmd


def test_resolution_off_the_32px_grid_is_rejected(tmp_path):
    with patch.object(ltx.subprocess, "run", side_effect=AssertionError("kein Render erlaubt")) as run:
        result = ltx.generate_video("x", str(tmp_path / "o.mp4"), width=704, height=472, verbose=False)
    run.assert_not_called()
    assert result["success"] is False
    assert "32" in result["error"]


def _cmd_for(tmp_path, **kwargs):
    output = tmp_path / "clip.mp4"
    runtime, model = tmp_path / "runtime", tmp_path / "model"
    runtime.mkdir(exist_ok=True); model.mkdir(exist_ok=True)
    for name in ("start.png", "end.png"):
        (tmp_path / name).write_bytes(b"img")

    def completed(cmd, **kw):
        output.write_bytes(b"video")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch.object(ltx.shutil, "which", return_value="/usr/bin/uv"),
        patch.object(ltx, "RUNTIME_DIR", runtime),
        patch.object(ltx, "MODEL_PATH", model),
        patch.object(ltx.subprocess, "run", side_effect=completed) as run,
    ):
        ltx.generate_video("x", str(output), verbose=False, **kwargs)
    return run.call_args.args[0], run.call_args.kwargs.get("env", {})


def _image_args(cmd):
    idx = [i for i, a in enumerate(cmd) if a == "--image"]
    return [cmd[i + 1:i + 5] for i in idx]


def test_image_crf_is_passed_per_image_without_runtime_patch(tmp_path):
    cmd, env = _cmd_for(tmp_path, image=str(tmp_path / "start.png"))
    assert _image_args(cmd)[0][1:4] == ["0", "1.0", "0"]
    assert "LTX_IMAGE_CRF" not in env


def test_keyframe_images_both_get_lossless_crf(tmp_path):
    cmd, _ = _cmd_for(tmp_path, image=str(tmp_path / "start.png"), end_image=str(tmp_path / "end.png"), frames=49)
    args = _image_args(cmd)
    assert args[0][1:4] == ["0", "1.0", "0"]
    assert args[1][1:4] == ["48", "1.0", "0"]


def test_preset_cas_reaches_sharpening(tmp_path):
    output = tmp_path / "clip.mp4"
    runtime, model = tmp_path / "runtime", tmp_path / "model"
    runtime.mkdir(); model.mkdir()

    def completed(cmd, **kwargs):
        output.write_bytes(b"video")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch.object(ltx.shutil, "which", return_value="/usr/bin/uv"),
        patch.object(ltx, "RUNTIME_DIR", runtime),
        patch.object(ltx, "MODEL_PATH", model),
        patch.object(ltx.subprocess, "run", side_effect=completed),
        patch.object(ltx, "sharpen_video", return_value=True) as sharpen,
    ):
        ltx.generate_video("x", str(output), sharpen=True, cas=0.35, verbose=False)
    assert sharpen.call_args.kwargs["cas"] == 0.35
