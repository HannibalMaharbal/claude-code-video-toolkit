import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tools import asset_record, delivery_gate, project_init

    root = tmp_path / "assets"
    monkeypatch.setattr(asset_record, "ASSET_ROOT", root)
    monkeypatch.setattr(delivery_gate, "ASSET_ROOT", root)
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _path: {
            "duration": 1.0,
            "width": 1920,
            "height": 1080,
            "fps": 25.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "container": "mp4",
        },
    )
    return root, asset_record, delivery_gate


def _accept_qc(asset_id: str, *, project_id: str = "qc-project") -> None:
    """Run the real QC pipeline end-to-end and record a genuine human accept."""
    from tools import project_init, qc_pipeline

    try:
        project_init.load_project_manifest(project_id)
    except project_init.ProjectInitError:
        project_init.init_project(project_id)
    verdict = qc_pipeline.run_qc(project_id, asset_id)
    qc_pipeline.apply_review(
        project_id, verdict["verdict_id"], reviewer="qa-lead", overall="accept"
    )


def _parent(
    root: Path,
    asset_record,
    *,
    asset_id: str,
    rights: dict[str, object],
    ai_generated: str = "none",
) -> dict[str, object]:
    media = root / "source" / f"{asset_id}.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(asset_id.encode("utf-8"))
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": "SOURCE",
        "media_type": "video",
        "path": media.relative_to(root).as_posix(),
        "sha256": asset_record.sha256_file(media),
        "bytes": media.stat().st_size,
        "created_at": datetime.now(UTC).isoformat(),
        "lifecycle": "ingested",
        "rights": rights,
        "ai_involvement": {"ai_generated": ai_generated},
    }
    media.with_name(f"{asset_id}.asset.json").write_text(json.dumps(record), encoding="utf-8")
    return record


def _approved_rights() -> dict[str, object]:
    return {
        "rights_status": "OWNED",
        "commercial_use": "allowed",
        "person_consent": "not_needed",
        "provider_data_scope": "local",
    }


def _output(tmp_path: Path, name: str = "output.mp4") -> Path:
    output = tmp_path / name
    output.write_bytes(f"derived media {name}".encode())
    return output


def test_unknown_parent_stays_unknown_and_gate_rejects(registry, tmp_path: Path) -> None:
    root, asset_record, delivery_gate = registry
    parent = _parent(
        root,
        asset_record,
        asset_id="ast_unknownparent",
        rights={
            "rights_status": "UNKNOWN",
            "commercial_use": "unknown",
            "person_consent": "unknown",
            "provider_data_scope": "cloud_not_approved",
        },
        ai_generated="unknown",
    )

    child = asset_record.register_derived(
        _output(tmp_path),
        parents=[parent["asset_id"]],
        role="MASTER",
        tool="ffmpeg",
        operation="cut",
    )

    assert child["rights"]["rights_status"] == "UNKNOWN"
    assert child["ai_involvement"]["ai_generated"] == "unknown"
    assert delivery_gate.check(child["asset_id"])["allowed"] is False


def test_derived_asset_from_approved_parents_passes_gate(registry, tmp_path: Path) -> None:
    root, asset_record, delivery_gate = registry
    first = _parent(root, asset_record, asset_id="ast_approvedone1", rights=_approved_rights())
    second = _parent(root, asset_record, asset_id="ast_approvedtwo2", rights=_approved_rights())

    child = asset_record.register_derived(
        _output(tmp_path),
        parents=[first["asset_id"], second["asset_id"]],
        role="MASTER",
        tool="ffmpeg",
        operation="concat",
    )

    assert delivery_gate.check(child["asset_id"]) == {"allowed": True, "reasons": []}


def test_mixed_parents_inherit_the_most_restrictive_values(registry, tmp_path: Path) -> None:
    root, asset_record, _delivery_gate = registry
    first = _parent(root, asset_record, asset_id="ast_mixedone1234", rights=_approved_rights())
    second = _parent(
        root,
        asset_record,
        asset_id="ast_mixedtwo1234",
        rights={
            "rights_status": "RESTRICTED",
            "commercial_use": "restricted",
            "person_consent": "missing",
            "provider_data_scope": "cloud_not_approved",
        },
        ai_generated="full",
    )

    child = asset_record.register_derived(
        _output(tmp_path),
        parents=[first["asset_id"], second["asset_id"]],
        role="VARIANT",
        tool="ffmpeg",
        operation="reframe",
    )

    assert child["rights"] == second["rights"]
    assert child["ai_involvement"]["ai_generated"] == "full"


def test_missing_parent_writes_nothing(registry, tmp_path: Path) -> None:
    root, asset_record, _delivery_gate = registry

    with pytest.raises(asset_record.AssetRecordError, match="Parent-Record fehlt"):
        asset_record.register_derived(
            _output(tmp_path),
            parents=["ast_missingparent"],
            role="MASTER",
            tool="ffmpeg",
            operation="cut",
        )

    assert not list(root.rglob("*.asset.json"))
    assert not list(root.glob("master/**"))


def test_ai_involvement_is_inherited_or_marked_partial_for_ai_tool(
    registry, tmp_path: Path
) -> None:
    root, asset_record, _delivery_gate = registry
    parent = _parent(
        root,
        asset_record,
        asset_id="ast_partialparent",
        rights=_approved_rights(),
        ai_generated="partial",
    )

    inherited = asset_record.register_derived(
        _output(tmp_path, "inherited.mp4"),
        parents=[parent["asset_id"]],
        role="MASTER",
        tool="ffmpeg",
        operation="cut",
    )
    generated = asset_record.register_derived(
        _output(tmp_path, "generated.mp4"),
        parents=[parent["asset_id"]],
        role="VARIANT",
        tool="openai-image",
        operation="animate",
    )

    assert inherited["ai_involvement"]["ai_generated"] == "partial"
    assert generated["ai_involvement"]["ai_generated"] == "partial"


def test_master_from_unknown_source_is_allowed_for_internal_work(registry, tmp_path: Path) -> None:
    root, asset_record, _delivery_gate = registry
    parent = _parent(
        root,
        asset_record,
        asset_id="ast_internalunknown",
        rights={
            "rights_status": "UNKNOWN",
            "commercial_use": "unknown",
            "person_consent": "unknown",
            "provider_data_scope": "cloud_not_approved",
        },
    )

    child = asset_record.register_derived(
        _output(tmp_path),
        parents=[parent["asset_id"]],
        role="MASTER",
        tool="ffmpeg",
        operation="trim",
    )

    assert child["role"] == "MASTER"
    assert (root / child["path"]).is_file()


def test_delivery_role_creates_only_a_local_delivery_copy(registry, tmp_path: Path) -> None:
    root, asset_record, delivery_gate = registry
    parent = _parent(root, asset_record, asset_id="ast_deliveryparent", rights=_approved_rights())
    _accept_qc(parent["asset_id"])

    delivery = asset_record.register_derived(
        _output(tmp_path),
        parents=[parent["asset_id"]],
        role="DELIVERY",
        tool="ffmpeg",
        operation="export",
    )

    assert delivery["path"].startswith("delivery/")
    assert delivery["lifecycle"] == "approved"
    assert delivery_gate.check(delivery["asset_id"])["allowed"] is True


def test_delivery_role_rejected_without_an_accepted_qc_verdict(
    registry, tmp_path: Path
) -> None:
    root, asset_record, _delivery_gate = registry
    parent = _parent(root, asset_record, asset_id="ast_noqaverdict", rights=_approved_rights())

    with pytest.raises(asset_record.AssetRecordError, match="QC-Verdikt"):
        asset_record.register_derived(
            _output(tmp_path),
            parents=[parent["asset_id"]],
            role="DELIVERY",
            tool="ffmpeg",
            operation="export",
        )


def test_delivery_role_rejected_when_qc_verdict_is_needs_human(
    registry, tmp_path: Path
) -> None:
    from tools import project_init, qc_pipeline

    root, asset_record, _delivery_gate = registry
    parent = _parent(root, asset_record, asset_id="ast_needshumanxx", rights=_approved_rights())
    project_init.init_project("qc-project-2")
    qc_pipeline.run_qc("qc-project-2", parent["asset_id"])  # no review applied -> needs_human

    with pytest.raises(asset_record.AssetRecordError, match="QC-Verdikt"):
        asset_record.register_derived(
            _output(tmp_path),
            parents=[parent["asset_id"]],
            role="DELIVERY",
            tool="ffmpeg",
            operation="export",
        )
