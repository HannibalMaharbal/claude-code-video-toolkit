#!/usr/bin/env python3
"""Facebook publish adapter: validation only, no API client imported or called."""

from __future__ import annotations

from tools.publish_adapters.base import BasePublishAdapter

DESCRIPTION_MAX = 63206


class FacebookAdapter(BasePublishAdapter):
    platform = "facebook"

    def validate(self) -> list[str]:
        findings = super().validate()
        metadata = self.package.get("metadata") or {}
        description = str(metadata.get("description", ""))
        if len(description) > DESCRIPTION_MAX:
            findings.append(f"Beschreibung > {DESCRIPTION_MAX} Zeichen.")
        return findings
