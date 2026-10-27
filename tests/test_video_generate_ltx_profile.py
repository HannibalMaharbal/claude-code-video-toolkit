"""M4 Pro/24-GB regression tests for the unified local-video dispatcher."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import video_generate


def test_local_draft_defaults_to_quality_first_distilled_profile(tmp_path: Path) -> None:
    with patch.object(video_generate.subprocess, "run") as run:
        run.return_value.returncode = 0
        result = video_generate._run_ltx_draft("prompt", str(tmp_path / "clip.mp4"))

    assert result == 0
    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--mode") + 1] == "distilled"
    assert cmd[cmd.index("--frames") + 1] == "49"
    assert "--preset" in cmd
    assert cmd[cmd.index("--preset") + 1] == "MAXIMAL"
    assert "--no-sharpen" in cmd


def test_local_profiles_map_to_calibrated_adapter_presets(tmp_path: Path) -> None:
    expected = {"STANDARD": "STANDARD", "HERO": "MAXIMAL"}
    assert video_generate.LOCAL_PROFILE_PRESETS == expected

    for profile, preset in expected.items():
        with patch.object(video_generate.subprocess, "run") as run:
            run.return_value.returncode = 0
            result = video_generate._run_ltx_draft(
                "prompt",
                str(tmp_path / f"{profile}.mp4"),
                local_profile=profile,
            )

        assert result == 0
        cmd = run.call_args.args[0]
        assert cmd[cmd.index("--preset") + 1] == preset


def test_duration_defaults_are_local_two_seconds_and_cloud_five_seconds() -> None:
    assert video_generate._resolve_duration("draft", None) == 2
    assert video_generate._resolve_duration("cloud", None) == 5
    assert video_generate._resolve_duration("draft", 4) == 4


def test_local_sharpen_outputs_exact_1080p_with_calibrated_cas(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    output = tmp_path / "crisp.mp4"

    with (
        patch.object(video_generate.shutil, "which", return_value="/opt/homebrew/bin/ffmpeg"),
        patch.object(
            video_generate.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stderr=""),
        ) as run,
    ):
        assert video_generate._run_local_hardware_sharpen(str(source), str(output), cas=0.45)

    cmd = run.call_args.args[0]
    vf = cmd[cmd.index("-vf") + 1]
    assert "crop=" in vf
    assert "scale=1920:1080" in vf
    assert "cas=0.45" in vf
    assert "cas=0.6" not in vf
    assert cmd[cmd.index("-b:v") + 1] == "24M"


def test_local_profiles_use_less_sharpening_for_higher_resolution() -> None:
    assert video_generate.LOCAL_PROFILE_CAS == {"STANDARD": 0.45, "HERO": 0.35}


def test_quality_first_default_profile_is_hero() -> None:
    assert video_generate.DEFAULT_LOCAL_PROFILE == "HERO"
