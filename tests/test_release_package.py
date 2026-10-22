from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import (
    asset_record,
    delivery_gate,
    platform_profiles,
    project_init,
    provenance_report,
    qc_pipeline,
    release_package,
)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(delivery_gate, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _p: {"duration": 1.0, "container": "mp4", "video_codec": "h264"},
    )
    project_init.init_project("demo-project")
    return tmp_path


@pytest.fixture
def verified_ad_1x1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(platform_profiles.PROFILES_PATH.read_text(encoding="utf-8"))
    data["profiles"]["ad_1x1"]["status"] = "VERIFIED"
    data["profiles"]["ad_1x1"]["verified_at"] = "2026-09-21T00:00:00+00:00"
    data["profiles"]["ad_1x1"]["source_url"] = "https://example.invalid/ad-1x1-docs"
    temp_path = tmp_path / "platform-profiles.json"
    temp_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(platform_profiles, "PROFILES_PATH", temp_path)


def _accept(project_id: str, asset_id: str) -> None:
    verdict = qc_pipeline.run_qc(project_id, asset_id)
    qc_pipeline.apply_review(project_id, verdict["verdict_id"], reviewer="qa", overall="accept")


def _full_pipeline(tmp_path: Path) -> dict[str, str]:
    """A complete, release-ready chain: source -> master -> variant, both QC-accepted."""
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source video bytes")
    source_record = asset_record.register_asset(
        source,
        ai_generated="none",
        rights_status="OWNED",
        commercial_use="allowed",
        person_consent="not_needed",
    )
    master = tmp_path / "master.mp4"
    master.write_bytes(b"master video bytes")
    master_record = asset_record.register_derived(
        master, parents=[str(source_record["asset_id"])], role="MASTER",
        tool="ffmpeg", operation="trim",
    )
    variant = tmp_path / "variant.mp4"
    variant.write_bytes(b"variant video bytes")
    variant_record = asset_record.register_derived(
        variant, parents=[str(master_record["asset_id"])], role="VARIANT",
        tool="platform_export", operation="variant_ad_1x1",
    )

    project_init.add_asset_id("demo-project", str(source_record["asset_id"]))
    project_init.add_asset_id("demo-project", str(master_record["asset_id"]))
    project_init.add_asset_id("demo-project", str(variant_record["asset_id"]))
    _accept("demo-project", str(master_record["asset_id"]))
    _accept("demo-project", str(variant_record["asset_id"]))

    provenance_report.set_labeling(
        "demo-project", "assessed_not_required", note="Kein KI-Inhalt", by="hannibal"
    )
    provenance_report.write_report("demo-project")

    metadata_path = project_init.PROJECTS_ROOT / "demo-project" / "specs" / "release-metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "targets": {
                    "ad_1x1": {
                        "title": "Beispiel-Anzeige",
                        "description": "Eine kurze Testbeschreibung.",
                        "hashtags": ["#beispiel"],
                        "alt_text": "Produktbild mit Text",
                        "language": "de",
                        "thumbnail_asset_id": None,
                        "visibility": "private",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return {
        "source_asset_id": str(source_record["asset_id"]),
        "master_asset_id": str(master_record["asset_id"]),
        "variant_asset_id": str(variant_record["asset_id"]),
    }


def test_create_builds_a_package_when_everything_is_ready(
    env: Path, verified_ad_1x1: None
) -> None:
    ids = _full_pipeline(env)

    result = release_package.create("demo-project", {"ad_1x1": ids["variant_asset_id"]})

    package_dir = Path(result["ad_1x1"]["package_dir"])
    assert package_dir.is_dir()
    manifest_path = package_dir / "package-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["variant_asset_id"] == ids["variant_asset_id"]
    assert manifest["master_asset_id"] == ids["master_asset_id"]
    assert manifest["metadata"]["title"] == "Beispiel-Anzeige"
    assert Path(result["ad_1x1"]["variant_path"]).is_file()
    assert release_package.is_approved(package_dir) is False


def test_create_rejects_profile_not_verified(env: Path) -> None:
    ids = _full_pipeline(env)  # ad_1x1 left UNVERIFIED (no verified_ad_1x1 fixture)

    with pytest.raises(release_package.ReleasePackageError, match="VERIFIED"):
        release_package.create("demo-project", {"ad_1x1": ids["variant_asset_id"]})


def test_create_rejects_not_assessed_labeling(env: Path, verified_ad_1x1: None) -> None:
    source = env / "source.mp4"
    source.write_bytes(b"x")
    asset_record.register_asset(source)
    # No set_labeling call -> ai_labeling_status stays "not_assessed"

    with pytest.raises(release_package.ReleasePackageError, match="not_assessed"):
        release_package.create("demo-project", {"ad_1x1": "ast_" + "a" * 12})


def test_create_rejects_missing_provenance_report(env: Path, verified_ad_1x1: None) -> None:
    provenance_report.set_labeling(
        "demo-project", "assessed_not_required", note="x", by="hannibal"
    )
    with pytest.raises(release_package.ReleasePackageError, match="Provenance"):
        release_package.create("demo-project", {"ad_1x1": "ast_" + "a" * 12})


def test_create_rejects_missing_metadata_for_target(env: Path, verified_ad_1x1: None) -> None:
    ids = _full_pipeline(env)
    metadata_path = project_init.PROJECTS_ROOT / "demo-project" / "specs" / "release-metadata.json"
    metadata_path.write_text(json.dumps({"version": "1.0", "targets": {}}), encoding="utf-8")

    with pytest.raises(release_package.ReleasePackageError, match="Metadaten"):
        release_package.create("demo-project", {"ad_1x1": ids["variant_asset_id"]})


def test_create_rejects_variant_without_accepted_verdict(env: Path, verified_ad_1x1: None) -> None:
    source = env / "source.mp4"
    source.write_bytes(b"source bytes 2")
    source_record = asset_record.register_asset(
        source, ai_generated="none", rights_status="OWNED",
        commercial_use="allowed", person_consent="not_needed",
    )
    master = env / "master2.mp4"
    master.write_bytes(b"master bytes 2")
    master_record = asset_record.register_derived(
        master, parents=[str(source_record["asset_id"])], role="MASTER",
        tool="ffmpeg", operation="trim",
    )
    variant = env / "variant2.mp4"
    variant.write_bytes(b"variant bytes 2")
    variant_record = asset_record.register_derived(
        variant, parents=[str(master_record["asset_id"])], role="VARIANT",
        tool="platform_export", operation="variant_ad_1x1",
    )
    project_init.add_asset_id("demo-project", str(variant_record["asset_id"]))
    _accept("demo-project", str(master_record["asset_id"]))
    # Variant itself never gets an accepted verdict.
    provenance_report.set_labeling(
        "demo-project", "assessed_not_required", note="x", by="hannibal"
    )
    provenance_report.write_report("demo-project")
    metadata_path = project_init.PROJECTS_ROOT / "demo-project" / "specs" / "release-metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "targets": {
                    "ad_1x1": {
                        "title": "t", "description": "d", "hashtags": [], "alt_text": "a",
                        "language": "de", "thumbnail_asset_id": None, "visibility": "private",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(release_package.ReleasePackageError, match="QC-Verdikt"):
        release_package.create("demo-project", {"ad_1x1": str(variant_record["asset_id"])})


def test_approve_creates_approval_file(env: Path, verified_ad_1x1: None) -> None:
    ids = _full_pipeline(env)
    result = release_package.create("demo-project", {"ad_1x1": ids["variant_asset_id"]})
    package_dir = Path(result["ad_1x1"]["package_dir"])

    approval = release_package.approve(package_dir, by="hannibal")

    assert approval["approved_by"] == "hannibal"
    assert release_package.is_approved(package_dir) is True


def test_approve_rejects_unknown_package(tmp_path: Path) -> None:
    with pytest.raises(release_package.ReleasePackageError, match="Kein Release-Paket"):
        release_package.approve(tmp_path / "nowhere", by="hannibal")


def test_approve_rejects_empty_by(env: Path, verified_ad_1x1: None) -> None:
    ids = _full_pipeline(env)
    result = release_package.create("demo-project", {"ad_1x1": ids["variant_asset_id"]})

    with pytest.raises(release_package.ReleasePackageError, match="by"):
        release_package.approve(Path(result["ad_1x1"]["package_dir"]), by="  ")
