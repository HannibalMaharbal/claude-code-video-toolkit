#!/usr/bin/env python3
"""Per-project provenance report: recursive lineage, rights, QC, cost, and an
unsigned C2PA-shaped ingredient mapping (JSON only, no C2PA library).

set_labeling() is the only way ai_labeling_status ever changes -- always an
explicit, attributed, audited human action, never automatic.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import asset_record, project_init

VALID_LABELING_STATUSES = ("assessed_not_required", "required_pending", "applied")
_MIME_BY_MEDIA_TYPE = {
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "image": "image/png",
    "subtitle": "text/vtt",
    "document": "application/json",
    "other": "application/octet-stream",
}


class ProvenanceError(RuntimeError):
    """A provenance report or labeling-status change could not proceed."""


def build_asset_provenance(asset_id: str, *, _path: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Recursively walk parent_ids into a lineage tree. Raises on a cycle."""
    if asset_id in _path:
        raise ProvenanceError(f"Zyklus in parent_ids erkannt bei {asset_id}")
    record, _record_path = asset_record.load_asset_record(asset_id)
    node: dict[str, Any] = {
        "asset_id": asset_id,
        "role": record["role"],
        "media_type": record["media_type"],
        "sha256": record["sha256"],
        "created_at": record["created_at"],
        "lifecycle": record["lifecycle"],
        "rights": record["rights"],
        "ai_involvement": record["ai_involvement"],
    }
    derivation = record.get("derivation")
    if derivation:
        node["derivation"] = derivation
    parent_ids = cast("list[str]", record.get("parent_ids") or [])
    if parent_ids:
        node["parents"] = [
            build_asset_provenance(parent_id, _path=_path | {asset_id}) for parent_id in parent_ids
        ]
    return node


def _flatten(node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node]
    for parent in node.get("parents", []):
        nodes.extend(_flatten(parent))
    return nodes


def _rights_summary(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "rights_status_values": sorted({node["rights"]["rights_status"] for node in nodes}),
        "commercial_use_values": sorted({node["rights"]["commercial_use"] for node in nodes}),
        "person_consent_values": sorted({node["rights"]["person_consent"] for node in nodes}),
        "provider_data_scope_values": sorted(
            {node["rights"]["provider_data_scope"] for node in nodes}
        ),
    }


def _ai_involvement_summary(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    values = {node["ai_involvement"]["ai_generated"] for node in nodes}
    return {"ai_generated_values": sorted(values)}


def _tools_summary(nodes: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    tools: set[tuple[str, str | None]] = set()
    for node in nodes:
        derivation = node.get("derivation")
        if derivation:
            tools.add((derivation["tool"], derivation.get("tool_version")))
    return [{"tool": tool, "tool_version": version} for tool, version in sorted(tools)]


def _collect_qc_verdicts(project_id: str) -> list[dict[str, Any]]:
    qc_dir = project_init.PROJECTS_ROOT / project_id / "qc"
    if not qc_dir.is_dir():
        return []
    verdicts = []
    for path in sorted(qc_dir.glob("qcv_*.json")):
        try:
            verdicts.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return verdicts


def _mime_for_media_type(media_type: str) -> str:
    return _MIME_BY_MEDIA_TYPE.get(media_type, "application/octet-stream")


def _c2pa_manifest_for_asset(node: dict[str, Any]) -> dict[str, Any]:
    """An unsigned, C2PA-shaped manifest for one asset: claim_generator, ingredients
    (direct parents, parentOf), one c2pa.actions assertion. Informational only --
    no signature, no C2PA library, not a certified/validatable manifest."""
    derivation = node.get("derivation") or {}
    ingredients = [
        {
            "title": parent["asset_id"],
            "format": _mime_for_media_type(parent["media_type"]),
            "instanceId": parent["asset_id"],
            "relationship": "parentOf",
            "hash": {"alg": "sha256", "value": parent["sha256"]},
            "validationStatus": [],
        }
        for parent in node.get("parents", [])
    ]
    return {
        "claim_generator": derivation.get("tool", "unknown"),
        "title": node["asset_id"],
        "format": _mime_for_media_type(node["media_type"]),
        "instanceId": node["asset_id"],
        "ingredients": ingredients,
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {"actions": [{"action": derivation.get("operation", "c2pa.created")}]},
            }
        ],
        "signature": None,
        "note": "unsigned, internal-only, not a validated/certified C2PA manifest",
    }


def generate_report(project_id: str) -> dict[str, Any]:
    manifest = project_init.load_project_manifest(project_id)
    asset_ids = manifest.get("asset_ids") or []
    graphs = [build_asset_provenance(asset_id) for asset_id in asset_ids]
    by_id = {node["asset_id"]: node for graph in graphs for node in _flatten(graph)}
    unique_nodes = list(by_id.values())

    return {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "asset_graphs": graphs,
        "rights_summary": _rights_summary(unique_nodes),
        "ai_involvement_summary": _ai_involvement_summary(unique_nodes),
        "tools": _tools_summary(unique_nodes),
        "qc_verdicts": _collect_qc_verdicts(project_id),
        "cost_decisions": manifest.get("cost_decisions") or [],
        "c2pa_manifests": [_c2pa_manifest_for_asset(node) for node in graphs],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Provenance Report — {report['project_id']}",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Assets",
    ]
    for graph in report["asset_graphs"]:
        lines.append(f"- {graph['asset_id']} ({graph['role']}, {graph['media_type']})")
    lines += ["", "## Rights Summary"]
    for key, values in report["rights_summary"].items():
        lines.append(f"- {key}: {', '.join(values) if values else '-'}")
    lines += [
        "",
        "## AI Involvement",
        "- ai_generated values: "
        + ", ".join(report["ai_involvement_summary"]["ai_generated_values"]),
        "",
        "## Tools",
    ]
    for tool in report["tools"]:
        lines.append(f"- {tool['tool']} ({tool['tool_version'] or 'unversioned'})")
    lines += ["", f"## QC Verdicts ({len(report['qc_verdicts'])})"]
    for verdict in report["qc_verdicts"]:
        lines.append(
            f"- {verdict['verdict_id']}: {verdict['overall']} (asset {verdict['asset_id']})"
        )
    lines += ["", f"## Cost Decisions ({len(report['cost_decisions'])})"]
    for decision in report["cost_decisions"]:
        lines.append(f"- {decision['step']}: {decision['cost_class']}")
    return "\n".join(lines) + "\n"


def write_report(project_id: str) -> tuple[dict[str, Any], Path, Path]:
    """Generate, write (JSON+MD, never overwriting), and mark provenance_status."""
    report = generate_report(project_id)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    provenance_dir = project_init.PROJECTS_ROOT / project_id / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    json_path = provenance_dir / f"provenance-{timestamp}.json"
    md_path = provenance_dir / f"provenance-{timestamp}.md"
    if json_path.exists() or md_path.exists():
        raise ProvenanceError(f"Provenance-Bericht existiert bereits: {timestamp}")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    manifest = project_init.load_project_manifest(project_id)
    manifest["provenance_status"] = "internal_hash_graph"
    project_init.save_project_manifest(project_id, manifest)

    return report, json_path, md_path


def set_labeling(project_id: str, status: str, *, note: str, by: str) -> dict[str, Any]:
    """The only path that changes ai_labeling_status -- always explicit and audited."""
    if status not in VALID_LABELING_STATUSES:
        raise ProvenanceError(f"status muss eine von {VALID_LABELING_STATUSES} sein.")
    if not note.strip():
        raise ProvenanceError("--note darf nicht leer sein.")
    if not by.strip():
        raise ProvenanceError("--by darf nicht leer sein.")

    manifest = project_init.load_project_manifest(project_id)
    old_status = manifest.get("ai_labeling_status")
    manifest["ai_labeling_status"] = status
    project_init.save_project_manifest(project_id, manifest)

    audit_path = project_init.PROJECTS_ROOT / project_id / "provenance" / "labeling-audit.log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "old_status": old_status,
        "new_status": status,
        "note": note,
        "by": by,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provenance reports and labeling status.")
    commands = parser.add_subparsers(dest="command", required=True)

    report_cmd = commands.add_parser("report", help="Generate a provenance report.")
    report_cmd.add_argument("project_id")

    labeling_cmd = commands.add_parser("set-labeling", help="Set ai_labeling_status (audited).")
    labeling_cmd.add_argument("project_id")
    labeling_cmd.add_argument("--status", required=True, choices=VALID_LABELING_STATUSES)
    labeling_cmd.add_argument("--note", required=True)
    labeling_cmd.add_argument("--by", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "report":
            _report, json_path, md_path = write_report(args.project_id)
            result: dict[str, Any] = {"json_path": str(json_path), "md_path": str(md_path)}
        else:
            manifest = set_labeling(args.project_id, args.status, note=args.note, by=args.by)
            result = {"ai_labeling_status": manifest["ai_labeling_status"]}
    except ProvenanceError as error:
        print(f"Provenance: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
