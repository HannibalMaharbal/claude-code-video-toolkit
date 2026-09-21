#!/usr/bin/env python3
"""E-commerce catalog publish adapter: validation only, no API client imported."""

from __future__ import annotations

from tools.publish_adapters.base import BasePublishAdapter

TITLE_MAX = 150
DESCRIPTION_MAX = 5000


class EcommerceAdapter(BasePublishAdapter):
    platform = "ecommerce"

    def validate(self) -> list[str]:
        findings = super().validate()
        metadata = self.package.get("metadata") or {}
        title = str(metadata.get("title", ""))
        if len(title) > TITLE_MAX:
            findings.append(f"Titel > {TITLE_MAX} Zeichen.")
        description = str(metadata.get("description", ""))
        if len(description) > DESCRIPTION_MAX:
            findings.append(f"Beschreibung > {DESCRIPTION_MAX} Zeichen.")
        return findings
