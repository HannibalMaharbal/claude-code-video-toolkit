#!/usr/bin/env python3
"""Parse orchestrator input: topic string, script file, or URL → structured script."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class InputType(StrEnum):
    TOPIC = "topic"
    SCRIPT = "script"
    URL = "url"


@dataclass
class ParsedInput:
    type: InputType
    raw: str  # original input
    title: str  # derived title for filename
    script: str  # markdown script text
    language: str = "de"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_like_url(s: str) -> bool:
    return re.match(r"^https?://", s.strip()) is not None


def _looks_like_file(s: str) -> bool:
    p = Path(s)
    return p.suffix in {".md", ".txt", ".rst"} and p.exists()


def _title_from_url(url: str) -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0]
    host = re.sub(r"^www\.", "", host)
    return host


def _title_from_topic(topic: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", topic).strip()
    slug = re.sub(r"\s+", "-", slug)
    return slug[:60]


# ---------------------------------------------------------------------------
# URL → script via Playwright scrape
# ---------------------------------------------------------------------------


def _scrape_url(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed: pip install playwright && playwright install chromium")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # grab meaningful text
        text = page.evaluate("""() => {
            const remove = ['script','style','nav','footer','header','aside','[role=banner]'];
            remove.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            return document.body.innerText;
        }""")
        browser.close()
    # trim whitespace runs
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text[:8000]  # cap to avoid huge context


def _url_to_script(url: str, duration: int, brand: str) -> str:
    """Scrape URL, then ask Claude to write a video script."""
    page_text = _scrape_url(url)
    prompt = _build_script_prompt(
        topic=f"Video über: {url}",
        context=page_text,
        duration=duration,
        brand=brand,
    )
    return _call_claude(prompt)


# ---------------------------------------------------------------------------
# Topic → script via Claude API
# ---------------------------------------------------------------------------


def _topic_to_script(topic: str, duration: int, brand: str) -> str:
    prompt = _build_script_prompt(topic=topic, context=None, duration=duration, brand=brand)
    return _call_claude(prompt)


def _build_script_prompt(topic: str, context: str | None, duration: int, brand: str) -> str:
    brand_hints = {
        "sac": (
            "Stil: dark, technisch, B2B, präzise. Farben: #0F1923, #4A90D9. Font: Barlow Condensed."
        ),
        "licbarska": (
            "Stil: premium, seriös, vertrauenswürdig. Farben: #0A1628 navy, "
            "#C9A96E gold. Font: Cormorant Garamond."
        ),
        "default": "Stil: clean, professionell.",
    }
    brand_hint = brand_hints.get(brand, brand_hints["default"])

    ctx_block = f"\n\nWebsite-Inhalt:\n{context}" if context else ""

    return f"""Schreibe ein Video-Script für ein ~{duration}s langes Marketing-Video.

Thema: {topic}
Brand: {brand} — {brand_hint}{ctx_block}

Format (Markdown):
---
# [Titel]

## Szene 1: title | [Kurztitel]
[Voiceover-Text]

## Szene 2: voiceover | [Kurztitel]
[Voiceover-Text]

## Szene N: cta | [Kurztitel]
[Call-to-Action-Text]
---

Szenen-Typen: title, voiceover, visual, code, cta
Sprache: Deutsch. Präzise. Kein Füllwort.
Ungefähr {duration // 15} Szenen.
"""


def _call_claude(prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic not installed: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(
    input_str: str,
    script_file: str | None = None,
    duration: int = 60,
    brand: str = "default",
    language: str = "de",
) -> ParsedInput:
    """Detect input type and return structured ParsedInput."""

    if script_file:
        path = Path(script_file)
        if not path.exists():
            sys.exit(f"Script file not found: {script_file}")
        script_text = path.read_text(encoding="utf-8")
        title = path.stem
        return ParsedInput(
            type=InputType.SCRIPT,
            raw=script_file,
            title=title,
            script=script_text,
            language=language,
        )

    if not input_str.strip():
        raise ValueError("input must not be empty")

    if _looks_like_file(input_str):
        path = Path(input_str)
        script_text = path.read_text(encoding="utf-8")
        return ParsedInput(
            type=InputType.SCRIPT,
            raw=input_str,
            title=path.stem,
            script=script_text,
            language=language,
        )

    if _looks_like_url(input_str):
        print("[input_parser] URL erkannt → scrape + script via Claude", flush=True)
        script_text = _url_to_script(input_str, duration=duration, brand=brand)
        return ParsedInput(
            type=InputType.URL,
            raw=input_str,
            title=_title_from_url(input_str),
            script=script_text,
            language=language,
        )

    # default: topic
    print("[input_parser] Thema erkannt → script via Claude", flush=True)
    script_text = _topic_to_script(input_str, duration=duration, brand=brand)
    return ParsedInput(
        type=InputType.TOPIC,
        raw=input_str,
        title=_title_from_topic(input_str),
        script=script_text,
        language=language,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse orchestrator input → structured script")
    ap.add_argument("input", nargs="?", help="Topic, URL, or script path")
    ap.add_argument("--script", help="Explicit script file path")
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--brand", default="default", choices=["default", "sac", "licbarska"])
    ap.add_argument("--language", default="de")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

    if not args.input and not args.script:
        ap.print_help()
        sys.exit(1)

    result = parse(
        input_str=args.input or "",
        script_file=args.script,
        duration=args.duration,
        brand=args.brand,
        language=args.language,
    )

    if args.json:
        d = asdict(result)
        d["type"] = result.type.value
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(f"Type:  {result.type.value}")
        print(f"Title: {result.title}")
        print(f"Script ({len(result.script)} chars):")
        print(result.script)


if __name__ == "__main__":
    main()
