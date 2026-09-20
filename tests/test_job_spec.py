from __future__ import annotations

import stat
from pathlib import Path

import pytest
from PIL import Image

from tools import asset_record, job_spec, project_init, reference_registry


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    asset_root = tmp_path / "assets"
    monkeypatch.setattr(asset_record, "ASSET_ROOT", asset_root)
    monkeypatch.setattr(reference_registry, "ASSET_ROOT", asset_root)
    monkeypatch.setattr(reference_registry, "REFSET_ROOT", asset_root / "references" / "sets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    return tmp_path


def _register_person_reference(
    tmp_path: Path, name: str, color: tuple[int, int, int]
) -> dict[str, object]:
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (10, 10), color).save(path)
    return asset_record.register_asset(
        path,
        role="REFERENCE",
        reference_kind="person",
        person_consent="documented",
        purpose_binding=["demo-project"],
        edit_approval=True,
    )


def _bound_project(tmp_path: Path) -> tuple[str, dict[str, object]]:
    project_init.init_project("demo-project")
    front = _register_person_reference(tmp_path, "front", (10, 20, 30))
    profile = _register_person_reference(tmp_path, "profile", (40, 50, 60))
    three_quarter = _register_person_reference(tmp_path, "three_quarter", (70, 80, 90))
    members = [
        {"asset_id": str(front["asset_id"]), "view": "front"},
        {"asset_id": str(profile["asset_id"]), "view": "profile"},
        {"asset_id": str(three_quarter["asset_id"]), "view": "three_quarter"},
    ]
    refset = reference_registry.create_set("PERSON_LOCK", "Anna v1", members)
    reference_registry.bind_project("demo-project", refset["reference_set_id"], "PERSON_LOCK")
    return "demo-project", refset


def test_build_with_no_locks_returns_empty_locks(env: Path) -> None:
    project_init.init_project("bare-project")

    job = job_spec.build("bare-project", "layout_render")

    assert job["locks"] == {}
    assert job["project_id"] == "bare-project"
    assert job["step"] == "layout_render"


def test_build_includes_active_lock_with_set_id_and_hash(env: Path) -> None:
    project_id, refset = _bound_project(env)

    job = job_spec.build(project_id, "image_edit")

    assert job["locks"]["PERSON_LOCK"]["reference_set_id"] == refset["reference_set_id"]
    assert job["locks"]["PERSON_LOCK"]["reference_set_sha256"] == refset["set_sha256"]
    assert job["locks"]["PERSON_LOCK"]["on_drift"] == "qc_fail"


def test_build_rejects_job_when_member_hash_no_longer_matches(env: Path) -> None:
    project_id, refset = _bound_project(env)
    front_asset_id = refset["members"][0]["asset_id"]
    record, _ = asset_record.load_asset_record(front_asset_id)
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    asset_path.chmod(asset_path.stat().st_mode | stat.S_IWUSR)
    asset_path.write_bytes(b"tampered content")

    with pytest.raises(job_spec.JobSpecError, match="Set"):
        job_spec.build(project_id, "image_edit")


def test_build_rejects_empty_step(env: Path) -> None:
    project_init.init_project("bare-project")
    with pytest.raises(job_spec.JobSpecError, match="step"):
        job_spec.build("bare-project", "   ")


def test_build_and_write_persists_job_under_project_jobs_dir(env: Path) -> None:
    project_id, _refset = _bound_project(env)

    job, path = job_spec.build_and_write(project_id, "image_edit")

    assert path.is_file()
    assert path.parent == project_init.PROJECTS_ROOT / project_id / "jobs"
    assert job["job_id"] in path.name


def test_build_and_write_does_not_write_a_rejected_job(env: Path) -> None:
    project_id, refset = _bound_project(env)
    front_asset_id = refset["members"][0]["asset_id"]
    record, _ = asset_record.load_asset_record(front_asset_id)
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    asset_path.chmod(asset_path.stat().st_mode | stat.S_IWUSR)
    asset_path.write_bytes(b"tampered content")

    with pytest.raises(job_spec.JobSpecError):
        job_spec.build_and_write(project_id, "image_edit")

    jobs_dir = project_init.PROJECTS_ROOT / project_id / "jobs"
    assert not jobs_dir.is_dir() or not list(jobs_dir.iterdir())
