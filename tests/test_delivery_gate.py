import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from tools import asset_record, delivery_gate

    root = tmp_path / "assets"
    monkeypatch.setattr(asset_record, "ASSET_ROOT", root)
    monkeypatch.setattr(delivery_gate, "ASSET_ROOT", root)
    return root, asset_record, delivery_gate


def _write_asset(
    root: Path,
    asset_record,
    *,
    asset_id: str,
    name: str,
    content: bytes = b"media",
    rights: dict[str, object] | None = None,
    parent_ids: list[str] | None = None,
    ai_generated: str = "none",
) -> tuple[dict[str, object], Path]:
    media = root / "source" / name
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(content)
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": "SOURCE",
        "media_type": "video",
        "path": media.relative_to(root).as_posix(),
        "sha256": asset_record.sha256_file(media),
        "bytes": len(content),
        "created_at": datetime.now(UTC).isoformat(),
        "lifecycle": "ingested",
        "rights": rights or {
            "rights_status": "OWNED",
            "commercial_use": "allowed",
            "person_consent": "not_needed",
            "provider_data_scope": "local",
        },
        "ai_involvement": {"ai_generated": ai_generated},
    }
    if parent_ids is not None:
        record["parent_ids"] = parent_ids
    manifest = media.with_name(f"{asset_id}.asset.json")
    manifest.write_text(json.dumps(record), encoding="utf-8")
    return record, media


def test_unknown_rights_are_rejected(registry) -> None:
    root, asset_record, delivery_gate = registry
    record, _ = _write_asset(
        root,
        asset_record,
        asset_id="ast_unknown12345",
        name="unknown.mp4",
        rights={
            "rights_status": "UNKNOWN",
            "commercial_use": "unknown",
            "person_consent": "unknown",
            "provider_data_scope": "cloud_not_approved",
        },
    )

    result = delivery_gate.check(record["asset_id"])

    assert result["allowed"] is False
    assert any("rights_status" in reason for reason in result["reasons"])


def test_missing_record_is_rejected(registry) -> None:
    _root, _asset_record, delivery_gate = registry

    result = delivery_gate.check("ast_missing1234")

    assert result == {"allowed": False, "reasons": ["Asset-Record nicht gefunden."]}


def test_modified_file_hash_is_rejected(registry) -> None:
    root, asset_record, delivery_gate = registry
    record, media = _write_asset(root, asset_record, asset_id="ast_hashmismatch1", name="clip.mp4")
    media.write_bytes(b"manipulated")

    result = delivery_gate.check(record["asset_id"])

    assert result["allowed"] is False
    assert any("SHA-256" in reason for reason in result["reasons"])


def test_set_rights_writes_an_audit_line(registry) -> None:
    root, asset_record, _delivery_gate = registry
    record, media = _write_asset(
        root,
        asset_record,
        asset_id="ast_rightsaudit1",
        name="clip.mp4",
        rights={
            "rights_status": "UNKNOWN",
            "commercial_use": "unknown",
            "person_consent": "unknown",
            "provider_data_scope": "cloud_not_approved",
        },
    )
    before_hash = asset_record.sha256_file(media)

    updated = asset_record.set_rights(
        record["asset_id"],
        rights_status="LICENSED",
        commercial_use="allowed",
        person_consent="documented",
        provider_data_scope="local",
        license_ref="license-42",
        note="License checked",
    )

    assert updated["rights"]["rights_status"] == "LICENSED"
    assert asset_record.sha256_file(media) == before_hash
    audit = root / "source" / "ast_rightsaudit1.rights.log.jsonl"
    entry = json.loads(audit.read_text(encoding="utf-8").strip())
    assert entry["note"] == "License checked"
    assert entry["old"]["rights_status"] == "UNKNOWN"
    assert entry["new"]["rights_status"] == "LICENSED"


def test_invalid_rights_change_writes_nothing(registry) -> None:
    root, asset_record, _delivery_gate = registry
    record, media = _write_asset(root, asset_record, asset_id="ast_invalidrights", name="clip.mp4")
    manifest = media.with_name(f"{record['asset_id']}.asset.json")
    before = manifest.read_bytes()

    with pytest.raises(asset_record.AssetRecordError, match="Schema"):
        asset_record.set_rights(record["asset_id"], rights_status="friendly", note="bad value")

    assert manifest.read_bytes() == before
    assert not list(root.rglob("*.rights.log.jsonl"))


def test_set_rights_cli_requires_a_note_and_updates_record(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, asset_record, _delivery_gate = registry
    record, _ = _write_asset(root, asset_record, asset_id="ast_clirights123", name="clip.mp4")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asset_record.py",
            "set-rights",
            record["asset_id"],
            "--rights-status",
            "LICENSED",
            "--note",
            "License reviewed",
        ],
    )

    assert asset_record.main() == 0
    assert list(root.rglob("*.rights.log.jsonl"))


def test_unknown_parent_blocks_child(registry) -> None:
    root, asset_record, delivery_gate = registry
    parent, _ = _write_asset(
        root,
        asset_record,
        asset_id="ast_parentunknown",
        name="parent.mp4",
        rights={
            "rights_status": "UNKNOWN",
            "commercial_use": "unknown",
            "person_consent": "unknown",
            "provider_data_scope": "cloud_not_approved",
        },
    )
    child, _ = _write_asset(
        root,
        asset_record,
        asset_id="ast_childallowed1",
        name="child.mp4",
        parent_ids=[parent["asset_id"]],
    )

    result = delivery_gate.check(child["asset_id"])

    assert result["allowed"] is False
    assert any(parent["asset_id"] in reason for reason in result["reasons"])


def test_approved_asset_is_allowed(registry) -> None:
    root, asset_record, delivery_gate = registry
    record, _ = _write_asset(root, asset_record, asset_id="ast_approvedasset", name="approved.mp4")

    result = delivery_gate.check(record["asset_id"])

    assert result == {"allowed": True, "reasons": []}
    entry = json.loads((root / delivery_gate.DECISION_LOG_NAME).read_text(encoding="utf-8"))
    assert entry["asset"] == record["asset_id"]
    assert entry["allowed"] is True
