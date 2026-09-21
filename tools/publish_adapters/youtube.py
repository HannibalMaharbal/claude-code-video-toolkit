#!/usr/bin/env python3
"""YouTube publish adapter: validation only, mirrors tools/youtube_upload.py's own
limits without importing that module -- it unconditionally imports the Google API
client libraries at module level and calls sys.exit(1) if they're missing, which
validate-only use here must never trigger.
"""

from __future__ import annotations

from tools.publish_adapters.base import BasePublishAdapter

TITLE_MAX = 100
DESCRIPTION_MAX = 5000
TAGS_COMBINED_MAX = 500


class YoutubeAdapter(BasePublishAdapter):
    platform = "youtube"

    def validate(self) -> list[str]:
        findings = super().validate()
        metadata = self.package.get("metadata") or {}
        title = str(metadata.get("title", ""))
        if len(title) > TITLE_MAX:
            findings.append(f"Titel > {TITLE_MAX} Zeichen.")
        description = str(metadata.get("description", ""))
        if len(description) > DESCRIPTION_MAX:
            findings.append(f"Beschreibung > {DESCRIPTION_MAX} Zeichen.")
        hashtags = metadata.get("hashtags") or []
        combined = sum(len(tag) for tag in hashtags)
        if combined > TAGS_COMBINED_MAX:
            findings.append(f"Hashtags kombiniert > {TAGS_COMBINED_MAX} Zeichen.")
        return findings
