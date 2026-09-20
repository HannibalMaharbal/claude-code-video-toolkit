"""Fail-closed delivery authorization for registered assets and their provenance."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from contracts.validate_contracts import validate
from tools.asset_record import ASSET_ROOT as DEFAULT_ASSET_ROOT
from tools.asset_record import sha256_file

ASSET_ROOT = DEFAULT_ASSET_ROOT
DECISION_LOG_NAME = "delivery-gate.log.jsonl"
ALLOWED_RIGHTS = {"OWNED", "LICENSED", "USER_PROVIDED", "PUBLIC_DOMAIN"}
ALLOWED_CONSENT = {"not_needed", "documented"}


class DeliveryGateError(RuntimeError):
    """A requested asset cannot be resolved to one unique manifest."""


class GateResult(TypedDict):
    allowed: bool
    reasons: list[str]


def _record_files() -> list[Path]:
    return list(ASSET_ROOT.rglob("ast_*.asset.json")) if ASSET_ROOT.is_dir() else []


def _read_record(record_path: Path) -> dict[str, object]:
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeliveryGateError(f"Asset-Record ist nicht lesbar: {record_path.name}") from error
    if not isinstance(record, dict):
        raise DeliveryGateError(f"Asset-Record ist kein JSON-Objekt: {record_path.name}")
    return record


def _record_by_id(asset_id: str) -> tuple[dict[str, object], Path]:
    matches = [path for path in _record_files() if path.name == f"{asset_id}.asset.json"]
    if not matches:
        raise DeliveryGateError("Asset-Record nicht gefunden.")
    if len(matches) != 1:
        raise DeliveryGateError(f"Mehrere Asset-Records für {asset_id} gefunden.")
    return _read_record(matches[0]), matches[0]


def _record_by_path(value: Path) -> tuple[dict[str, object], Path]:
    target = value.expanduser().resolve()
    matches: list[tuple[dict[str, object], Path]] = []
    for record_path in _record_files():
        try:
            record = _read_record(record_path)
            relative_asset_path = record.get("path")
            if not isinstance(relative_asset_path, str):
                continue
            asset_path = (ASSET_ROOT / relative_asset_path).resolve()
            if asset_path == target:
                matches.append((record, record_path))
        except DeliveryGateError:
            continue
    if not matches:
        raise DeliveryGateError("Asset-Record nicht gefunden.")
    if len(matches) != 1:
        raise DeliveryGateError(f"Mehrere Asset-Records für {target.name} gefunden.")
    return matches[0]


def _resolve_record(asset_id_or_path: str | Path) -> tuple[dict[str, object], Path]:
    value = str(asset_id_or_path)
    if value.startswith("ast_") and "/" not in value and "\\" not in value:
        return _record_by_id(value)
    return _record_by_path(Path(value))


def _asset_path(record: dict[str, object]) -> Path | None:
    relative_path = record.get("path")
    if not isinstance(relative_path, str):
        return None
    candidate = (ASSET_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(ASSET_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _check_record(
    record: dict[str, object],
    record_path: Path,
    *,
    checked_ids: set[str],
    reasons: list[str],
) -> None:
    asset_id = record.get("asset_id")
    label = asset_id if isinstance(asset_id, str) else record_path.name
    if label in checked_ids:
        reasons.append(f"{label}: Parent-Graph enthält einen Zyklus.")
        return
    checked_ids.add(label)

    errors = validate("asset", record)
    if errors:
        reasons.append(f"{label}: Schema ungültig: {errors[0]}")
        return

    asset_path = _asset_path(record)
    expected_hash = record.get("sha256")
    if asset_path is None or not asset_path.is_file():
        reasons.append(f"{label}: Asset-Datei fehlt.")
    elif not isinstance(expected_hash, str) or sha256_file(asset_path) != expected_hash:
        reasons.append(f"{label}: SHA-256 stimmt nicht mit dem Record überein.")

    rights = record.get("rights")
    if not isinstance(rights, dict):
        reasons.append(f"{label}: Rechteblock fehlt.")
        return
    if rights.get("rights_status") not in ALLOWED_RIGHTS:
        reasons.append(f"{label}: rights_status ist nicht für Delivery freigegeben.")
    if rights.get("commercial_use") != "allowed":
        reasons.append(f"{label}: commercial_use ist nicht allowed.")
    if rights.get("person_consent") not in ALLOWED_CONSENT:
        reasons.append(f"{label}: person_consent ist nicht dokumentiert oder nicht_needed.")
    ai_involvement = record.get("ai_involvement")
    if not isinstance(ai_involvement, dict) or ai_involvement.get("ai_generated") == "unknown":
        reasons.append(f"{label}: ai_involvement.ai_generated ist unknown oder fehlt.")

    parent_ids = record.get("parent_ids", [])
    if not isinstance(parent_ids, list):
        reasons.append(f"{label}: parent_ids ist ungültig.")
        return
    for parent_id in parent_ids:
        if not isinstance(parent_id, str):
            reasons.append(f"{label}: Parent-ID ist ungültig.")
            continue
        try:
            parent, parent_path = _record_by_id(parent_id)
        except DeliveryGateError:
            reasons.append(f"{label}: Parent-Record fehlt: {parent_id}.")
            continue
        _check_record(parent, parent_path, checked_ids=checked_ids, reasons=reasons)


def _append_decision(asset_id_or_path: str | Path, result: GateResult) -> None:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "asset": str(asset_id_or_path),
        "allowed": result["allowed"],
        "reasons": result["reasons"],
    }
    with (ASSET_ROOT / DECISION_LOG_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def check(asset_id_or_path: str | Path) -> GateResult:
    """Return a logged, fail-closed delivery decision for an asset and all parents."""
    reasons: list[str] = []
    try:
        record, record_path = _resolve_record(asset_id_or_path)
        _check_record(record, record_path, checked_ids=set(), reasons=reasons)
    except DeliveryGateError as error:
        reasons.append(str(error))
    result: GateResult = {"allowed": not reasons, "reasons": reasons}
    _append_decision(asset_id_or_path, result)
    return result
