import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "tools" / "seedvr2_mlx_adapter.py"
SPEC = importlib.util.spec_from_file_location("seedvr2_mlx_adapter", MODULE_PATH)
seedvr2 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(seedvr2)


def _complete_model(model: Path) -> None:
    for component in ("transformer", "vae"):
        component_dir = model / component
        component_dir.mkdir(parents=True)
        shard = component_dir / "0.safetensors"
        shard.write_bytes(b"weights")
        (component_dir / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {f"{component}.weight": shard.name}}),
            encoding="utf-8",
        )


def _run(tmp_path: Path, **overrides):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "enhanced.mp4"
    model = tmp_path / "model"
    _complete_model(model)

    def completed(cmd, **kwargs):
        output.write_bytes(b"enhanced-video")
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    options = {
        "input_path": str(source),
        "output_path": str(output),
        "verbose": False,
    }
    options.update(overrides)
    with (
        patch.object(seedvr2, "MODEL_PATH", model),
        patch.object(seedvr2.shutil, "which", return_value="/usr/local/bin/mflux-upscale-seedvr2"),
        patch.object(seedvr2.subprocess, "run", side_effect=completed) as run,
    ):
        result = seedvr2.enhance_video(**options)
    command = run.call_args.args[0] if run.call_args else None
    return result, command


def test_default_command_is_local_safe_and_temporally_coherent(tmp_path):
    result, cmd = _run(tmp_path)

    assert result["success"] is True
    assert cmd[cmd.index("--resolution") + 1] == "1x"
    assert cmd[cmd.index("--color-correction") + 1] == "wavelet"
    assert cmd[cmd.index("--temporal-chunk-size") + 1] == "49"
    assert cmd[cmd.index("--temporal-chunk-overlap") + 1] == "16"
    assert "--low-ram" in cmd
    assert "--no-replace" in cmd
    assert "--drop-audio" not in cmd


def test_existing_output_is_never_overwritten(tmp_path):
    source = tmp_path / "source.mp4"
    output = tmp_path / "existing.mp4"
    source.write_bytes(b"video")
    output.write_bytes(b"keep-me")

    result = seedvr2.enhance_video(str(source), str(output), verbose=False)

    assert result["success"] is False
    assert "existiert bereits" in result["error"]
    assert output.read_bytes() == b"keep-me"


def test_incomplete_model_fails_before_launch(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    model = tmp_path / "model"
    model.mkdir()

    with patch.object(seedvr2, "MODEL_PATH", model):
        result = seedvr2.enhance_video(str(source), str(tmp_path / "out.mp4"), verbose=False)

    assert result["success"] is False
    assert "unvollständig" in result["error"]


def test_invalid_temporal_profile_is_rejected(tmp_path):
    result, _ = _run(tmp_path, temporal_chunk_size=48)

    assert result["success"] is False
    assert "4n+1" in result["error"]


def test_overlap_must_be_divisible_by_four(tmp_path):
    result, command = _run(tmp_path, temporal_chunk_overlap=14)

    assert result["success"] is False
    assert "durch 4 teilbar" in result["error"]
    assert command is None


def test_dry_run_builds_command_without_starting_inference(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    model = tmp_path / "model"
    _complete_model(model)

    with (
        patch.object(seedvr2, "MODEL_PATH", model),
        patch.object(seedvr2.shutil, "which", return_value="/usr/local/bin/mflux-upscale-seedvr2"),
        patch.object(seedvr2.subprocess, "run") as run,
    ):
        result = seedvr2.enhance_video(
            str(source), str(tmp_path / "out.mp4"), dry_run=True, verbose=False
        )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert "--video-path" in result["command"]
    run.assert_not_called()


def test_guarded_override_rejects_when_workload_exceeds_available_memory(tmp_path):
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(1920, 1080)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=14_500_000_000),
    ):
        result, command = _run(
            tmp_path,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert result["success"] is False
    assert "real verifizierten Bereich" in result["error"]
    assert command is None


def test_guarded_override_adds_runtime_flag_after_memory_preflight(tmp_path):
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(640, 360)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=14_500_000_000),
    ):
        result, command = _run(
            tmp_path,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert result["success"] is True
    assert "--force-unsafe-video-memory" in command
    assert result["guarded_memory_override"] is True
    assert result["memory_plan"]["output_size"] == "640x352"
    assert result["memory_plan"]["calibrated_working_gb"] > 3.0


def test_guarded_override_fails_closed_when_memory_is_unavailable(tmp_path):
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(640, 360)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=None),
    ):
        result, command = _run(
            tmp_path,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert result["success"] is False
    assert "nicht sicher messen" in result["error"]
    assert command is None


def test_guarded_override_rejects_2x_after_real_metal_oom(tmp_path):
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(640, 360)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=14_500_000_000),
    ):
        scaled, scaled_command = _run(
            tmp_path,
            guarded_memory_override=True,
            resolution="2x",
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert scaled["success"] is False
    assert "Upscaling (>1x)" in scaled["error"]
    assert scaled_command is None


def test_guarded_override_rejects_cache_above_one_gb(tmp_path):
    result, command = _run(
        tmp_path,
        guarded_memory_override=True,
        temporal_chunk_size=5,
        temporal_chunk_overlap=4,
        max_frames=5,
        cache_limit_gb=1.01,
    )

    assert result["success"] is False
    assert "maximal 1 GB" in result["error"]
    assert command is None


def test_guarded_override_accepts_one_gb_cache_boundary(tmp_path):
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(640, 360)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=14_500_000_000),
    ):
        result, command = _run(
            tmp_path,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
            cache_limit_gb=1.0,
        )

    assert result["success"] is True
    assert command[command.index("--mlx-cache-limit-gb") + 1] == "1.0"


def test_guarded_override_preserves_13gb_empirical_floor(tmp_path):
    below_dir = tmp_path / "below"
    below_dir.mkdir()
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(128, 128)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=12_999_999_999),
    ):
        below, below_command = _run(
            below_dir,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert below["success"] is False
    assert below["memory_plan"]["required_available_gb"] == 13.0
    assert below_command is None

    boundary_dir = tmp_path / "boundary"
    boundary_dir.mkdir()
    with (
        patch.object(seedvr2, "_probe_video_size", return_value=(128, 128)),
        patch.object(seedvr2, "_host_available_memory_bytes", return_value=13_000_000_000),
    ):
        boundary, boundary_command = _run(
            boundary_dir,
            guarded_memory_override=True,
            temporal_chunk_size=5,
            temporal_chunk_overlap=4,
            max_frames=5,
        )

    assert boundary["success"] is True
    assert boundary["memory_plan"]["required_available_gb"] == 13.0
    assert "--force-unsafe-video-memory" in boundary_command


def test_guarded_override_requires_bounded_total_length(tmp_path):
    result, command = _run(
        tmp_path,
        guarded_memory_override=True,
        temporal_chunk_size=5,
        temporal_chunk_overlap=4,
        max_frames=None,
    )

    assert result["success"] is False
    assert "Gesamtlänge" in result["error"]
    assert command is None


def test_working_set_estimator_matches_upstream_reference_values():
    estimate = seedvr2._estimated_working_set_bytes(
        frame_count=49,
        width=1920,
        height=1072,
    )

    assert round(estimate / (1000**3), 2) == 14.12


def test_resolution_geometry_matches_upstream_crop_rules():
    assert seedvr2._resolved_output_size((1920, 1080), "1x") == (1920, 1072)
    assert seedvr2._resolved_output_size((640, 360), "2x") == (1280, 720)
    assert seedvr2._resolved_output_size((1920, 1080), "720") == (1280, 720)
    assert seedvr2._resolved_output_size((640, 360), "invalid") is None


def test_video_probe_reads_ffprobe_geometry(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    completed = type(
        "Result",
        (),
        {"stdout": json.dumps({"streams": [{"width": 640, "height": 360}]})},
    )()

    with (
        patch.object(seedvr2.shutil, "which", return_value="/opt/homebrew/bin/ffprobe"),
        patch.object(seedvr2.subprocess, "run", return_value=completed),
    ):
        assert seedvr2._probe_video_size(source) == (640, 360)
