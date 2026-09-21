#!/usr/bin/env python3
"""Create and update media-pipeline projects under video-toolkit-media/projects/.

This is a separate concept from the toolkit's own `projects/<name>/project.json`
Remotion video-production projects (untouched, never read or written here).
Every manifest read or write is schema-validated; nothing is ever silently
accepted or persisted against contracts/project-manifest.schema.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate

MEDIA_ROOT = Path(__file__).resolve().parents[2] / "video-toolkit-media"
PROJECTS_ROOT = MEDIA_ROOT / "projects"
PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
PROJECT_SUBDIRS = ("brief", "specs", "manifests", "analysis", "qc", "prompts", "jobs", "provenance")


class ProjectInitError(RuntimeError):
    """A project could not be created, or its manifest could not be read/saved."""


def _manifest_path(project_id: str) -> Path:
    return PROJECTS_ROOT / project_id / "manifests" / "project.manifest.json"


def load_project_manifest(project_id: str) -> dict[str, Any]:
    """Load and schema-validate an existing project's manifest. Never repairs it."""
    path = _manifest_path(project_id)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectInitError(f"Projektmanifest nicht lesbar: {project_id}") from error
    errors = validate("project", manifest)
    if errors:
        raise ProjectInitError(f"Projektmanifest verletzt das Schema: {errors[0]}")
    return manifest


def save_project_manifest(project_id: str, manifest: dict[str, Any]) -> None:
    """Schema-validate, then atomically overwrite an existing project's manifest."""
    errors = validate("project", manifest)
    if errors:
        raise ProjectInitError(f"Projektmanifest verletzt das Schema: {errors[0]}")
    path = _manifest_path(project_id)
    if not path.parent.is_dir():
        raise ProjectInitError(f"Projekt nicht gefunden: {project_id}")
    content = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def add_asset_id(project_id: str, asset_id: str) -> dict[str, Any]:
    """Idempotently track an asset_id on a project's manifest (schema-validated)."""
    manifest = load_project_manifest(project_id)
    asset_ids = set(manifest.get("asset_ids") or [])
    if asset_id not in asset_ids:
        asset_ids.add(asset_id)
        manifest["asset_ids"] = sorted(asset_ids)
        save_project_manifest(project_id, manifest)
    return manifest


def init_project(project_id: str, *, brief_text: str = "") -> dict[str, Any]:
    """Create projects/<project_id>/ with its subfolders and a validated manifest."""
    if not PROJECT_ID_PATTERN.match(project_id):
        raise ProjectInitError(f"project_id verletzt das Muster: {project_id!r}")
    project_dir = PROJECTS_ROOT / project_id
    if project_dir.exists():
        raise ProjectInitError(f"Projekt existiert bereits: {project_id}")

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "created_at": datetime.now(UTC).isoformat(),
        "brief_ref": "brief/brief.md",
        "asset_ids": [],
        "lock_policy": {},
        "cost_decisions": [],
        "delivery_targets": [],
        "provenance_status": "none",
        "ai_labeling_status": "not_assessed",
    }
    errors = validate("project", manifest)
    if errors:
        raise ProjectInitError(f"Projektmanifest verletzt das Schema: {errors[0]}")

    for subdir in PROJECT_SUBDIRS:
        (project_dir / subdir).mkdir(parents=True)
    (project_dir / "brief" / "brief.md").write_text(
        brief_text or f"# {project_id}\n", encoding="utf-8"
    )
    manifest_path = project_dir / "manifests" / "project.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize a new media-pipeline project.")
    parser.add_argument("project_id")
    parser.add_argument("--brief", help="Optional brief text (else a placeholder is written).")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest = init_project(args.project_id, brief_text=args.brief or "")
    except ProjectInitError as error:
        print(f"Project-Init: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
