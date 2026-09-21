from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import asset_record, platform_export, platform_profiles, project_init, qc_pipeline


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    return tmp_path


def _make_master(tmp_path: Path, name: str = "master.mp4", duration: float = 2.0) -> Path:
    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def _center_focus_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "focus.json"
    spec.write_text(json.dumps({"keyframes": [{"t": 0.0, "cx": 0.5, "cy": 0.5}]}), encoding="utf-8")
    return spec


def test_make_variant_produces_registered_variant_and_verdict(env: Path) -> None:
    master = _make_master(env)
    master_record = asset_record.register_asset(master, ai_generated="none")
    spec = _center_focus_spec(env)

    result = platform_export.make_variant(
        "demo-project", master_record["asset_id"], "ad_1x1", focus_spec_path=spec
    )

    assert result["draft"] is True  # ad_1x1 starts UNVERIFIED
    assert result["verdict_overall"] in ("needs_human", "reject")
    variant, _path = asset_record.load_asset_record(result["variant_asset_id"])
    assert variant["role"] == "VARIANT"
    assert master_record["asset_id"] in variant["parent_ids"]
    verdict = qc_pipeline.load_verdict("demo-project", result["verdict_id"])
    assert {check["name"] for check in verdict["checks"]} == {"technical", "audio"}


def test_make_variant_output_matches_profile_technical_envelope(env: Path) -> None:
    master = _make_master(env)
    master_record = asset_record.register_asset(master)
    spec = _center_focus_spec(env)

    result = platform_export.make_variant(
        "demo-project", master_record["asset_id"], "ad_1x1", focus_spec_path=spec
    )

    variant, _path = asset_record.load_asset_record(result["variant_asset_id"])
    assert variant["technical"]["width"] == 1080
    assert variant["technical"]["height"] == 1080


def test_make_variant_creates_thumbnail_when_profile_requires_one(env: Path) -> None:
    master = _make_master(env)
    master_record = asset_record.register_asset(master)
    spec = _center_focus_spec(env)

    result = platform_export.make_variant(
        "demo-project", master_record["asset_id"], "ecommerce_video", focus_spec_path=spec
    )

    assert result["thumbnail_asset_id"] is not None
    thumbnail, _path = asset_record.load_asset_record(result["thumbnail_asset_id"])
    assert thumbnail["parent_ids"] == [result["variant_asset_id"]]


def test_make_variant_rejects_non_video_profile(env: Path) -> None:
    master = _make_master(env)
    master_record = asset_record.register_asset(master)

    with pytest.raises(platform_export.PlatformExportError, match="Video-Profil"):
        platform_export.make_variant("demo-project", master_record["asset_id"], "ecommerce_image")


def test_make_variant_registers_subtitle_asset_as_parent_when_burning(env: Path) -> None:
    master = _make_master(env)
    master_record = asset_record.register_asset(master)
    spec = _center_focus_spec(env)
    srt = env / "cues.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8")

    result = platform_export.make_variant(
        "demo-project",
        master_record["asset_id"],
        "ad_1x1",
        focus_spec_path=spec,
        burn_subtitles_path=srt,
    )

    variant, _path = asset_record.load_asset_record(result["variant_asset_id"])
    assert len(variant["parent_ids"]) == 3  # master, focus spec, srt


# --- check_against_profile(): pure technical comparison ------------------------------


def test_check_against_profile_passes_for_conforming_output(env: Path) -> None:
    profile = platform_profiles.get_profile("ad_1x1")
    conforming = env / "conforming.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1080x1080:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            str(conforming),
        ],
        check=True, capture_output=True,
    )
    checks = platform_export.check_against_profile(conforming, profile)
    statuses = {check["name"]: check["status"] for check in checks}
    assert statuses["technical"] == "pass"


def test_check_against_profile_fails_for_wrong_resolution(env: Path) -> None:
    profile = platform_profiles.get_profile("ad_1x1")
    wrong = env / "wrong.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x480:rate=30",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(wrong),
        ],
        check=True, capture_output=True,
    )
    checks = platform_export.check_against_profile(wrong, profile)
    technical = next(check for check in checks if check["name"] == "technical")
    assert technical["status"] == "fail"
    assert "Auflösung" in technical["evidence"]
