#!/usr/bin/env python3
"""Instagram publish adapter: validation only, no API client imported or called."""

from __future__ import annotations

from tools.publish_adapters.base import BasePublishAdapter

CAPTION_MAX = 2200
HASHTAG_MAX = 30


class InstagramAdapter(BasePublishAdapter):
    platform = "instagram"

    def validate(self) -> list[str]:
        findings = super().validate()
        metadata = self.package.get("metadata") or {}
        description = str(metadata.get("description", ""))
        if len(description) > CAPTION_MAX:
            findings.append(f"Caption > {CAPTION_MAX} Zeichen.")
        hashtags = metadata.get("hashtags") or []
        if len(hashtags) > HASHTAG_MAX:
            findings.append(f"Mehr als {HASHTAG_MAX} Hashtags.")
        return findings
