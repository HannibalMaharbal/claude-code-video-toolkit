#!/usr/bin/env python3
"""Split a markdown video script into structured scenes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class SceneType(StrEnum):
    TITLE = "title"
    VOICEOVER = "voiceover"
    CODE = "code"
    VISUAL = "visual"
    CTA = "cta"


SCENE_TYPE_ALIASES = {
    "titel": SceneType.TITLE,
    "title": SceneType.TITLE,
    "intro": SceneType.TITLE,
    "voiceover": SceneType.VOICEOVER,
    "narration": SceneType.VOICEOVER,
    "sprache": SceneType.VOICEOVER,
    "code": SceneType.CODE,
    "terminal": SceneType.CODE,
    "demo": SceneType.CODE,
    "visual": SceneType.VISUAL,
    "bild": SceneType.VISUAL,
    "szene": SceneType.VISUAL,
    "cta": SceneType.CTA,
    "outro": SceneType.CTA,
    "abschluss": SceneType.CTA,
}

# Estimated seconds per scene type (base duration if no voiceover length known)
DEFAULT_DURATION: dict[SceneType, int] = {
    SceneType.TITLE: 4,
    SceneType.VOICEOVER: 12,
    SceneType.CODE: 15,
    SceneType.VISUAL: 8,
    SceneType.CTA: 6,
}

WORDS_PER_SECOND = 2.5  # standard narration pace
MAX_SCENE_DURATION = 30.0


@dataclass
class Scene:
    index: int
    type: SceneType
    title: str
    text: str  # voiceover / display text
    duration_s: float  # estimated seconds
    brand: str = "default"
    has_code: bool = False
    code_block: str | None = None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SCENE_RE = re.compile(
    r"^##\s+Szene\s+\d+\s*:\s*(\w+)\s*\|\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


def _estimate_duration(text: str, scene_type: SceneType) -> float:
    """Estimate scene duration from word count."""
    word_count = len(text.split())
    if word_count < 5:
        return float(DEFAULT_DURATION[scene_type])
    return min(round(word_count / WORDS_PER_SECOND, 1), MAX_SCENE_DURATION)


def _extract_code(text: str) -> tuple[str, str | None]:
    """Strip fenced code blocks from text, return (clean_text, code_block)."""
    code_match = re.search(r"```[\w]*\n(.*?)```", text, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()
        clean = re.sub(r"```[\w]*\n.*?```", "", text, flags=re.DOTALL).strip()
        return clean, code
    return text, None


def split(script: str, brand: str = "default") -> list[Scene]:
    """Parse markdown script into Scene list."""
    if not script.strip():
        raise ValueError("script must not be empty")

    matches = list(_SCENE_RE.finditer(script))
    if not matches:
        # No structured scenes → treat entire script as single voiceover
        return [
            Scene(
                index=0,
                type=SceneType.VOICEOVER,
                title="Main",
                text=script.strip(),
                duration_s=_estimate_duration(script, SceneType.VOICEOVER),
                brand=brand,
            )
        ]

    scenes: list[Scene] = []
    for i, match in enumerate(matches):
        raw_type = match.group(1).lower()
        scene_title = match.group(2).strip()
        scene_type = SCENE_TYPE_ALIASES.get(raw_type, SceneType.VOICEOVER)

        # Text = everything between this heading and next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(script)
        raw_text = script[start:end].strip()

        clean_text, code_block = _extract_code(raw_text)

        scenes.append(
            Scene(
                index=i,
                type=scene_type,
                title=scene_title,
                text=clean_text,
                duration_s=_estimate_duration(clean_text, scene_type),
                brand=brand,
                has_code=code_block is not None,
                code_block=code_block,
            )
        )

    return scenes


def total_duration(scenes: list[Scene]) -> float:
    return sum(s.duration_s for s in scenes)


def to_dict(scenes: list[Scene]) -> list[dict]:
    result = []
    for s in scenes:
        d = asdict(s)
        d["type"] = s.type.value
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Split video script into scenes")
    ap.add_argument("script", nargs="?", help="Script file (.md) or - for stdin")
    ap.add_argument("--brand", default="default", choices=["default", "sac", "licbarska"])
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    if args.script and args.script != "-":
        text = Path(args.script).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.print_help()
        sys.exit(1)

    scenes = split(text, brand=args.brand)

    if args.json:
        print(json.dumps(to_dict(scenes), ensure_ascii=False, indent=2))
    else:
        print(f"Szenen: {len(scenes)} | Gesamt: {total_duration(scenes):.1f}s")
        for s in scenes:
            code_flag = " [code]" if s.has_code else ""
            summary = (
                f"  [{s.index}] {s.type.value:<10} | {s.title:<30} | "
                f"{s.duration_s:5.1f}s{code_flag}"
            )
            print(summary)


if __name__ == "__main__":
    main()
