#!/usr/bin/env python3
"""Cost cascade router: cached_asset > local_deterministic > included_approved_surface
> external_specialist > premium, driven by contracts/task-routing.json.

external_specialist and premium are gated twice: a human approval file that
only `cost_router.py approve` can create, and the egress guard underneath --
approving a cost tier never grants network access by itself.
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

from tools import asset_record, project_init
from tools.egress_guard import EgressBlocked, require_egress

ROOT = Path(__file__).resolve().parents[1]
TASK_ROUTING_PATH = ROOT / "contracts" / "task-routing.json"
GATED_COST_CLASSES = ("external_specialist", "premium")


class CostRouterError(RuntimeError):
    """A cost decision could not be made, approved, or recorded."""


def _routing_table() -> dict[str, Any]:
    return json.loads(TASK_ROUTING_PATH.read_text(encoding="utf-8"))


def _base_cost_class(task_type: str) -> tuple[str, bool]:
    """Map a task-routing route's locality to one rung of the cost cascade."""
    routes = _routing_table().get("routes", {})
    if task_type not in routes:
        raise CostRouterError(f"Unbekannter Aufgabentyp: {task_type!r}")
    route = routes[task_type]
    requires_approval = bool(route["requires_approval"])
    locality = route["locality"]
    if locality == "local":
        return "local_deterministic", requires_approval
    if locality == "mixed":
        return "included_approved_surface", requires_approval
    return "external_specialist", requires_approval


def find_cached_asset(*, tool: str, operation: str, params_sha256: str) -> dict[str, Any] | None:
    """Find an existing derived asset with matching (tool, operation, params_sha256)."""
    if not asset_record.ASSET_ROOT.is_dir():
        return None
    for path in asset_record.ASSET_ROOT.rglob("*.asset.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        derivation = record.get("derivation") or {}
        if (
            derivation.get("tool") != tool
            or derivation.get("operation") != operation
            or derivation.get("params_sha256") != params_sha256
        ):
            continue
        asset_path = asset_record.ASSET_ROOT / str(record.get("path", ""))
        if not asset_path.is_file():
            continue
        if asset_record.sha256_file(asset_path) != record.get("sha256"):
            continue
        return record
    return None


def _approval_path(project_id: str, step: str) -> Path:
    return project_init.PROJECTS_ROOT / project_id / "provenance" / f"{step}.approval.json"


def _cost_log_path(project_id: str) -> Path:
    return project_init.PROJECTS_ROOT / project_id / "cost-log.jsonl"


def approve(project_id: str, step: str, *, by: str) -> dict[str, Any]:
    """Create the approval file external_specialist/premium decisions require."""
    if not by.strip():
        raise CostRouterError("--by darf nicht leer sein.")
    project_init.load_project_manifest(project_id)  # fail fast if the project doesn't exist
    approval = {
        "step": step,
        "approved_by": by,
        "approved_at": datetime.now(UTC).isoformat(),
    }
    path = _approval_path(project_id, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return approval


def _load_approval(project_id: str, step: str) -> dict[str, Any] | None:
    path = _approval_path(project_id, step)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _append_cost_log(project_id: str, entry: dict[str, Any]) -> None:
    path = _cost_log_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def decide(
    project_id: str,
    step: str,
    *,
    task_type: str,
    tool: str,
    operation: str,
    params_sha256: str,
    premium: bool = False,
    known_cost: dict[str, Any] | None = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Force the cascade, record a cost_decision on the project manifest, and log it.

    Never retries automatically: a missing approval or a blocked egress attempt
    raises CostRouterError/EgressBlocked immediately, once, with no fallback.
    """
    cached = find_cached_asset(tool=tool, operation=operation, params_sha256=params_sha256)
    if cached is not None:
        cost_class, requires_approval = "cached_asset", False
    elif premium:
        cost_class, requires_approval = "premium", True
        if not fallback_reason or not fallback_reason.strip():
            raise CostRouterError("premium braucht einen nicht-leeren fallback_reason.")
    else:
        cost_class, requires_approval = _base_cost_class(task_type)

    decision: dict[str, Any] = {
        "step": step,
        "cost_class": cost_class,
        "known_cost": known_cost,
        "quota_status": "ok" if cost_class != "external_specialist" else "unknown",
        "fallback_reason": fallback_reason,
        "approval_required": requires_approval,
    }
    if cost_class == "premium":
        decision["quota_status"] = "unknown"

    if cost_class in GATED_COST_CLASSES:
        approval = _load_approval(project_id, step)
        if approval is None:
            raise CostRouterError(
                f"{cost_class} braucht eine Freigabe: "
                f"cost_router.py approve {project_id} {step} --by <name>"
            )
        decision["approval_status"] = "approved"
        decision["approved_by"] = approval["approved_by"]
        decision["approved_at"] = approval["approved_at"]
        # An approval file authorizes spend tracking, never network access by itself.
        require_egress(f"cost_tier:{cost_class}", step)
    elif requires_approval:
        # included_approved_surface: pre-approved by the routing table itself, not
        # by a per-step human file -- recorded as a system approval, not a real one.
        decision["approval_status"] = "approved"
        decision["approved_by"] = "system:task-routing"
        decision["approved_at"] = datetime.now(UTC).isoformat()

    manifest = project_init.load_project_manifest(project_id)
    cost_decisions = list(manifest.get("cost_decisions") or [])
    cost_decisions.append(decision)
    manifest["cost_decisions"] = cost_decisions
    project_init.save_project_manifest(project_id, manifest)

    _append_cost_log(
        project_id,
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "task_type": task_type,
            "tool": tool,
            "operation": operation,
            "params_sha256": params_sha256,
            "cached_asset_id": cached.get("asset_id") if cached else None,
            **decision,
        },
    )
    return {"decision": decision, "cached_asset": cached}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Force the cost cascade for one project step.")
    commands = parser.add_subparsers(dest="command", required=True)

    decide_cmd = commands.add_parser("decide", help="Make and record a cost decision.")
    decide_cmd.add_argument("project_id")
    decide_cmd.add_argument("step")
    decide_cmd.add_argument("--task-type", required=True)
    decide_cmd.add_argument("--tool", required=True)
    decide_cmd.add_argument("--operation", required=True)
    decide_cmd.add_argument("--params-sha256", required=True)
    decide_cmd.add_argument("--premium", action="store_true")
    decide_cmd.add_argument("--fallback-reason")
    decide_cmd.add_argument("--known-cost-amount", type=float)
    decide_cmd.add_argument("--known-cost-currency")
    decide_cmd.add_argument(
        "--known-cost-unit", choices=("render", "second", "credit", "request", "flat")
    )

    approve_cmd = commands.add_parser("approve", help="Create an approval for a gated step.")
    approve_cmd.add_argument("project_id")
    approve_cmd.add_argument("step")
    approve_cmd.add_argument("--by", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "approve":
            result: dict[str, Any] = approve(args.project_id, args.step, by=args.by)
        else:
            known_cost = None
            if args.known_cost_amount is not None:
                if not args.known_cost_currency or not args.known_cost_unit:
                    raise CostRouterError(
                        "--known-cost-amount braucht --known-cost-currency und --known-cost-unit."
                    )
                known_cost = {
                    "amount": args.known_cost_amount,
                    "currency": args.known_cost_currency,
                    "unit": args.known_cost_unit,
                }
            result = decide(
                args.project_id,
                args.step,
                task_type=args.task_type,
                tool=args.tool,
                operation=args.operation,
                params_sha256=args.params_sha256,
                premium=args.premium,
                known_cost=known_cost,
                fallback_reason=args.fallback_reason,
            )
    except (CostRouterError, EgressBlocked) as error:
        print(f"Cost-Router: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
