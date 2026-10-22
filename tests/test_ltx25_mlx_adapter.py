import importlib.util
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "tools" / "ltx25_mlx_adapter.py"
SPEC = importlib.util.spec_from_file_location("ltx25_mlx_adapter", MODULE_PATH)
ltx = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ltx)


def _run(tmp_path: Path, mode: str, image: str | None = None):
    output = tmp_path / "clip.mp4"
    runtime = tmp_path / "runtime"
    model = tmp_path / "model"
    runtime.mkdir()
    model.mkdir()
    (model / "transformer-dev.safetensors").touch()
    if image:
        image_path = tmp_path / image
        image_path.write_bytes(b"reference-image")
        image = str(image_path)

    def completed(cmd, **kwargs):
        output.write_bytes(b"video")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch.object(ltx.shutil, "which", return_value="/usr/bin/uv"),
        patch.object(ltx, "RUNTIME_DIR", runtime),
        patch.object(ltx, "MODEL_PATH", model),
        patch.object(ltx.subprocess, "run", side_effect=completed) as run,
    ):
        result = ltx.generate_video(
            "A luxury car rolls slowly through a studio.",
            str(output),
            mode=mode,
            image=image,
            verbose=False,
        )
    return result, run.call_args.args[0]


def test_hq_mode_keeps_native_quality_defaults(tmp_path):
    result, cmd = _run(tmp_path, "two-stages-hq")

    assert result["success"] is True
    assert "--enable-teacache" not in cmd
    assert "--stage1-steps" not in cmd


def test_balanced_two_stage_retains_acceleration(tmp_path):
    _, cmd = _run(tmp_path, "two-stage")

    assert "--enable-teacache" in cmd
    assert cmd[cmd.index("--teacache-thresh") + 1] == "0.7"


def test_prompt_gets_continuity_and_motion_constraints(tmp_path):
    result, cmd = _run(tmp_path, "distilled", image="reference.png")
    prompt = cmd[cmd.index("--prompt") + 1]

    assert "same subject, physical set, wardrobe, and props" in prompt
    assert "smooth motivated camera movement" in prompt
    assert "Preserve the reference image" in prompt
    assert "no spatial teleportation" in prompt
    assert result["prompt_enhanced"] is True


def test_prompt_enhancement_is_idempotent():
    once = ltx.enhance_ltx_prompt("A quiet close-up.")

    assert ltx.enhance_ltx_prompt(once) == once


def test_continuation_extracts_last_frame_and_uses_it_as_image_anchor(tmp_path):
    previous = tmp_path / "previous.mp4"
    previous.write_bytes(b"previous-video")
    output = tmp_path / "continued.mp4"
    runtime = tmp_path / "runtime"
    model = tmp_path / "model"
    runtime.mkdir()
    model.mkdir()

    calls = []

    def completed(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "/usr/bin/ffmpeg":
            Path(cmd[-1]).write_bytes(b"last-frame")
        else:
            output.write_bytes(b"continued-video")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with (
        patch.object(
            ltx.shutil,
            "which",
            side_effect=lambda name: f"/usr/bin/{name}" if name in {"uv", "ffmpeg"} else None,
        ),
        patch.object(ltx, "RUNTIME_DIR", runtime),
        patch.object(ltx, "MODEL_PATH", model),
        patch.object(ltx.subprocess, "run", side_effect=completed),
    ):
        result = ltx.generate_video(
            "The car continues rolling forward.",
            str(output),
            continue_from=str(previous),
            verbose=False,
        )

    assert result["success"] is True
    assert result["continuation_source"] == str(previous)
    assert calls[0][:7] == [
        "/usr/bin/ffmpeg",
        "-y",
        "-sseof",
        "-1",
        "-i",
        str(previous),
        "-vf",
    ]
    assert calls[0][7] == "reverse"
    generation_cmd = calls[1]
    anchor = Path(generation_cmd[generation_cmd.index("--image") + 1])
    assert "Preserve the reference image" in generation_cmd[generation_cmd.index("--prompt") + 1]
    assert not anchor.exists()


def test_continuation_and_image_are_mutually_exclusive(tmp_path):
    result = ltx.generate_video(
        "Continue.",
        str(tmp_path / "out.mp4"),
        image="still.png",
        continue_from="previous.mp4",
        verbose=False,
    )

    assert result["success"] is False
    assert "nicht gleichzeitig" in result["error"]


def test_missing_image_fails_before_runtime_lookup(tmp_path):
    result = ltx.generate_video(
        "Animate.",
        str(tmp_path / "out.mp4"),
        image=str(tmp_path / "missing.png"),
        verbose=False,
    )

    assert result["success"] is False
    assert "Eingabebild fehlt" in result["error"]
