from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools import asset_record, project_init, provenance_report, qc_pipeline


def _write_record(root: Path, asset_id: str, *, parent_ids: list[str] | None = None) -> None:
    media = root / "source" / f"{asset_id}.bin"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(asset_id.encode("utf-8"))
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": "SOURCE" if not parent_ids else "MASTER",
        "media_type": "video",
        "path": media.relative_to(root).as_posix(),
        "sha256": asset_record.sha256_file(media),
        "bytes": media.stat().st_size,
        "created_at": datetime.now(UTC).isoformat(),
        "lifecycle": "ingested" if not parent_ids else "analysed",
        "rights": {
            "rights_status": "OWNED",
            "commercial_use": "allowed",
            "person_consent": "not_needed",
            "provider_data_scope": "local",
        },
        "ai_involvement": {"ai_generated": "none"},
    }
    if parent_ids:
        record["parent_ids"] = parent_ids
        record["derivation"] = {"tool": "ffmpeg", "operation": "trim", "tool_version": "9.0.2"}
    media.with_name(f"{asset_id}.asset.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    return tmp_path


def test_build_asset_provenance_walks_parents(env: Path) -> None:
    root = asset_record.ASSET_ROOT
    _write_record(root, "ast_" + "a" * 12)
    _write_record(root, "ast_" + "b" * 12, parent_ids=["ast_" + "a" * 12])

    node = provenance_report.build_asset_provenance("ast_" + "b" * 12)

    assert node["asset_id"] == "ast_" + "b" * 12
    assert node["derivation"]["tool"] == "ffmpeg"
    assert len(node["parents"]) == 1
    assert node["parents"][0]["asset_id"] == "ast_" + "a" * 12
    assert "parents" not in node["parents"][0]


def test_build_asset_provenance_detects_cycles(env: Path) -> None:
    root = asset_record.ASSET_ROOT
    a, b = "ast_" + "c" * 12, "ast_" + "d" * 12
    _write_record(root, a, parent_ids=[b])
    _write_record(root, b, parent_ids=[a])

    with pytest.raises(provenance_report.ProvenanceError, match="Zyklus"):
        provenance_report.build_asset_provenance(a)


def test_generate_report_includes_qc_and_cost(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = asset_record.ASSET_ROOT
    asset_id = "ast_" + "e" * 12
    _write_record(root, asset_id)
    project_init.add_asset_id("demo-project", asset_id)
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _p: {"duration": 1.0, "container": "mp4", "video_codec": "h264"},
    )
    qc_pipeline.write_verdict(
        "demo-project", asset_id, [{"name": "technical", "status": "pass", "evidence": "ok"}]
    )
    manifest = project_init.load_project_manifest("demo-project")
    manifest["cost_decisions"] = [
        {
            "step": "render",
            "cost_class": "local_deterministic",
            "known_cost": None,
            "quota_status": "ok",
            "fallback_reason": None,
            "approval_required": False,
        }
    ]
    project_init.save_project_manifest("demo-project", manifest)

    report = provenance_report.generate_report("demo-project")

    assert report["project_id"] == "demo-project"
    assert len(report["asset_graphs"]) == 1
    assert len(report["qc_verdicts"]) == 1
    assert len(report["cost_decisions"]) == 1
    assert report["ai_involvement_summary"]["ai_generated_values"] == ["none"]
    assert report["c2pa_manifests"][0]["instanceId"] == asset_id
    assert report["c2pa_manifests"][0]["signature"] is None


def test_write_report_creates_files_and_sets_provenance_status(env: Path) -> None:
    root = asset_record.ASSET_ROOT
    asset_id = "ast_" + "f" * 12
    _write_record(root, asset_id)
    project_init.add_asset_id("demo-project", asset_id)

    report, json_path, md_path = provenance_report.write_report("demo-project")

    assert json_path.is_file()
    assert md_path.is_file()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["project_id"] == "demo-project"
    assert "# Provenance Report" in md_path.read_text(encoding="utf-8")
    manifest = project_init.load_project_manifest("demo-project")
    assert manifest["provenance_status"] == "internal_hash_graph"


def test_write_report_refuses_to_collide_on_the_same_timestamp(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return datetime(2026, 9, 21, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(provenance_report, "datetime", _FixedDatetime)
    root = asset_record.ASSET_ROOT
    asset_id = "ast_" + "g" * 12
    _write_record(root, asset_id)
    project_init.add_asset_id("demo-project", asset_id)

    provenance_report.write_report("demo-project")
    with pytest.raises(provenance_report.ProvenanceError, match="existiert bereits"):
        provenance_report.write_report("demo-project")


def test_set_labeling_updates_manifest_and_writes_audit_line(env: Path) -> None:
    from contracts.validate_contracts import validate

    manifest = provenance_report.set_labeling(
        "demo-project", "required_pending", note="Braucht KI-Kennzeichnung", by="constantin"
    )

    assert manifest["ai_labeling_status"] == "required_pending"
    assert validate("project", manifest) == []
    audit_path = (
        project_init.PROJECTS_ROOT / "demo-project" / "provenance" / "labeling-audit.log.jsonl"
    )
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["new_status"] == "required_pending"
    assert entries[0]["by"] == "constantin"


def test_set_labeling_rejects_not_assessed(env: Path) -> None:
    with pytest.raises(provenance_report.ProvenanceError, match="status"):
        provenance_report.set_labeling(
            "demo-project", "not_assessed", note="x", by="constantin"
        )


def test_set_labeling_rejects_empty_note(env: Path) -> None:
    with pytest.raises(provenance_report.ProvenanceError, match="note"):
        provenance_report.set_labeling(
            "demo-project", "assessed_not_required", note="  ", by="constantin"
        )
