#!/usr/bin/env python3
"""Structured QC verdicts (P2): run technical checks, gate DELIVERY on human accept.

Visual checks (product, brand, face_hands, continuity) have no local image
model to run against, so they are always recorded as needs_human -- never a
silent pass. A verdict can only reach overall=accept through an explicit,
attributed human review (apply_review), never automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate
from tools import asset_record, media_validation, project_init

VISUAL_CHECKS = ("product", "brand", "face_hands", "continuity")
OVERALL_STATUSES = ("accept", "retry", "reject", "needs_human")


class QcPipelineError(RuntimeError):
    """A QC verdict could not be created, retried, reviewed, or found."""


def _verdict_path(project_id: str, verdict_id: str) -> Path:
    return project_init.PROJECTS_ROOT / project_id / "qc" / f"{verdict_id}.json"


def _run_technical(asset_path: Path, media_type: str) -> dict[str, str]:
    if media_type != "video":
        return {"name": "technical", "status": "not_run", "evidence": f"media_type={media_type}."}
    try:
        report = media_validation.validate_video(asset_path)
    except media_validation.MediaValidationError as error:
        return {"name": "technical", "status": "fail", "evidence": str(error)}
    return {
        "name": "technical",
        "status": "pass",
        "evidence": f"{report.codec}, {report.duration:.2f}s",
    }


def _run_audio(asset_path: Path, media_type: str) -> dict[str, str]:
    if media_type not in ("video", "audio"):
        return {"name": "audio", "status": "not_run", "evidence": f"media_type={media_type}."}
    try:
        report = media_validation.validate_audio(asset_path)
    except media_validation.MediaValidationError as error:
        if "Audiospur" in str(error):
            return {"name": "audio", "status": "not_run", "evidence": str(error)}
        return {"name": "audio", "status": "fail", "evidence": str(error)}
    return {
        "name": "audio",
        "status": "pass",
        "evidence": f"{report.details['loudnessLufs']} LUFS",
    }


def _run_subtitle(asset_path: Path, media_type: str) -> dict[str, str]:
    if media_type != "subtitle":
        return {"name": "subtitle", "status": "not_run", "evidence": f"media_type={media_type}."}
    from tools.transcribe import validate_subtitle_file

    errors = validate_subtitle_file(asset_path)
    if errors:
        return {"name": "subtitle", "status": "fail", "evidence": "; ".join(errors)}
    return {"name": "subtitle", "status": "pass", "evidence": "SRT/VTT-Struktur und Cues valide."}


def _run_layout(asset_path: Path, record: dict[str, Any]) -> dict[str, str]:
    derivation = record.get("derivation") or {}
    if derivation.get("tool") != "layout_render":
        return {"name": "layout", "status": "not_run", "evidence": "Kein layout_render-Derivat."}
    try:
        if asset_path.suffix.lower() == ".pdf":
            if not asset_path.read_bytes()[:5] == b"%PDF-":
                raise ValueError("Keine gueltige PDF-Signatur.")
        else:
            from PIL import Image

            with Image.open(asset_path) as image:
                image.verify()
    except Exception as error:  # noqa: BLE001 - any decode/verify failure is a real QC fail
        return {"name": "layout", "status": "fail", "evidence": str(error)}
    return {"name": "layout", "status": "pass", "evidence": "Renderausgabe strukturell valide."}


def _visual_checks() -> list[dict[str, str]]:
    return [
        {"name": name, "status": "needs_human", "evidence": "Kein lokales Bildmodell verfuegbar."}
        for name in VISUAL_CHECKS
    ]


def _run_all_checks(asset_path: Path, record: dict[str, Any]) -> list[dict[str, str]]:
    media_type = str(record["media_type"])
    return [
        _run_technical(asset_path, media_type),
        *_visual_checks(),
        _run_subtitle(asset_path, media_type),
        _run_audio(asset_path, media_type),
        _run_layout(asset_path, record),
    ]


def _overall(checks: list[dict[str, str]]) -> str:
    statuses = {check["status"] for check in checks}
    if "fail" in statuses:
        return "reject"
    if "needs_human" in statuses:
        return "needs_human"
    return "accept"


def _save_verdict(project_id: str, verdict: dict[str, Any]) -> None:
    errors = validate("qc_verdict", verdict)
    if errors:
        raise QcPipelineError(f"QC-Verdikt verletzt das Schema: {errors[0]}")
    path = _verdict_path(project_id, verdict["verdict_id"])
    if not path.parent.is_dir():
        raise QcPipelineError(f"Projekt oder qc/-Ordner fehlt: {project_id}")
    content = json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def load_verdict(project_id: str, verdict_id: str) -> dict[str, Any]:
    path = _verdict_path(project_id, verdict_id)
    try:
        verdict = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QcPipelineError(f"QC-Verdikt nicht lesbar: {verdict_id}") from error
    errors = validate("qc_verdict", verdict)
    if errors:
        raise QcPipelineError(f"QC-Verdikt verletzt das Schema: {errors[0]}")
    return verdict


def run_qc(project_id: str, asset_id: str, *, retry_limit: int = 3) -> dict[str, Any]:
    """Run every applicable technical check once and write a fresh verdict."""
    record, _path = asset_record.load_asset_record(asset_id)
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    if not asset_path.is_file():
        raise QcPipelineError(f"Asset-Datei fehlt: {asset_id}")

    checks = _run_all_checks(asset_path, record)
    digest = hashlib.sha256(
        f"{asset_id}:{datetime.now(UTC).isoformat()}".encode()
    ).hexdigest()
    verdict: dict[str, Any] = {
        "schema_version": "1.0.0",
        "verdict_id": f"qcv_{digest[:20]}",
        "asset_id": asset_id,
        "created_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "overall": _overall(checks),
        "retry_count": 0,
        "retry_limit": retry_limit,
    }
    errors = validate("qc_verdict", verdict)
    if errors:
        raise QcPipelineError(f"QC-Verdikt verletzt das Schema: {errors[0]}")

    path = _verdict_path(project_id, verdict["verdict_id"])
    if path.exists():
        raise QcPipelineError(f"QC-Verdikt existiert bereits: {verdict['verdict_id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return verdict


def retry_qc(project_id: str, verdict_id: str) -> dict[str, Any]:
    """Re-run every check, bump retry_count, and refuse once retry_limit is hit."""
    verdict = load_verdict(project_id, verdict_id)
    if verdict["retry_count"] >= verdict["retry_limit"]:
        raise QcPipelineError(
            f"Retry-Limit erreicht: {verdict['retry_count']}/{verdict['retry_limit']}."
        )
    record, _path = asset_record.load_asset_record(verdict["asset_id"])
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    if not asset_path.is_file():
        raise QcPipelineError(f"Asset-Datei fehlt: {verdict['asset_id']}")

    verdict["checks"] = _run_all_checks(asset_path, record)
    verdict["overall"] = _overall(verdict["checks"])
    verdict["retry_count"] += 1
    verdict.pop("reviewer", None)
    _save_verdict(project_id, verdict)
    return verdict


def apply_review(
    project_id: str, verdict_id: str, *, reviewer: str, overall: str
) -> dict[str, Any]:
    """Record a human's explicit, attributed decision on an existing verdict."""
    if not reviewer.strip():
        raise QcPipelineError("reviewer darf nicht leer sein.")
    if overall not in OVERALL_STATUSES:
        raise QcPipelineError(f"overall muss eine von {OVERALL_STATUSES} sein.")
    verdict = load_verdict(project_id, verdict_id)
    verdict["overall"] = overall
    verdict["reviewer"] = reviewer
    _save_verdict(project_id, verdict)
    return verdict


def find_accepted_verdict(asset_id: str) -> dict[str, Any] | None:
    """Scan every project's qc/ folder for the newest accepted verdict on this asset."""
    if not project_init.PROJECTS_ROOT.is_dir():
        return None
    accepted: list[dict[str, Any]] = []
    for path in project_init.PROJECTS_ROOT.glob("*/qc/qcv_*.json"):
        try:
            verdict = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if verdict.get("asset_id") != asset_id or verdict.get("overall") != "accept":
            continue
        if validate("qc_verdict", verdict):
            continue
        accepted.append(verdict)
    if not accepted:
        return None
    return max(accepted, key=lambda entry: str(entry["created_at"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, retry, or review structured QC verdicts.")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="Run all applicable checks and write a verdict.")
    run_cmd.add_argument("project_id")
    run_cmd.add_argument("asset_id")
    run_cmd.add_argument("--retry-limit", type=int, default=3)

    retry_cmd = commands.add_parser("retry", help="Re-run checks on an existing verdict.")
    retry_cmd.add_argument("project_id")
    retry_cmd.add_argument("verdict_id")

    review_cmd = commands.add_parser("review", help="Record a human review decision.")
    review_cmd.add_argument("project_id")
    review_cmd.add_argument("verdict_id")
    review_cmd.add_argument("--by", required=True, dest="reviewer")
    review_cmd.add_argument("--overall", required=True, choices=OVERALL_STATUSES)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "run":
            result = run_qc(args.project_id, args.asset_id, retry_limit=args.retry_limit)
        elif args.command == "retry":
            result = retry_qc(args.project_id, args.verdict_id)
        else:
            result = apply_review(
                args.project_id, args.verdict_id, reviewer=args.reviewer, overall=args.overall
            )
    except QcPipelineError as error:
        print(f"QC-Pipeline: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
