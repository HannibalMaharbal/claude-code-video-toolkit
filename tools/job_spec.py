#!/usr/bin/env python3
"""Build job specifications that carry hash-pinned, freshly re-verified locks.

A job spec is rejected outright if any active lock's reference set no longer
verifies (a member asset changed) or no longer matches the hash the project
was bound to -- never built with a stale or silently-updated lock.
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

from tools import project_init
from tools.reference_registry import ReferenceRegistryError, verify_set


class JobSpecError(RuntimeError):
    """A job specification could not be built because a lock is no longer valid."""


def build(project_id: str, step: str) -> dict[str, Any]:
    """Build (without persisting) a job spec whose locks are freshly re-verified."""
    if not step.strip():
        raise JobSpecError("step darf nicht leer sein.")
    manifest = project_init.load_project_manifest(project_id)
    lock_policy = manifest.get("lock_policy") or {}

    active_locks: dict[str, Any] = {}
    for lock_key, lock in lock_policy.items():
        if not lock.get("enabled"):
            continue
        reference_set_id = lock["reference_set_id"]
        try:
            refset = verify_set(reference_set_id)
        except ReferenceRegistryError as error:
            raise JobSpecError(
                f"Lock {lock_key} referenziert ein ungueltiges Set {reference_set_id}: {error}"
            ) from error
        if refset["set_sha256"] != lock["reference_set_sha256"]:
            raise JobSpecError(
                f"Lock {lock_key} ist an Hash {lock['reference_set_sha256']} gebunden, "
                f"Set {reference_set_id} hat jetzt {refset['set_sha256']}."
            )
        active_locks[lock_key] = {
            "reference_set_id": reference_set_id,
            "reference_set_sha256": refset["set_sha256"],
            "on_drift": lock.get("on_drift", "qc_fail"),
        }

    return {
        "project_id": project_id,
        "step": step,
        "created_at": datetime.now(UTC).isoformat(),
        "locks": active_locks,
    }


def build_and_write(project_id: str, step: str) -> tuple[dict[str, Any], Path]:
    """Build a job spec and persist it under the project's jobs/ folder."""
    job = build(project_id, step)
    job_id = f"job_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
    jobs_dir = project_init.PROJECTS_ROOT / project_id / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    path = jobs_dir / f"{job_id}.json"
    payload = {"job_id": job_id, **job}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a lock-verified job specification.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="Build and write a job spec.")
    build_cmd.add_argument("project_id")
    build_cmd.add_argument("step")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        job, path = build_and_write(args.project_id, args.step)
    except JobSpecError as error:
        print(f"Job-Spec: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps({**job, "path": str(path)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
