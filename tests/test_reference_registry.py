from __future__ import annotations

import stat
from pathlib import Path

import pytest
from PIL import Image

from tools import asset_record, reference_registry


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    asset_root = tmp_path / "assets"
    monkeypatch.setattr(asset_record, "ASSET_ROOT", asset_root)
    monkeypatch.setattr(reference_registry, "ASSET_ROOT", asset_root)
    monkeypatch.setattr(reference_registry, "REFSET_ROOT", asset_root / "references" / "sets")
    return reference_registry


def _register_person_reference(
    tmp_path: Path,
    name: str,
    color: tuple[int, int, int],
    *,
    person_consent: str = "documented",
    purpose_binding: list[str] | None = None,
    edit_approval: bool | None = True,
) -> dict[str, object]:
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (10, 10), color).save(path)
    return asset_record.register_asset(
        path,
        role="REFERENCE",
        reference_kind="person",
        person_consent=person_consent,
        purpose_binding=purpose_binding if purpose_binding is not None else ["proj-demo-001"],
        edit_approval=edit_approval,
    )


def _person_members(tmp_path: Path) -> list[dict[str, str]]:
    front = _register_person_reference(tmp_path, "front", (10, 20, 30))
    profile = _register_person_reference(tmp_path, "profile", (40, 50, 60))
    three_quarter = _register_person_reference(tmp_path, "three_quarter", (70, 80, 90))
    return [
        {"asset_id": str(front["asset_id"]), "view": "front"},
        {"asset_id": str(profile["asset_id"]), "view": "profile"},
        {"asset_id": str(three_quarter["asset_id"]), "view": "three_quarter"},
    ]


def test_create_set_with_full_person_views_validates(registry, tmp_path: Path) -> None:
    from contracts.validate_contracts import validate

    members = _person_members(tmp_path)

    refset = registry.create_set("PERSON_LOCK", "Anna v1", members)

    assert refset["reference_set_id"].startswith("rset_")
    assert len(refset["members"]) == 3
    assert validate("refset", refset) == []


def test_create_set_person_lock_rejects_missing_views(registry, tmp_path: Path) -> None:
    # Three members (satisfies the schema's minItems:3) but no "three_quarter" view.
    front = _register_person_reference(tmp_path, "front", (10, 20, 30))
    profile = _register_person_reference(tmp_path, "profile", (40, 50, 60))
    extra = _register_person_reference(tmp_path, "extra", (11, 22, 33))
    members = [
        {"asset_id": str(front["asset_id"]), "view": "front"},
        {"asset_id": str(profile["asset_id"]), "view": "profile"},
        {"asset_id": str(extra["asset_id"]), "view": "expression"},
    ]

    with pytest.raises(registry.ReferenceRegistryError, match="Schema"):
        registry.create_set("PERSON_LOCK", "Anna incomplete", members)


def test_create_set_rejects_non_reference_role_member(registry, tmp_path: Path) -> None:
    image_path = tmp_path / "plain.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(image_path)
    plain_source = asset_record.register_asset(image_path)  # role=SOURCE, not REFERENCE

    with pytest.raises(registry.ReferenceRegistryError, match="REFERENCE-Rolle"):
        registry.create_set(
            "PERSON_LOCK", "bad", [{"asset_id": str(plain_source["asset_id"]), "view": "front"}]
        )


def test_create_set_rejects_reference_kind_mismatch(registry, tmp_path: Path) -> None:
    person = _register_person_reference(tmp_path, "front", (10, 20, 30))

    with pytest.raises(registry.ReferenceRegistryError, match="reference_kind"):
        registry.create_set(
            "BRAND_LOCK", "wrong-kind", [{"asset_id": str(person["asset_id"])}]
        )


def test_create_set_rejects_product_member_without_edit_approval(
    registry, tmp_path: Path
) -> None:
    image_path = tmp_path / "product.png"
    Image.new("RGB", (10, 10), (5, 6, 7)).save(image_path)

    with pytest.raises(asset_record.AssetRecordError, match="Schema"):
        asset_record.register_asset(
            image_path,
            role="REFERENCE",
            reference_kind="product",
            purpose_binding=["proj-demo-001"],
            edit_approval=None,
        )


def test_create_set_is_idempotent_for_identical_content(registry, tmp_path: Path) -> None:
    members = _person_members(tmp_path)

    first = registry.create_set("PERSON_LOCK", "Anna v1", members)
    second = registry.create_set("PERSON_LOCK", "Anna v1", members)

    assert first == second


def test_different_member_content_produces_a_different_set_hash(
    registry, tmp_path: Path
) -> None:
    members_a = _person_members(tmp_path)
    refset_a = registry.create_set("PERSON_LOCK", "Anna v1", members_a)

    # Re-register a changed "front" photo -> different content -> different asset_id/sha256.
    changed_front = _register_person_reference(tmp_path, "front-v2", (99, 98, 97))
    members_b = [
        {"asset_id": str(changed_front["asset_id"]), "view": "front"},
        members_a[1],
        members_a[2],
    ]
    refset_b = registry.create_set("PERSON_LOCK", "Anna v2", members_b)

    assert refset_a["set_sha256"] != refset_b["set_sha256"]
    assert refset_a["reference_set_id"] != refset_b["reference_set_id"]


def test_verify_set_passes_right_after_creation(registry, tmp_path: Path) -> None:
    members = _person_members(tmp_path)
    refset = registry.create_set("PERSON_LOCK", "Anna v1", members)

    assert registry.verify_set(refset["reference_set_id"]) == refset


def test_verify_set_detects_a_tampered_member_file(registry, tmp_path: Path) -> None:
    members = _person_members(tmp_path)
    refset = registry.create_set("PERSON_LOCK", "Anna v1", members)

    front_asset_id = members[0]["asset_id"]
    record, _ = asset_record.load_asset_record(front_asset_id)
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    asset_path.chmod(asset_path.stat().st_mode | stat.S_IWUSR)
    asset_path.write_bytes(b"tampered bytes, different content")

    with pytest.raises(registry.ReferenceRegistryError, match="Hash"):
        registry.verify_set(refset["reference_set_id"])


def test_bind_project_records_lock_on_manifest(registry, tmp_path: Path, monkeypatch) -> None:
    from tools import project_init

    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    members = _person_members(tmp_path)
    refset = registry.create_set("PERSON_LOCK", "Anna v1", members)

    manifest = registry.bind_project("demo-project", refset["reference_set_id"], "PERSON_LOCK")

    assert manifest["lock_policy"]["PERSON_LOCK"]["enabled"] is True
    assert manifest["lock_policy"]["PERSON_LOCK"]["reference_set_id"] == refset["reference_set_id"]
    assert manifest["lock_policy"]["PERSON_LOCK"]["reference_set_sha256"] == refset["set_sha256"]
    assert refset["reference_set_id"] in manifest["reference_set_ids"]

    from contracts.validate_contracts import validate

    assert validate("project", manifest) == []


def test_bind_project_rejects_lock_type_mismatch(registry, tmp_path: Path, monkeypatch) -> None:
    from tools import project_init

    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    members = _person_members(tmp_path)
    refset = registry.create_set("PERSON_LOCK", "Anna v1", members)

    with pytest.raises(registry.ReferenceRegistryError, match="Typ"):
        registry.bind_project("demo-project", refset["reference_set_id"], "BRAND_LOCK")
