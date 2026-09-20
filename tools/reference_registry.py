#!/usr/bin/env python3
"""Immutable reference-set (P1) registry: create, re-verify, and bind locks.

A reference set is a content-hashed, immutable list of REFERENCE assets that a
project locks onto (PERSON_LOCK, PRODUCT_LOCK, ...). Changing a member means a
new set with a new hash-derived ID -- never an in-place edit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import refset_hash, validate
from tools.asset_record import ASSET_ROOT, AssetRecordError, load_asset_record, sha256_file

LOCK_TYPES = ("PERSON_LOCK", "PRODUCT_LOCK", "BRAND_LOCK", "STYLE_LOCK", "SCENE_LOCK")
_LOCK_TYPE_TO_REFERENCE_KIND = {
    "PERSON_LOCK": "person",
    "PRODUCT_LOCK": "product",
    "BRAND_LOCK": "brand",
    "STYLE_LOCK": "style",
    "SCENE_LOCK": "scene",
}
REFSET_ROOT = ASSET_ROOT / "references" / "sets"


class ReferenceRegistryError(RuntimeError):
    """A reference set could not be created, re-verified, or bound to a project."""


def _refset_path(reference_set_id: str) -> Path:
    return REFSET_ROOT / f"{reference_set_id}.refset.json"


def _verify_member_asset(asset_id: str, expected_reference_kind: str) -> dict[str, Any]:
    """Re-load a member's asset record and re-verify its identity against disk.

    Rights (documented consent, purpose_binding, edit_approval) are enforced by
    asset-manifest.schema.json at registration time already; re-validating the
    record here re-confirms that guarantee still holds rather than re-deriving it.
    """
    try:
        record, _path = load_asset_record(asset_id)
    except AssetRecordError as error:
        raise ReferenceRegistryError(f"Member-Asset nicht gefunden: {asset_id}") from error
    errors = validate("asset", record)
    if errors:
        raise ReferenceRegistryError(f"Member-Asset verletzt das Schema: {asset_id}: {errors[0]}")
    if record.get("role") != "REFERENCE":
        raise ReferenceRegistryError(f"Member-Asset ist keine REFERENCE-Rolle: {asset_id}")
    if record.get("reference_kind") != expected_reference_kind:
        raise ReferenceRegistryError(
            f"Member-Asset {asset_id} hat reference_kind={record.get('reference_kind')!r}, "
            f"erwartet {expected_reference_kind!r}."
        )
    asset_path = (ASSET_ROOT / str(record["path"])).resolve()
    if not asset_path.is_file():
        raise ReferenceRegistryError(f"Member-Asset-Datei fehlt: {asset_id}")
    if sha256_file(asset_path) != record["sha256"]:
        raise ReferenceRegistryError(f"Member-Asset-Hash stimmt nicht mehr: {asset_id}")
    return record


def create_set(lock_type: str, label: str, members: list[dict[str, str]]) -> dict[str, Any]:
    """Validate every member against disk, hash the set, and write it once."""
    if lock_type not in LOCK_TYPES:
        raise ReferenceRegistryError(f"lock_type muss eine von {LOCK_TYPES} sein.")
    if not members:
        raise ReferenceRegistryError("Mindestens ein Member ist erforderlich.")
    reference_kind = _LOCK_TYPE_TO_REFERENCE_KIND[lock_type]

    verified_members: list[dict[str, str]] = []
    for member in members:
        asset_id = member["asset_id"]
        record = _verify_member_asset(asset_id, reference_kind)
        entry: dict[str, str] = {"asset_id": asset_id, "sha256": str(record["sha256"])}
        if member.get("view"):
            entry["view"] = member["view"]
        verified_members.append(entry)

    digest = refset_hash(verified_members)
    reference_set_id = f"rset_{digest[:20]}"
    refset: dict[str, Any] = {
        "schema_version": "1.0.0",
        "reference_set_id": reference_set_id,
        "lock_type": lock_type,
        "label": label,
        "members": verified_members,
        "set_sha256": digest,
        "created_at": datetime.now(UTC).isoformat(),
    }
    errors = validate("refset", refset)
    if errors:
        raise ReferenceRegistryError(f"Reference-Set verletzt das Schema: {errors[0]}")

    path = _refset_path(reference_set_id)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("set_sha256") == digest:
            return existing
        raise ReferenceRegistryError(
            f"Abweichendes Reference-Set existiert bereits: {reference_set_id}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(refset, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
    return refset


def load_reference_set(reference_set_id: str) -> dict[str, Any]:
    path = _refset_path(reference_set_id)
    try:
        refset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReferenceRegistryError(f"Reference-Set nicht lesbar: {reference_set_id}") from error
    errors = validate("refset", refset)
    if errors:
        raise ReferenceRegistryError(f"Reference-Set verletzt das Schema: {errors[0]}")
    return refset


def verify_set(reference_set_id: str) -> dict[str, Any]:
    """Re-verify every member's hash/rights and that set_sha256 still matches."""
    refset = load_reference_set(reference_set_id)
    reference_kind = _LOCK_TYPE_TO_REFERENCE_KIND[refset["lock_type"]]
    for member in refset["members"]:
        record = _verify_member_asset(member["asset_id"], reference_kind)
        if str(record["sha256"]) != member["sha256"]:
            raise ReferenceRegistryError(
                f"Member {member['asset_id']} hat sich geaendert: Set erwartet "
                f"{member['sha256']}, Asset ist jetzt {record['sha256']}."
            )
    recomputed = refset_hash(refset["members"])
    if recomputed != refset["set_sha256"]:
        raise ReferenceRegistryError(
            f"set_sha256 stimmt nicht mehr: gespeichert {refset['set_sha256']}, "
            f"berechnet {recomputed}."
        )
    return refset


def bind_project(
    project_id: str, reference_set_id: str, lock_key: str, *, on_drift: str = "qc_fail"
) -> dict[str, Any]:
    """Re-verify a set, then record it as an active lock on a project's manifest."""
    from tools.project_init import load_project_manifest, save_project_manifest

    if lock_key not in LOCK_TYPES:
        raise ReferenceRegistryError(f"lock_key muss eine von {LOCK_TYPES} sein.")
    if on_drift not in ("qc_fail", "warn"):
        raise ReferenceRegistryError("on_drift muss 'qc_fail' oder 'warn' sein.")
    refset = verify_set(reference_set_id)
    if refset["lock_type"] != lock_key:
        raise ReferenceRegistryError(
            f"Set {reference_set_id} ist vom Typ {refset['lock_type']}, nicht {lock_key}."
        )

    manifest = load_project_manifest(project_id)
    lock_policy = dict(manifest.get("lock_policy") or {})
    lock_policy[lock_key] = {
        "enabled": True,
        "reference_set_id": reference_set_id,
        "reference_set_sha256": refset["set_sha256"],
        "on_drift": on_drift,
    }
    manifest["lock_policy"] = lock_policy
    reference_set_ids = set(manifest.get("reference_set_ids") or [])
    reference_set_ids.add(reference_set_id)
    manifest["reference_set_ids"] = sorted(reference_set_ids)
    save_project_manifest(project_id, manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create, re-verify, and bind reference locks.")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-set", help="Create a new reference set.")
    create.add_argument("--lock-type", required=True, choices=LOCK_TYPES)
    create.add_argument("--label", required=True)
    create.add_argument(
        "--member", action="append", required=True, dest="members", help="asset_id[:view]"
    )

    verify = commands.add_parser("verify-set", help="Re-verify an existing set's members.")
    verify.add_argument("reference_set_id")

    bind = commands.add_parser("bind-project", help="Bind a verified set as a project lock.")
    bind.add_argument("project_id")
    bind.add_argument("reference_set_id")
    bind.add_argument("lock_key", choices=LOCK_TYPES)
    bind.add_argument("--on-drift", choices=("qc_fail", "warn"), default="qc_fail")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create-set":
            members = []
            for spec in args.members:
                asset_id, _, view = spec.partition(":")
                entry = {"asset_id": asset_id, **({"view": view} if view else {})}
                members.append(entry)
            result = create_set(args.lock_type, args.label, members)
        elif args.command == "verify-set":
            result = verify_set(args.reference_set_id)
        else:
            result = bind_project(
                args.project_id, args.reference_set_id, args.lock_key, on_drift=args.on_drift
            )
    except ReferenceRegistryError as error:
        print(f"Reference-Registry: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
