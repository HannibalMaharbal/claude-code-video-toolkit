"""Read-only inventory of local automation that could cross the egress boundary."""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.egress_guard import N8N_WORKFLOWS_DIR  # noqa: E402

HOME = Path.home()
LAUNCH_AGENTS_DIR = HOME / "Library" / "LaunchAgents"
NLM_UPLOAD_DIR = HOME / "Documents" / "nlm-upload"
ASSET_ROOT = HOME / "PROJEKTE" / "video-toolkit-media" / "assets"
REPO_ROOTS = {
    "video-toolkit": Path(__file__).resolve().parents[1],
    "video-toolkit-media": HOME / "PROJEKTE" / "video-toolkit-media",
}


def _launch_agents() -> list[dict[str, object]]:
    agents: list[dict[str, object]] = []
    for plist_path in sorted(LAUNCH_AGENTS_DIR.glob("*.plist")):
        try:
            raw = plist_path.read_bytes()
        except OSError:
            continue
        try:
            payload = plistlib.loads(raw)
        except plistlib.InvalidFileException:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        arguments = payload.get("ProgramArguments", []) if isinstance(payload, dict) else payload
        if not isinstance(arguments, list):
            continue
        values = [str(argument) for argument in arguments]
        if any("video-toolkit" in value or "nlm" in value.casefold() for value in values):
            agents.append({"path": str(plist_path), "arguments": values})
    return agents


def _asset_root_relation() -> dict[str, object]:
    upload_root = NLM_UPLOAD_DIR.resolve()
    asset_root = ASSET_ROOT.resolve()
    related = False
    try:
        upload_root.relative_to(asset_root)
        related = True
    except ValueError:
        try:
            asset_root.relative_to(upload_root)
            related = True
        except ValueError:
            pass
    return {
        "nlm_upload_path": str(upload_root),
        "asset_root": str(asset_root),
        "related_or_linked": related,
    }


def _active_n8n_workflows() -> list[dict[str, object]]:
    workflows: list[dict[str, object]] = []
    for workflow_path in sorted(N8N_WORKFLOWS_DIR.glob("*.json")):
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if workflow.get("active") is True:
            workflows.append(
                {
                    "path": str(workflow_path),
                    "name": workflow.get("name"),
                    "node_types": [
                        node.get("type")
                        for node in workflow.get("nodes", [])
                        if isinstance(node, dict)
                    ],
                }
            )
    return workflows


def _run_git(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip()


def repo_remote_push_status(repo_root: Path) -> list[dict[str, object]]:
    """Report each remote's fetch/push URL and whether push has been disabled.

    Read-only: never changes a remote's configuration. "Disabled" means the
    push URL was deliberately pointed away from the fetch URL (e.g. the
    DISABLED_INTERNAL_ONLY sentinel), not that push is technically impossible.
    """
    if not (repo_root / ".git").exists():
        return []
    names_raw = _run_git(repo_root, "remote")
    if not names_raw:
        return []
    remotes: list[dict[str, object]] = []
    for name in names_raw.splitlines():
        if not name:
            continue
        fetch_url = _run_git(repo_root, "remote", "get-url", name)
        push_url = _run_git(repo_root, "remote", "get-url", "--push", name)
        remotes.append(
            {
                "name": name,
                "fetch_url": fetch_url,
                "push_url": push_url,
                "push_disabled": push_url is not None and push_url != fetch_url,
            }
        )
    return remotes


def _repo_push_status() -> dict[str, object]:
    return {
        name: {"path": str(root), "remotes": repo_remote_push_status(root)}
        for name, root in REPO_ROOTS.items()
    }


def audit() -> dict[str, object]:
    """Return an inventory without changing launchd, n8n, files, or services."""
    return {
        "launch_agents": _launch_agents(),
        "asset_root_relation": _asset_root_relation(),
        "active_n8n_workflows": _active_n8n_workflows(),
        "repo_push_status": _repo_push_status(),
    }


def main() -> None:
    print(json.dumps(audit(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
