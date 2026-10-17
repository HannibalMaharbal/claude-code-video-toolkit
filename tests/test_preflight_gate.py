"""Unit tests for tools/preflight_gate.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools.preflight_gate import compute_sha256, validate_manifest


@pytest.fixture
def sample_workspace(tmp_path: Path):
    """Creates a temporary workspace with master image and shots."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    master_file = images_dir / "candidate_master_01.png"
    master_file.write_bytes(b"master_henri_portrait_v1_bytes")
    master_sha = hashlib.sha256(b"master_henri_portrait_v1_bytes").hexdigest()

    shots_dir = tmp_path / "scenes"
    shots_dir.mkdir()

    shot_files = []
    shot_shas = []
    for i in range(1, 12):
        s_file = shots_dir / f"shot_{i:02d}.png"
        content = f"scene_{i}_bytes_derived_from_master".encode()
        s_file.write_bytes(content)
        shot_files.append(s_file)
        shot_shas.append(hashlib.sha256(content).hexdigest())

    manifest = {
        "project_id": "paris-1920-cafe",
        "target_duration_sec": 60.0,
        "technical_specs": {"fps": 24.0, "resolution": "1920x1080"},
        "master_asset": {
            "path": "images/candidate_master_01.png",
            "sha256": master_sha,
            "model": "flux-dev",
            "seed": 812734,
        },
        "shots": [
            {
                "id": f"shot-{i:02d}",
                "source": f"scenes/shot_{i:02d}.png",
                "sha256": shot_shas[i - 1],
                "derived_from_master_sha256": master_sha,
                "duration_frames": 168,  # 7 seconds each @ 24fps -> 77s total (~28% reserve)
            }
            for i in range(1, 12)
        ],
    }
    return tmp_path, manifest, master_file, master_sha


def test_preflight_valid_manifest(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    report = validate_manifest(manifest, base_dir=base_dir, min_handle_reserve_pct=10.0)
    assert report.is_valid is True
    assert len(report.errors) == 0
    assert report.verified_assets == 12  # 1 master + 11 shots
    assert report.total_planned_duration_sec == 77.0
    assert report.handle_reserve_pct == 28.3


def test_preflight_catches_cache_drift_when_master_changed(sample_workspace):
    """
    Simulates the exact Paris 1920 failure:
    Master was updated, but the scenes still reference the old master hash!
    """
    base_dir, manifest, master_file, old_sha = sample_workspace

    # Modify master file with new Henri face
    master_file.write_bytes(b"master_henri_NEW_FACE_PORTRAIT")
    new_master_sha = hashlib.sha256(b"master_henri_NEW_FACE_PORTRAIT").hexdigest()

    # Update master sha in manifest, but shots still derived from old sha
    manifest["master_asset"]["sha256"] = new_master_sha

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("Asset-Inkonsistenz / Cache-Drift" in err for err in report.errors)


def test_preflight_rejects_wildcards(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    manifest["shots"][0]["source"] = "scenes/shot_*.png"  # Illegal wildcard

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("Wildcards im Pfad" in err for err in report.errors)


def test_preflight_rejects_missing_file(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    manifest["shots"][0]["source"] = "scenes/non_existent.png"

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("existiert nicht" in err for err in report.errors)


def test_preflight_rejects_insufficient_duration(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    # Shorten frames to only 40 seconds total
    for s in manifest["shots"]:
        s["duration_frames"] = 80  # ~3.3s each * 11 = ~36.6s total

    report = validate_manifest(manifest, base_dir=base_dir, min_handle_reserve_pct=10.0)
    assert report.is_valid is False
    assert any("Gesamtlaufzeit unzureichend" in err for err in report.errors)


def test_preflight_rejects_duplicate_shot_ids(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    manifest["shots"][1]["id"] = manifest["shots"][0]["id"]  # Duplicate ID

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("Doppelte Shot-ID entdeckt" in err for err in report.errors)


def test_preflight_rejects_path_traversal(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    manifest["shots"][0]["source"] = "../../etc/passwd"

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("Pfad-Traversal" in err for err in report.errors)


def test_preflight_rejects_symlinks(sample_workspace):
    base_dir, manifest, _, _ = sample_workspace
    symlink_file = base_dir / "scenes" / "symlink_shot.png"
    target_file = base_dir / "scenes" / "shot_01.png"
    symlink_file.symlink_to(target_file)

    manifest["shots"][0]["source"] = "scenes/symlink_shot.png"

    report = validate_manifest(manifest, base_dir=base_dir)
    assert report.is_valid is False
    assert any("Symlinks sind im Produktions-Manifest verboten" in err for err in report.errors)

