#!/usr/bin/env python3
"""Shared base for publish adapters: validate a local package, then refuse to send.

send() always calls require_egress("publish", <platform>) before doing
anything else -- in this repo's internal_only mode that is an unconditional
EgressBlocked. No adapter module here imports a network library; that is
enforced by a static test over the AST, not just documented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.asset_record import sha256_file
from tools.egress_guard import require_egress


class PublishAdapterError(RuntimeError):
    """A release package could not be loaded for a publish adapter."""


class BasePublishAdapter:
    platform: str = "base"

    def __init__(self, package_dir: Path):
        self.package_dir = Path(package_dir)
        manifest_path = self.package_dir / "package-manifest.json"
        if not manifest_path.is_file():
            raise PublishAdapterError(f"Kein Release-Paket an diesem Pfad: {package_dir}")
        try:
            self.package: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise PublishAdapterError(f"package-manifest.json ist ungültig: {error}") from error

    def _media_path(self) -> Path | None:
        candidates = [
            path
            for path in self.package_dir.iterdir()
            if path.name not in ("package-manifest.json", "approval.json")
        ]
        return candidates[0] if len(candidates) == 1 else None

    def validate(self) -> list[str]:
        """Common checks every platform needs; subclasses extend, not replace."""
        findings: list[str] = []
        metadata = self.package.get("metadata") or {}
        if not str(metadata.get("title", "")).strip():
            findings.append("Titel fehlt.")
        if not str(metadata.get("alt_text", "")).strip():
            findings.append("alt_text fehlt.")

        media_path = self._media_path()
        if media_path is None or not media_path.is_file():
            findings.append("Mediendatei im Paket fehlt.")
        elif sha256_file(media_path) != self.package.get("sha256"):
            findings.append("SHA-256 der Paketdatei stimmt nicht mit dem Manifest überein.")

        approval_path = self.package_dir / "approval.json"
        if not approval_path.is_file():
            findings.append("Paket ist nicht freigegeben (release_package.py approve fehlt).")
        return findings

    def send(self) -> None:
        """Would publish; always blocked in internal_only. Never reached in this mode."""
        require_egress("publish", self.platform)
