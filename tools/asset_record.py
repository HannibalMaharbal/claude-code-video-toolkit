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

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate  # noqa: E402
from tools.video_ingest import probe_media, sanitize_filename  # noqa: E402


class AssetRecordError(RuntimeError):
    """An asset could not be recorded without weakening its invariants."""


ASSET_ROOT = Path(__file__).resolve().parents[2] / "video-toolkit-media" / "assets"
DERIVED_ROLES = ("MASTER", "VARIANT", "DELIVERY")
_RIGHTS_STATUS_RANK = {
    "OWNED": 1,
    "PUBLIC_DOMAIN": 1,
    "LICENSED": 2,
    "USER_PROVIDED": 2,
    "UNKNOWN": 3,
    "RESTRICTED": 4,
}
_CONSENT_RANK = {"not_needed": 1, "documented": 2, "unknown": 3, "missing": 4}
_PROVIDER_SCOPE_RANK = {"cloud_approved": 1, "local": 2, "cloud_not_approved": 3}
_AI_TOOL_MARKERS = (
    "ai",
    "ollama",
    "openai",
    "chatgpt",
    "claude",
    "gemini",
    "grok",
    "higgsfield",
    "runway",
    "veo",
    "seedance",
    "heygen",
    "kokoro",
    "whisper",
    "mlx",
)


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


def _text_asset_type(path: Path) -> str | None:
    if path.suffix.lower() in {".srt", ".vtt"}:
        return "subtitle"
    if path.suffix.lower() in {".json", ".txt", ".pdf"}:
        return "document"
    return None


def _image_metadata(path: Path) -> dict[str, object]:
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
    return {"width": width, "height": height}


def _metadata_for_asset(path: Path) -> tuple[str, dict[str, object], dict[str, object]]:
    text_type = _text_asset_type(path)
    if text_type == "subtitle":
        from tools.transcribe import validate_subtitle_file

        errors = validate_subtitle_file(path)
        if errors:
            raise AssetRecordError("Subtitle-QC fehlgeschlagen: " + "; ".join(errors))
        return text_type, {}, {}
    if text_type == "document":
        return text_type, {}, {}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return "image", {}, _image_metadata(path)
    metadata = probe_media(path)
    technical: dict[str, object] = {
        "duration_s": metadata["duration"],
        "codec": metadata.get("video_codec") or metadata.get("audio_codec"),
        "container": metadata["container"],
    }
    for key in ("width", "height", "fps"):
        if metadata.get(key) is not None:
            technical[key] = metadata[key]
    return _media_type(metadata), metadata, technical


def _existing_record(asset_id: str, digest: str) -> dict[str, object] | None:
    if not ASSET_ROOT.is_dir():
        return None
    records = list(ASSET_ROOT.rglob(f"{asset_id}.asset.json"))
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


def _read_record_for_reuse(record_path: Path, asset_id: str) -> dict[str, object]:
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AssetRecordError(f"Vorhandener Asset-Record {asset_id} ist nicht lesbar.") from error
    if not isinstance(record, dict) or record.get("asset_id") != asset_id:
        raise AssetRecordError(f"Vorhandener Asset-Record {asset_id} ist ungültig.")
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(
            f"Vorhandener Asset-Record {asset_id} verletzt das Schema: {errors[0]}"
        )
    return record


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


SOURCE_ROLES = ("SOURCE", "EDITABLE_SOURCE")


def build_asset_record(
    source: Path,
    *,
    digest: str,
    destination: Path,
    role: str = "SOURCE",
    rights_status: str = "UNKNOWN",
    commercial_use: str = "unknown",
    person_consent: str = "unknown",
    license_ref: str | None = None,
) -> dict[str, object]:
    """Build, but do not persist, one SOURCE/EDITABLE_SOURCE record for a validated file."""
    media_type, metadata, technical = _metadata_for_asset(source)
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
    return {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": role,
        "media_type": media_type,
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
    role: str = "SOURCE",
    rights_status: str = "UNKNOWN",
    commercial_use: str = "unknown",
    person_consent: str = "unknown",
    license_ref: str | None = None,
) -> dict[str, object]:
    """Copy one imported file into immutable SOURCE/EDITABLE_SOURCE storage and record it once."""
    if role not in SOURCE_ROLES:
        raise AssetRecordError(f"--role muss eine von {SOURCE_ROLES} sein.")
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise AssetRecordError("Zu registrierendes Asset fehlt oder ist leer.")
    digest = sha256_file(source)
    asset_id = asset_id_for_sha256(digest)
    existing = _existing_record(asset_id, digest)
    if existing is not None:
        return existing

    month = datetime.now(UTC).strftime("%Y-%m")
    target = ASSET_ROOT / role.lower() / month / sanitize_filename(source.name)
    if target.exists():
        raise AssetRecordError(
            f"Abweichendes Asset mit gleichem Namen existiert bereits: {target.name}"
        )
    record = build_asset_record(
        source,
        digest=digest,
        destination=target,
        role=role,
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


def _parent_asset_path(record: dict[str, object]) -> Path:
    relative_path = record.get("path")
    if not isinstance(relative_path, str):
        raise AssetRecordError("Parent-Record enthält keinen gültigen Asset-Pfad.")
    asset_path = (ASSET_ROOT / relative_path).resolve()
    try:
        asset_path.relative_to(ASSET_ROOT.resolve())
    except ValueError as error:
        raise AssetRecordError("Parent-Record verweist außerhalb des Asset-Roots.") from error
    return asset_path


def _validated_parent(asset_id: str) -> dict[str, object]:
    try:
        record, _record_path = load_asset_record(asset_id)
    except AssetRecordError as error:
        raise AssetRecordError(f"Parent-Record fehlt oder ist ungültig: {asset_id}") from error
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(f"Parent-Record verletzt das Schema: {asset_id}: {errors[0]}")
    asset_path = _parent_asset_path(record)
    if not asset_path.is_file():
        raise AssetRecordError(f"Parent-Asset fehlt: {asset_id}")
    if sha256_file(asset_path) != record["sha256"]:
        raise AssetRecordError(f"Parent-Asset hat einen abweichenden Hash: {asset_id}")
    return record


def _most_restrictive(values: list[str], ranks: dict[str, int]) -> str:
    return max(values, key=lambda value: ranks[value])


def _inherited_rights(parents: list[dict[str, object]]) -> dict[str, object]:
    rights_blocks = [parent["rights"] for parent in parents]
    if not all(isinstance(rights, dict) for rights in rights_blocks):
        raise AssetRecordError("Parent-Record enthält keinen gültigen Rechteblock.")
    rights = [rights for rights in rights_blocks if isinstance(rights, dict)]
    statuses = [rights_block["rights_status"] for rights_block in rights]
    commercial_uses = [rights_block["commercial_use"] for rights_block in rights]
    consents = [rights_block["person_consent"] for rights_block in rights]
    provider_scopes = [rights_block["provider_data_scope"] for rights_block in rights]
    if not all(
        isinstance(value, str)
        for values in (statuses, commercial_uses, consents, provider_scopes)
        for value in values
    ):
        raise AssetRecordError("Parent-Rechte enthalten ungültige Werte.")
    if not all(value in _RIGHTS_STATUS_RANK for value in statuses):
        raise AssetRecordError("Parent-Rechte enthalten einen unbekannten rights_status.")
    if not all(value in _CONSENT_RANK for value in consents):
        raise AssetRecordError("Parent-Rechte enthalten einen unbekannten person_consent-Wert.")
    if not all(value in _PROVIDER_SCOPE_RANK for value in provider_scopes):
        raise AssetRecordError(
            "Parent-Rechte enthalten einen unbekannten provider_data_scope-Wert."
        )
    if not all(value in {"allowed", "restricted", "unknown"} for value in commercial_uses):
        raise AssetRecordError("Parent-Rechte enthalten einen unbekannten commercial_use-Wert.")
    commercial_use = (
        "allowed"
        if all(value == "allowed" for value in commercial_uses)
        else "unknown"
        if "unknown" in commercial_uses
        else "restricted"
    )
    return {
        "rights_status": _most_restrictive(statuses, _RIGHTS_STATUS_RANK),
        "commercial_use": commercial_use,
        "person_consent": _most_restrictive(consents, _CONSENT_RANK),
        "provider_data_scope": _most_restrictive(provider_scopes, _PROVIDER_SCOPE_RANK),
    }


def _inherited_ai_involvement(parents: list[dict[str, object]], tool: str) -> dict[str, str]:
    values: list[str] = []
    for parent in parents:
        involvement = parent.get("ai_involvement")
        if not isinstance(involvement, dict) or not isinstance(
            involvement.get("ai_generated"), str
        ):
            values.append("unknown")
        else:
            values.append(involvement["ai_generated"])
    normalized_tool = tool.casefold()
    tool_uses_ai = any(marker in normalized_tool for marker in _AI_TOOL_MARKERS)
    if "full" in values:
        value = "full"
    elif "unknown" in values:
        value = "unknown"
    elif tool_uses_ai or "partial" in values:
        value = "partial"
    else:
        value = "none"
    return {"ai_generated": value}


def register_derived(
    output_path: Path | str,
    *,
    parents: list[str],
    role: str,
    tool: str,
    operation: str,
    tool_version: str | None = None,
    job_id: str | None = None,
) -> dict[str, object]:
    """Register a local, immutable derivative after validating all parent assets."""
    output = Path(output_path).expanduser().resolve()
    if role not in DERIVED_ROLES:
        raise AssetRecordError(f"Abgeleitete Rolle muss eine von {DERIVED_ROLES} sein.")
    if not output.is_file() or output.stat().st_size <= 0:
        raise AssetRecordError("Abgeleitetes Output-Asset fehlt oder ist leer.")
    if not parents:
        raise AssetRecordError("Mindestens ein Parent-Asset ist erforderlich.")
    if len(set(parents)) != len(parents):
        raise AssetRecordError("Parent-IDs dürfen nicht doppelt vorkommen.")
    if not tool.strip() or not operation.strip():
        raise AssetRecordError("--tool und --operation dürfen nicht leer sein.")

    parent_records = [_validated_parent(parent_id) for parent_id in parents]
    digest = sha256_file(output)
    asset_id = asset_id_for_sha256(digest)
    existing_paths = list(ASSET_ROOT.rglob(f"{asset_id}.asset.json")) if ASSET_ROOT.is_dir() else []
    if existing_paths:
        if len(existing_paths) != 1:
            raise AssetRecordError(f"Mehrere Asset-Records für {asset_id} gefunden.")
        existing = _read_record_for_reuse(existing_paths[0], asset_id)
        if (
            existing.get("sha256") == digest
            and existing.get("parent_ids") == parents
            and existing.get("role") == role
        ):
            return existing
        raise AssetRecordError(
            f"Asset-Inhalt existiert bereits mit abweichender Herkunft: {asset_id}"
        )

    month = datetime.now(UTC).strftime("%Y-%m")
    target = ASSET_ROOT / role.lower() / month / sanitize_filename(output.name)
    if target.exists():
        raise AssetRecordError(
            f"Abweichendes Asset mit gleichem Namen existiert bereits: {target.name}"
        )
    media_type, _metadata, technical = _metadata_for_asset(output)
    derivation: dict[str, object] = {"tool": tool, "operation": operation}
    if tool_version:
        derivation["tool_version"] = tool_version
    if job_id:
        derivation["job_id"] = job_id
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "role": role,
        "media_type": media_type,
        "path": target.relative_to(ASSET_ROOT).as_posix(),
        "sha256": digest,
        "bytes": output.stat().st_size,
        "created_at": datetime.now(UTC).isoformat(),
        "lifecycle": "approved" if role == "DELIVERY" else "analysed",
        "parent_ids": parents,
        "derivation": derivation,
        "rights": _inherited_rights(parent_records),
        "ai_involvement": _inherited_ai_involvement(parent_records, tool),
        "technical": technical,
    }
    errors = validate("asset", record)
    if errors:
        raise AssetRecordError(f"Abgeleiteter Asset-Record verletzt das Schema: {errors[0]}")

    record_path = _record_path(asset_id, target)
    try:
        _copy_new_file(output, target)
        _make_read_only(target)
        content = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        _write_new_file(record_path, content.encode("utf-8"))
    except OSError as error:
        target.unlink(missing_ok=True)
        raise AssetRecordError(
            f"Abgeleitetes Asset konnte nicht gespeichert werden: {error}"
        ) from error
    except AssetRecordError:
        target.unlink(missing_ok=True)
        raise
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
    derived_parser = commands.add_parser(
        "register-derived", help="Register a local derived asset with parent provenance."
    )
    derived_parser.add_argument("output_path")
    derived_parser.add_argument("--parents", nargs="+", required=True)
    derived_parser.add_argument("--role", choices=DERIVED_ROLES, required=True)
    derived_parser.add_argument("--tool", required=True)
    derived_parser.add_argument("--operation", required=True)
    derived_parser.add_argument("--tool-version")
    derived_parser.add_argument("--job-id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "set-rights":
            record = set_rights(
                args.asset_id,
                rights_status=args.rights_status,
                commercial_use=args.commercial_use,
                person_consent=args.person_consent,
                provider_data_scope=args.provider_data_scope,
                license_ref=args.license_ref,
                note=args.note,
            )
        else:
            record = register_derived(
                args.output_path,
                parents=args.parents,
                role=args.role,
                tool=args.tool,
                operation=args.operation,
                tool_version=args.tool_version,
                job_id=args.job_id,
            )
    except AssetRecordError as error:
        print(f"Asset-Rechte: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
