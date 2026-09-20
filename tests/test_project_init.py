from __future__ import annotations

from pathlib import Path

import pytest

from tools import project_init


@pytest.fixture
def projects_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", root)
    return root


def test_init_project_creates_all_subdirs(projects_root: Path) -> None:
    project_init.init_project("demo-project")

    for subdir in project_init.PROJECT_SUBDIRS:
        assert (projects_root / "demo-project" / subdir).is_dir()


def test_init_project_writes_a_schema_valid_manifest(projects_root: Path) -> None:
    from contracts.validate_contracts import validate

    manifest = project_init.init_project("demo-project")

    assert validate("project", manifest) == []
    on_disk = project_init.load_project_manifest("demo-project")
    assert on_disk == manifest


def test_init_project_rejects_invalid_project_id(projects_root: Path) -> None:
    with pytest.raises(project_init.ProjectInitError, match="Muster"):
        project_init.init_project("Not_Valid!")
    assert not projects_root.exists() or not list(projects_root.iterdir())


def test_init_project_refuses_duplicate(projects_root: Path) -> None:
    project_init.init_project("demo-project")
    with pytest.raises(project_init.ProjectInitError, match="existiert bereits"):
        project_init.init_project("demo-project")


def test_init_project_writes_brief_file(projects_root: Path) -> None:
    project_init.init_project("demo-project", brief_text="# Custom brief\n")

    brief = (projects_root / "demo-project" / "brief" / "brief.md").read_text(encoding="utf-8")
    assert brief == "# Custom brief\n"


def test_load_project_manifest_rejects_unknown_project(projects_root: Path) -> None:
    with pytest.raises(project_init.ProjectInitError, match="nicht lesbar"):
        project_init.load_project_manifest("does-not-exist")


def test_save_project_manifest_round_trips(projects_root: Path) -> None:
    manifest = project_init.init_project("demo-project")
    manifest["provenance_status"] = "internal_hash_graph"

    project_init.save_project_manifest("demo-project", manifest)

    assert project_init.load_project_manifest("demo-project")["provenance_status"] == (
        "internal_hash_graph"
    )


def test_save_project_manifest_rejects_schema_violation_without_writing(
    projects_root: Path,
) -> None:
    manifest = project_init.init_project("demo-project")
    before = (projects_root / "demo-project" / "manifests" / "project.manifest.json").read_text(
        encoding="utf-8"
    )
    broken = dict(manifest)
    broken["provenance_status"] = "not-a-real-status"

    with pytest.raises(project_init.ProjectInitError, match="Schema"):
        project_init.save_project_manifest("demo-project", broken)

    after = (projects_root / "demo-project" / "manifests" / "project.manifest.json").read_text(
        encoding="utf-8"
    )
    assert after == before


def test_save_project_manifest_refuses_unknown_project(projects_root: Path) -> None:
    manifest = {
        "schema_version": "1.0.0",
        "project_id": "ghost",
        "created_at": "2026-09-20T00:00:00+00:00",
        "brief_ref": "brief/brief.md",
        "asset_ids": [],
        "lock_policy": {},
        "cost_decisions": [],
        "delivery_targets": [],
        "provenance_status": "none",
        "ai_labeling_status": "not_assessed",
    }
    with pytest.raises(project_init.ProjectInitError, match="nicht gefunden"):
        project_init.save_project_manifest("ghost", manifest)
