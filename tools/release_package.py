#!/usr/bin/env python3
"""Release packages: real local copies into release-ready/, gated hard.

create() refuses unless every one of these holds for each target: the
variant's platform profile is VERIFIED, the variant passes the existing
delivery_gate, both the variant and its master have an accepted
(overall=accept) QC verdict, the project's ai_labeling_status is not
"not_assessed", a provenance report exists, and release metadata for that
target is present and schema-valid. A package is only "approved" after an
explicit `release_package.py approve <package_dir> --by <name>` -- no
network code anywhere in this module.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate
from tools import asset_record, delivery_gate, platform_profiles, project_init, qc_pipeline


class ReleasePackageError(RuntimeError):
    """A release package could not be created or approved."""


def release_root() -> Path:
    """The media store's release-ready/ root, resolved from the *current*
    asset_record.ASSET_ROOT (not captured at import time)."""
    return asset_record.ASSET_ROOT.parent / "release-ready"


def _metadata_path(project_id: str) -> Path:
    return project_init.PROJECTS_ROOT / project_id / "specs" / "release-metadata.json"


def load_release_metadata(project_id: str) -> dict[str, Any]:
    path = _metadata_path(project_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleasePackageError(f"release-metadata.json nicht lesbar: {error}") from error
    errors = validate("release_metadata", data)
    if errors:
        raise ReleasePackageError(f"release-metadata.json verletzt das Schema: {errors[0]}")
    return data


def _latest_provenance_report(project_id: str) -> Path | None:
    provenance_dir = project_init.PROJECTS_ROOT / project_id / "provenance"
    if not provenance_dir.is_dir():
        return None
    candidates = sorted(provenance_dir.glob("provenance-*.json"))
    return candidates[-1] if candidates else None


def _package_dir(project_id: str, target: str) -> Path:
    return release_root() / project_id / target


def _build_one_package(
    project_id: str,
    target: str,
    variant_asset_id: str,
    *,
    target_metadata: dict[str, Any],
    provenance_path: Path,
) -> dict[str, Any]:
    profile = platform_profiles.get_profile(target)
    if profile["status"] != "VERIFIED":
        raise ReleasePackageError(f"Profil {target!r} ist nicht VERIFIED.")

    variant_record, _path = asset_record.load_asset_record(variant_asset_id)
    gate = delivery_gate.check(variant_asset_id)
    if not gate["allowed"]:
        raise ReleasePackageError(
            f"Delivery-Gate abgelehnt für {variant_asset_id}: {'; '.join(gate['reasons'])}"
        )

    variant_verdict = qc_pipeline.find_accepted_verdict(variant_asset_id)
    if variant_verdict is None:
        raise ReleasePackageError(f"Kein akzeptiertes QC-Verdikt für Variante {variant_asset_id}.")

    parent_ids = cast("list[str]", variant_record.get("parent_ids") or [])
    if not parent_ids:
        raise ReleasePackageError(f"Variante {variant_asset_id} hat keinen Master-Parent.")
    master_asset_id = str(parent_ids[0])
    master_verdict = qc_pipeline.find_accepted_verdict(master_asset_id)
    if master_verdict is None:
        raise ReleasePackageError(f"Kein akzeptiertes QC-Verdikt für Master {master_asset_id}.")

    package_dir = _package_dir(project_id, target)
    if package_dir.exists():
        raise ReleasePackageError(f"Release-Paket existiert bereits: {package_dir}")

    variant_path = asset_record.ASSET_ROOT / str(variant_record["path"])
    package_dir.mkdir(parents=True)
    dest_path = package_dir / Path(str(variant_record["path"])).name
    try:
        shutil.copy2(variant_path, dest_path)
        package_manifest = {
            "project_id": project_id,
            "target": target,
            "variant_asset_id": variant_asset_id,
            "master_asset_id": master_asset_id,
            "sha256": variant_record["sha256"],
            "metadata": target_metadata,
            "rights": variant_record["rights"],
            "qc": {
                "variant_verdict_id": variant_verdict["verdict_id"],
                "master_verdict_id": master_verdict["verdict_id"],
            },
            "provenance_ref": provenance_path.name,
            "created_at": datetime.now(UTC).isoformat(),
        }
        (package_dir / "package-manifest.json").write_text(
            json.dumps(package_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        raise
    return {"package_dir": str(package_dir), "variant_path": str(dest_path)}


def create(project_id: str, targets: dict[str, str]) -> dict[str, Any]:
    """targets: {platform_profile_name: variant_asset_id}."""
    if not targets:
        raise ReleasePackageError("Mindestens ein Ziel ist erforderlich.")
    manifest = project_init.load_project_manifest(project_id)
    if manifest.get("ai_labeling_status") == "not_assessed":
        raise ReleasePackageError(
            "ai_labeling_status ist not_assessed; provenance_report.py set-labeling zuerst "
            "ausführen."
        )
    provenance_path = _latest_provenance_report(project_id)
    if provenance_path is None:
        raise ReleasePackageError("Kein Provenance-Bericht vorhanden.")
    release_metadata = load_release_metadata(project_id)
    target_entries = release_metadata.get("targets", {})

    results: dict[str, Any] = {}
    for target, variant_asset_id in targets.items():
        target_metadata = target_entries.get(target)
        if target_metadata is None:
            raise ReleasePackageError(f"Keine Release-Metadaten für Ziel {target!r}.")
        results[target] = _build_one_package(
            project_id,
            target,
            variant_asset_id,
            target_metadata=target_metadata,
            provenance_path=provenance_path,
        )
    return results


def approve(package_dir: Path, *, by: str) -> dict[str, Any]:
    """Create the approval file that marks a package as release-approved."""
    if not by.strip():
        raise ReleasePackageError("--by darf nicht leer sein.")
    manifest_path = package_dir / "package-manifest.json"
    if not manifest_path.is_file():
        raise ReleasePackageError(f"Kein Release-Paket an diesem Pfad: {package_dir}")
    approval = {"approved_by": by, "approved_at": datetime.now(UTC).isoformat()}
    (package_dir / "approval.json").write_text(
        json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return approval


def is_approved(package_dir: Path) -> bool:
    return (package_dir / "approval.json").is_file()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and approve local release packages.")
    commands = parser.add_subparsers(dest="command", required=True)

    create_cmd = commands.add_parser("create", help="Build one package per target.")
    create_cmd.add_argument("project_id")
    create_cmd.add_argument(
        "--targets", nargs="+", required=True, help="profile_name:variant_asset_id pairs"
    )

    approve_cmd = commands.add_parser("approve", help="Approve an existing package.")
    approve_cmd.add_argument("package_dir", type=Path)
    approve_cmd.add_argument("--by", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create":
            targets = dict(pair.split(":", 1) for pair in args.targets)
            result: dict[str, Any] = create(args.project_id, targets)
        else:
            result = approve(args.package_dir, by=args.by)
    except (ReleasePackageError, platform_profiles.PlatformProfileError) as error:
        print(f"Release-Package: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
