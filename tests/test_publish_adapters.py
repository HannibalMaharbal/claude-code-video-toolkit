from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tools import asset_record
from tools.egress_guard import EgressBlocked
from tools.publish_adapters import (
    ADAPTERS,
    EcommerceAdapter,
    FacebookAdapter,
    InstagramAdapter,
    PublishAdapterError,
    TiktokAdapter,
    YoutubeAdapter,
)

ADAPTER_DIR = Path("tools/publish_adapters")
FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "urllib",
    "urllib2",
    "socket",
    "smtplib",
    "ftplib",
    "googleapiclient",
    "google_auth_oauthlib",
    "google",
    "httplib2",
}


def _make_package(
    tmp_path: Path,
    *,
    title: str = "Titel",
    description: str = "Beschreibung",
    alt_text: str = "Alt-Text",
    hashtags: list[str] | None = None,
    approved: bool = True,
    correct_hash: bool = True,
) -> Path:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    media = package_dir / "variant.mp4"
    media.write_bytes(b"fake variant bytes")
    sha256 = asset_record.sha256_file(media) if correct_hash else "0" * 64
    manifest = {
        "project_id": "demo-project",
        "target": "youtube_long",
        "variant_asset_id": "ast_" + "a" * 12,
        "master_asset_id": "ast_" + "b" * 12,
        "sha256": sha256,
        "metadata": {
            "title": title,
            "description": description,
            "hashtags": hashtags or [],
            "alt_text": alt_text,
            "language": "de",
            "thumbnail_asset_id": None,
            "visibility": "private",
        },
        "rights": {
            "rights_status": "OWNED",
            "commercial_use": "allowed",
            "person_consent": "not_needed",
            "provider_data_scope": "local",
        },
        "qc": {"variant_verdict_id": "qcv_x", "master_verdict_id": "qcv_y"},
        "provenance_ref": "provenance-x.json",
        "created_at": "2026-09-21T00:00:00+00:00",
    }
    (package_dir / "package-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if approved:
        (package_dir / "approval.json").write_text(
            json.dumps({"approved_by": "x", "approved_at": "y"}), encoding="utf-8"
        )
    return package_dir


# --- registry -------------------------------------------------------------------------


def test_adapters_registry_maps_all_five_platforms() -> None:
    assert set(ADAPTERS) == {"youtube", "instagram", "facebook", "tiktok", "ecommerce"}
    assert ADAPTERS["youtube"] is YoutubeAdapter
    assert ADAPTERS["instagram"] is InstagramAdapter
    assert ADAPTERS["facebook"] is FacebookAdapter
    assert ADAPTERS["tiktok"] is TiktokAdapter
    assert ADAPTERS["ecommerce"] is EcommerceAdapter


# --- base validation shared by every adapter ------------------------------------------


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_validate_passes_for_a_well_formed_approved_package(tmp_path: Path, adapter_cls) -> None:
    package_dir = _make_package(tmp_path)
    assert adapter_cls(package_dir).validate() == []


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_validate_flags_unapproved_package(tmp_path: Path, adapter_cls) -> None:
    package_dir = _make_package(tmp_path, approved=False)
    findings = adapter_cls(package_dir).validate()
    assert any("freigegeben" in finding for finding in findings)


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_validate_flags_missing_alt_text(tmp_path: Path, adapter_cls) -> None:
    package_dir = _make_package(tmp_path, alt_text="")
    findings = adapter_cls(package_dir).validate()
    assert any("alt_text" in finding for finding in findings)


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_validate_flags_hash_mismatch(tmp_path: Path, adapter_cls) -> None:
    package_dir = _make_package(tmp_path, correct_hash=False)
    findings = adapter_cls(package_dir).validate()
    assert any("SHA-256" in finding for finding in findings)


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_constructor_rejects_missing_package(tmp_path: Path, adapter_cls) -> None:
    with pytest.raises(PublishAdapterError, match="Kein Release-Paket"):
        adapter_cls(tmp_path / "nowhere")


# --- platform-specific overflow checks ------------------------------------------------


def test_youtube_flags_title_over_limit(tmp_path: Path) -> None:
    package_dir = _make_package(tmp_path, title="x" * 200)
    findings = YoutubeAdapter(package_dir).validate()
    assert any("Titel" in finding for finding in findings)


def test_instagram_flags_too_many_hashtags(tmp_path: Path) -> None:
    package_dir = _make_package(tmp_path, hashtags=[f"#tag{i}" for i in range(40)])
    findings = InstagramAdapter(package_dir).validate()
    assert any("Hashtags" in finding for finding in findings)


def test_tiktok_flags_caption_over_limit(tmp_path: Path) -> None:
    package_dir = _make_package(tmp_path, description="x" * 3000)
    findings = TiktokAdapter(package_dir).validate()
    assert any("Caption" in finding for finding in findings)


def test_ecommerce_flags_title_over_limit(tmp_path: Path) -> None:
    package_dir = _make_package(tmp_path, title="x" * 200)
    findings = EcommerceAdapter(package_dir).validate()
    assert any("Titel" in finding for finding in findings)


def test_facebook_accepts_a_long_but_within_limit_description(tmp_path: Path) -> None:
    package_dir = _make_package(tmp_path, description="x" * 10000)
    assert FacebookAdapter(package_dir).validate() == []


# --- send() is always blocked ----------------------------------------------------------


@pytest.mark.parametrize("adapter_cls", list(ADAPTERS.values()))
def test_send_is_always_blocked_by_the_egress_guard(tmp_path: Path, adapter_cls) -> None:
    package_dir = _make_package(tmp_path)
    with pytest.raises(EgressBlocked, match="internal_only"):
        adapter_cls(package_dir).send()


# --- static: no adapter module imports a network library -------------------------------


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_adapter_module_imports_a_network_library() -> None:
    for path in sorted(ADAPTER_DIR.glob("*.py")):
        roots = _imported_roots(path)
        forbidden = roots & FORBIDDEN_IMPORT_ROOTS
        assert not forbidden, f"{path} imports network-capable module(s): {forbidden}"
