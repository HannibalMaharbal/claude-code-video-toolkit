"""Repository-visible, fail-closed controls for any outbound action."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "contracts" / "egress-policy.json"
ALLOWLIST_PATH = REPO_ROOT / "contracts" / "egress-allowlist.json"
N8N_WORKFLOWS_DIR = Path.home() / ".n8n" / "workflows"
ACTIVE_N8N_NODE_ALLOWLIST = {
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.set",
    "n8n-nodes-base.code",
    "n8n-nodes-base.respondToWebhook",
}

SEND_PATTERNS = {
    "googleapiclient": re.compile(r"\bgoogleapiclient\b", re.IGNORECASE),
    "requests_send": re.compile(r"\brequests\.(?:post|put|patch|request)\b", re.IGNORECASE),
    "httpx_send": re.compile(r"\bhttpx\.(?:post|put|patch|request)\b", re.IGNORECASE),
    "urllib_send": re.compile(
        r"\burllib\.request\.(?:urlopen|urlretrieve)\b", re.IGNORECASE
    ),
    "smtplib": re.compile(r"\bsmtplib\b", re.IGNORECASE),
    "social_api": re.compile(r"\b(?:instagram|facebook|tiktok)\b", re.IGNORECASE),
    "nlm_source_add": re.compile(r"\bnlm\s+source\s+add\b", re.IGNORECASE),
}


class EgressBlocked(RuntimeError):
    """An action attempted to cross the internal-only boundary."""


def load_policy() -> dict[str, object]:
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EgressBlocked(f"Egress-Policy ist nicht lesbar: {error}") from error
    if not isinstance(policy, dict):
        raise EgressBlocked("Egress-Policy ist kein JSON-Objekt.")
    return policy


def require_egress(action: str, target: str) -> None:
    """Permit egress only through an explicitly committed release policy."""
    policy = load_policy()
    allowed_actions = policy.get("allowed_actions")
    if policy.get("mode") != "release_enabled" or not isinstance(allowed_actions, list):
        raise EgressBlocked(f"Egress blockiert: {action} → {target} (internal_only).")
    if action not in allowed_actions:
        raise EgressBlocked(f"Egress blockiert: Aktion {action!r} ist nicht freigegeben.")


def scan_send_patterns(repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    """Find outbound-capable source patterns without executing any source code."""
    findings: list[dict[str, str]] = []
    tools_dir = repo_root / "tools"
    for source_path in sorted(tools_dir.rglob("*.py")):
        if source_path.name in {"egress_guard.py", "egress_audit.py"}:
            continue
        content = source_path.read_text(encoding="utf-8", errors="replace")
        relative_path = source_path.relative_to(repo_root).as_posix()
        for pattern_name, pattern in SEND_PATTERNS.items():
            if pattern.search(content):
                findings.append({"path": relative_path, "pattern": pattern_name})
    return findings


def load_egress_allowlist() -> list[dict[str, str]]:
    try:
        payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Egress-Allowlist ist nicht lesbar: {error}") from error
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("Egress-Allowlist benötigt ein entries-Array.")
    validated: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(key), str) and entry[key].strip()
            for key in ("path", "pattern", "reason")
        ):
            raise RuntimeError("Egress-Allowlist enthält einen ungültigen Eintrag.")
        validated.append(
            {
                "path": entry["path"],
                "pattern": entry["pattern"],
                "reason": entry["reason"],
            }
        )
    return validated


def unallowlisted_send_patterns(repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    allowlist = {(entry["path"], entry["pattern"]) for entry in load_egress_allowlist()}
    return [
        finding
        for finding in scan_send_patterns(repo_root)
        if (finding["path"], finding["pattern"]) not in allowlist
    ]


def active_n8n_workflow_violations(
    workflow_dir: Path = N8N_WORKFLOWS_DIR,
) -> list[str]:
    """Reject active workflows containing nodes beyond the internal test allowlist."""
    violations: list[str] = []
    for workflow_path in sorted(workflow_dir.glob("*.json")):
        try:
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            violations.append(f"{workflow_path.name}: nicht lesbar ({error})")
            continue
        if workflow.get("active") is not True:
            continue
        for node in workflow.get("nodes", []):
            node_type = node.get("type") if isinstance(node, dict) else None
            if node_type not in ACTIVE_N8N_NODE_ALLOWLIST:
                violations.append(
                    f"{workflow_path.name}: nicht erlaubter aktiver Node {node_type!r}"
                )
    return violations
