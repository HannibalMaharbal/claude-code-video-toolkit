"""Immutable, fail-closed source asset records for imported media."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from contracts.validate_contracts import validate
from tools.video_ingest import probe_media, sanitize_filename


class AssetRecordError(RuntimeError):
    """An asset could not be recorded without weakening its invariants."""


ASSET_ROOT = Path(__file__).resolve().parents[2] / "video-toolkit-media" / "assets"


def sha256_file(path: Path) -> str:
    """Return a content hash without loading a media file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_id_for_sha256(digest: str) -> str:
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise AssetRecordError("SHA-256 muss ein 64-stelliger Hexwert sein.")
    return f"ast_{digest[:20]}"


def _media_type(metadata: dict[str, object]) -> str:
    if metadata.get("video_codec") is not None:
        return "video"
    if metadata.get("audio_codec") is not None:
        return "audio"
    return "other"


def _existing_record(asset_id: str, digest: str) -> dict[str, object] | None:
    if not ASSET_ROOT.is_dir():
        return None
    records = list(ASSET_ROOT.glob(f"source/**/{asset_id}.asset.json"))
    if not records:
        return None
    if len(records) != 1:
        raise AssetRecordError(f"Mehrere Asset-Records für {asset_id} gefunden.")
    try:
        record = json.loads(records[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetRecordError(f"Vorhandener Asset-Record {asset_id} ist nicht lesbar.") from error
    if not isinstance(record, dict) or record.get("asset_id") != asset_id:
        raise AssetRecordError(f"Vorhandener Asset-Record {asset_id} ist ungültig.")
    if record.get("sha256") != digest:
        raise AssetRecordError(f"Vorhandener Asset-Record {asset_id} hat einen abweichenden Hash.")
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(
            f"Vorhandener Asset-Record {asset_id} verletzt das Schema: {errors[0]}"
        )
    return record


def load_asset_record(asset_id: str) -> tuple[dict[str, object], Path]:
    """Load exactly one record by ID without modifying it."""
    records = list(ASSET_ROOT.rglob(f"{asset_id}.asset.json")) if ASSET_ROOT.is_dir() else []
    if not records:
        raise AssetRecordError(f"Asset-Record nicht gefunden: {asset_id}")
    if len(records) != 1:
        raise AssetRecordError(f"Mehrere Asset-Records für {asset_id} gefunden.")
    try:
        record = json.loads(records[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetRecordError(f"Asset-Record ist nicht lesbar: {asset_id}") from error
    if not isinstance(record, dict) or record.get("asset_id") != asset_id:
        raise AssetRecordError(f"Asset-Record ist ungültig: {asset_id}")
    return record, records[0]


def _record_path(asset_id: str, source_path: Path) -> Path:
    return source_path.with_name(f"{asset_id}.asset.json")


def _write_new_file(path: Path, content: bytes) -> None:
    """Create a file atomically without replacing an existing destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.link(temporary, path)
    except FileExistsError as error:
        raise AssetRecordError(f"Zieldatei existiert bereits: {path.name}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _replace_file(path: Path, content: bytes) -> None:
    """Atomically replace an existing record only after caller-side validation."""
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_jsonl(path: Path, entry: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def _copy_new_file(source: Path, target: Path) -> None:
    if target.exists():
        raise AssetRecordError(f"Zieldatei existiert bereits: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.link(temporary, target)
    except FileExistsError as error:
        raise AssetRecordError(f"Zieldatei existiert bereits: {target.name}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _make_read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def build_asset_record(
    source: Path,
    *,
    digest: str,
    destination: Path,
    rights_status: str = "UNKNOWN",
    commercial_use: str = "unknown",
    person_consent: str = "unknown",
    license_ref: str | None = None,
) -> dict[str, object]:
    """Build, but do not persist, one SOURCE record for a validated media file."""
    metadata = probe_media(source)
    asset_id = asset_id_for_sha256(digest)
    relative_path = destination.resolve().relative_to(ASSET_ROOT.resolve()).as_posix()
    rights: dict[str, object] = {
        "rights_status": rights_status,
        "commercial_use": commercial_use,
        "person_consent": person_consent,
        "provider_data_scope": "cloud_not_approved",
    }
    if license_ref:
        rights["license_ref"] = license_ref
    technical: dict[str, object] = {
        "duration_s": metadata["duration"],
        "codec": metadata.get("video_codec") or metadata.get("audio_codec"),
        "container": metadata["container"],
    }
    for key in ("width", "height", "fps"):
        if metadata.get(key) is not None:
            technical[key] = metadata[key]
    return {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": "SOURCE",
        "media_type": _media_type(metadata),
        "path": relative_path,
        "sha256": digest,
        "bytes": source.stat().st_size,
        "created_at": datetime.now(UTC).isoformat(),
        "lifecycle": "ingested",
        "rights": rights,
        "ai_involvement": {"ai_generated": "unknown"},
        "technical": technical,
    }


def register_asset(
    source: Path | str,
    *,
    rights_status: str = "UNKNOWN",
    commercial_use: str = "unknown",
    person_consent: str = "unknown",
    license_ref: str | None = None,
) -> dict[str, object]:
    """Copy one imported file into immutable SOURCE storage and record it once."""
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise AssetRecordError("Zu registrierendes Asset fehlt oder ist leer.")
    digest = sha256_file(source)
    asset_id = asset_id_for_sha256(digest)
    existing = _existing_record(asset_id, digest)
    if existing is not None:
        return existing

    month = datetime.now(UTC).strftime("%Y-%m")
    target = ASSET_ROOT / "source" / month / sanitize_filename(source.name)
    if target.exists():
        raise AssetRecordError(
            f"Abweichendes Asset mit gleichem Namen existiert bereits: {target.name}"
        )
    record = build_asset_record(
        source,
        digest=digest,
        destination=target,
        rights_status=rights_status,
        commercial_use=commercial_use,
        person_consent=person_consent,
        license_ref=license_ref,
    )
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(f"Asset-Record verletzt das Schema: {errors[0]}")

    record_path = _record_path(asset_id, target)
    try:
        _copy_new_file(source, target)
        _make_read_only(target)
        record_content = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        _write_new_file(record_path, record_content.encode("utf-8"))
    except OSError as error:
        target.unlink(missing_ok=True)
        raise AssetRecordError(f"Asset konnte nicht gespeichert werden: {error}") from error
    except AssetRecordError:
        target.unlink(missing_ok=True)
        raise
    return record


def set_rights(
    asset_id: str,
    *,
    rights_status: str | None = None,
    commercial_use: str | None = None,
    person_consent: str | None = None,
    provider_data_scope: str | None = None,
    license_ref: str | None = None,
    note: str,
) -> dict[str, object]:
    """Update only a record's rights block and append an immutable audit entry."""
    if not note.strip():
        raise AssetRecordError("--note darf nicht leer sein.")
    record, record_path = load_asset_record(asset_id)
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(f"Bestehender Asset-Record verletzt das Schema: {errors[0]}")

    current_rights = record.get("rights")
    if not isinstance(current_rights, dict):
        raise AssetRecordError("Bestehender Asset-Record enthält keinen Rechteblock.")
    old_rights: dict[str, object] = copy.deepcopy(current_rights)
    new_rights = copy.deepcopy(old_rights)
    changes = {
        "rights_status": rights_status,
        "commercial_use": commercial_use,
        "person_consent": person_consent,
        "provider_data_scope": provider_data_scope,
        "license_ref": license_ref,
    }
    supplied = {key: value for key, value in changes.items() if value is not None}
    if not supplied:
        raise AssetRecordError("Mindestens ein Rechtefeld muss gesetzt werden.")
    new_rights.update(supplied)
    record["rights"] = new_rights
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(f"Rechteänderung verletzt das Schema: {errors[0]}")

    content = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    audit_entry: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "asset_id": asset_id,
        "old": old_rights,
        "new": new_rights,
        "note": note,
    }
    _replace_file(record_path, content.encode("utf-8"))
    _append_jsonl(record_path.with_name(f"{asset_id}.rights.log.jsonl"), audit_entry)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or update immutable asset records.")
    commands = parser.add_subparsers(dest="command", required=True)
    set_rights_parser = commands.add_parser("set-rights", help="Set audited rights fields.")
    set_rights_parser.add_argument("asset_id")
    set_rights_parser.add_argument(
        "--rights-status",
        choices=("OWNED", "LICENSED", "USER_PROVIDED", "PUBLIC_DOMAIN", "UNKNOWN", "RESTRICTED"),
    )
    set_rights_parser.add_argument(
        "--commercial-use", choices=("allowed", "restricted", "unknown")
    )
    set_rights_parser.add_argument(
        "--person-consent", choices=("not_needed", "documented", "missing", "unknown")
    )
    set_rights_parser.add_argument(
        "--provider-data-scope", choices=("local", "cloud_approved", "cloud_not_approved")
    )
    set_rights_parser.add_argument("--license-ref")
    set_rights_parser.add_argument("--note", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        record = set_rights(
            args.asset_id,
            rights_status=args.rights_status,
            commercial_use=args.commercial_use,
            person_consent=args.person_consent,
            provider_data_scope=args.provider_data_scope,
            license_ref=args.license_ref,
            note=args.note,
        )
    except AssetRecordError as error:
        print(f"Asset-Rechte: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
