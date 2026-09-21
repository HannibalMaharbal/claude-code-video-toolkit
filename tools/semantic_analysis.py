#!/usr/bin/env python3
"""Semantic analysis contract: local-first frame/transcript prep, agent-result ingest.

Cloud analyzers are only permitted when the target asset's own rights record
says so (provider_data_scope=cloud_approved and the provider is listed in
approved_providers). prepare() enforces this at request time; ingest()
re-verifies it against the asset's *current* rights rather than trusting an
agent-supplied self-declaration in the result file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate
from tools import asset_record, project_init
from tools.video_ingest import probe_media

DEFAULT_INTERVAL_S = 2.0
DEFAULT_MAX_FRAMES = 30


class SemanticAnalysisError(RuntimeError):
    """A semantic-analysis prepare/ingest step could not proceed."""


def _analysis_dir(project_id: str) -> Path:
    return project_init.PROJECTS_ROOT / project_id / "analysis"


def _cloud_log_path(project_id: str) -> Path:
    return _analysis_dir(project_id) / "cloud-rejections.log.jsonl"


def _cloud_allowance(record: dict[str, Any]) -> dict[str, Any]:
    rights = record.get("rights") or {}
    approved_providers = list(rights.get("approved_providers") or [])
    allowed = rights.get("provider_data_scope") == "cloud_approved" and bool(approved_providers)
    return {"cloud_allowed": allowed, "approved_providers": approved_providers}


def _log_cloud_rejection(project_id: str, asset_id: str, reason: str) -> None:
    path = _cloud_log_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(UTC).isoformat(), "asset_id": asset_id, "reason": reason}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def prepare(
    project_id: str,
    asset_id: str,
    *,
    requested_scope: str = "local",
    interval_s: float = DEFAULT_INTERVAL_S,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> dict[str, Any]:
    """Extract a bounded set of frames; report which analyzer scope is allowed.

    Local is always allowed. A "cloud" request is refused (and logged) unless
    the asset's own rights already say provider_data_scope=cloud_approved with
    a non-empty approved_providers list.
    """
    if requested_scope not in ("local", "cloud"):
        raise SemanticAnalysisError("requested_scope muss 'local' oder 'cloud' sein.")
    record, _path = asset_record.load_asset_record(asset_id)
    allowance = _cloud_allowance(record)
    if requested_scope == "cloud" and not allowance["cloud_allowed"]:
        reason = (
            f"Asset {asset_id} ist nicht cloud_approved oder hat keine "
            f"approved_providers (rights={record.get('rights')})."
        )
        _log_cloud_rejection(project_id, asset_id, reason)
        raise SemanticAnalysisError(f"Cloud-Nutzung abgelehnt: {reason}")

    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    metadata = probe_media(asset_path)
    duration = float(cast(float, metadata["duration"]))

    frames_dir = _analysis_dir(project_id) / f"{asset_id}-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[str] = []
    index = 0
    while index < max_frames:
        timestamp = index * interval_s
        if timestamp >= duration:
            break
        frame_path = frames_dir / f"frame-{index:04d}.png"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{timestamp}", "-i", str(asset_path),
                    "-frames:v", "1", str(frame_path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except subprocess.CalledProcessError as error:
            raise SemanticAnalysisError(
                f"Frame-Extraktion fehlgeschlagen: {error.stderr[-500:]}"
            ) from error
        frame_paths.append(str(frame_path))
        index += 1

    return {
        "project_id": project_id,
        "asset_id": asset_id,
        "local_allowed": True,
        "cloud_allowed": allowance["cloud_allowed"],
        "approved_providers": allowance["approved_providers"],
        "frames": frame_paths,
        "interval_s": interval_s,
    }


def ingest(project_id: str, result_path: Path) -> dict[str, Any]:
    """Validate an agent-produced result, write analysis/semantic.json, register it."""
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SemanticAnalysisError(f"Ergebnis nicht lesbar: {error}") from error
    errors = validate("semantic_analysis", result)
    if errors:
        raise SemanticAnalysisError(f"Ergebnis verletzt das Schema: {errors[0]}")

    asset_id = result["asset_id"]
    record, _path = asset_record.load_asset_record(asset_id)
    analyzer = result["analyzer"]
    if analyzer["scope"] == "cloud_approved":
        allowance = _cloud_allowance(record)
        provider = analyzer.get("provider")
        if not allowance["cloud_allowed"] or provider not in allowance["approved_providers"]:
            reason = (
                f"Analyzer behauptet cloud_approved (provider={provider!r}) fuer {asset_id}, "
                f"aber das Asset erlaubt das nicht (rights={record.get('rights')})."
            )
            _log_cloud_rejection(project_id, asset_id, reason)
            raise SemanticAnalysisError(f"Scope-Nachweis ungültig: {reason}")

    analysis_dir = _analysis_dir(project_id)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    output_path = analysis_dir / "semantic.json"
    if output_path.exists():
        raise SemanticAnalysisError(
            f"analysis/semantic.json existiert bereits fuer Projekt {project_id}."
        )
    content = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output_path.write_text(content, encoding="utf-8")

    derived = asset_record.register_derived(
        output_path,
        parents=[asset_id],
        role="VARIANT",
        tool=analyzer["name"],
        operation="semantic_analysis",
        ai_generated="partial",
    )
    return {"semantic_path": str(output_path), "asset_record": derived}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare and ingest semantic analysis.")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_cmd = commands.add_parser("prepare", help="Extract frames; report allowed scope.")
    prepare_cmd.add_argument("project_id")
    prepare_cmd.add_argument("asset_id")
    prepare_cmd.add_argument("--scope", choices=("local", "cloud"), default="local")
    prepare_cmd.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S)
    prepare_cmd.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES)

    ingest_cmd = commands.add_parser("ingest", help="Validate and register a result file.")
    ingest_cmd.add_argument("project_id")
    ingest_cmd.add_argument("result_path", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "prepare":
            result = prepare(
                args.project_id,
                args.asset_id,
                requested_scope=args.scope,
                interval_s=args.interval,
                max_frames=args.max_frames,
            )
        else:
            result = ingest(args.project_id, args.result_path)
    except SemanticAnalysisError as error:
        print(f"Semantic-Analysis: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
