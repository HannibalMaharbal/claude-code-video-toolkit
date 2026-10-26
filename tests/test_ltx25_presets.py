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


@pytest.mark.parametrize("w,h", [(704, 480), (512, 288)])
def test_two_stage_modes_reject_resolutions_off_the_64px_grid(tmp_path, w, h):
    # Ohne Validierung würde hier ein echter Render starten: Subprozesse sind hart blockiert.
    with patch.object(ltx.subprocess, "run", side_effect=AssertionError("kein Render erlaubt")) as run, \
         patch.object(ltx, "_ensure_ollama_unloaded"):
        result = ltx.generate_video("x", str(tmp_path / "o.mp4"), width=w, height=h, verbose=False)
    run.assert_not_called()
    assert result["success"] is False
    assert "64" in result["error"]


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
