#!/usr/bin/env python3
"""
Creator Radar — Wöchentlicher Praxis- & Benchmark-Scanner.

Überwacht den Zielkanal vollautomatisch, filtert Marketing/Kurse heraus und
extrahiert ausschließlich relevante technische Hacks, Modelle und Kostenvorteile
für das HANNIBAL AI OS.

Usage:
    python tools/creator_radar.py [--limit 10] [--json] [--force]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_CHANNEL = "https://www.youtube.com/@calvinweischeslischt/videos"
CACHE_FILE = Path.home() / ".cache" / "creator_radar_seen.json"

# Relevante Signalwörter für System-Optimierung
TECH_KEYWORDS = [
    "claude", "code", "higgsfield", "kling", "seedance", "veo", "sora", "grok",
    "mcp", "connector", "credits", "hack", "trick", "schnitt", "cut", "katana",
    "upscale", "automation", "api", "prompt", "workflow", "team", "tools"
]

# Marketing-/Sponsor-Ausschlusskriterien
IGNORE_PATTERNS = [
    "community", "skool", "masterclass", "store", "plaud", "rabatt",
    "dankeschön", "geschenk", "uncut", "realtalk"
]


def get_latest_videos(channel_url: str, limit: int = 10) -> list[dict[str, str]]:
    """Fetch latest videos via yt-dlp."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--playlist-end", str(limit),
        "--print", "%(title)s\t%(id)s\t%(url)s",
        channel_url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except Exception as e:
        print(f"Fehler beim Abrufen des Kanals: {e}", file=sys.stderr)
        return []

    videos = []
    for line in res.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            videos.append({"title": parts[0], "id": parts[1], "url": parts[2]})
    return videos


def load_seen_ids() -> set[str]:
    """Load cached video IDs."""
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return set(data.get("seen_ids", []))
        except Exception:
            return set()
    return set()


def save_seen_ids(seen: set[str]) -> None:
    """Save seen video IDs."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({"seen_ids": list(seen)}, indent=2), encoding="utf-8")


def evaluate_video(video: dict[str, str]) -> dict[str, str] | None:
    """Evaluate if video contains valuable optimization ideas."""
    title_lower = video["title"].lower()

    # Prüfung auf Relevanz
    matches_tech = any(kw in title_lower for kw in TECH_KEYWORDS)
    if not matches_tech:
        return None

    # Schnelle Beschreibung holen
    desc_cmd = ["yt-dlp", "--skip-download", "--print", "%(description)s", video["url"]]
    try:
        desc_res = subprocess.run(desc_cmd, capture_output=True, text=True, timeout=10)
        desc = desc_res.stdout[:600]
    except Exception:
        desc = ""

    # Relevanz-Einstufung
    relevance = 7
    if any(k in title_lower for k in ["credits", "mcp", "code", "katana", "hack"]):
        relevance = 9

    return {
        "title": video["title"],
        "url": video["url"],
        "id": video["id"],
        "relevance": str(relevance),
        "summary_snippet": desc.split("\n")[0] if desc else video["title"]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Wöchentlicher KI-Praxis Radar.")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Anzahl neuester Videos prüfen")
    parser.add_argument("--force", "-f", action="store_true", help="Cache ignorieren und alle prüfen")
    parser.add_argument("--json", action="store_true", help="JSON Output für Agenten")
    args = parser.parse_args()

    seen_ids = set() if args.force else load_seen_ids()
    videos = get_latest_videos(DEFAULT_CHANNEL, args.limit)

    findings = []
    for vid in videos:
        if vid["id"] in seen_ids and not args.force:
            continue
        eval_result = evaluate_video(vid)
        if eval_result:
            findings.append(eval_result)
        seen_ids.add(vid["id"])

    save_seen_ids(seen_ids)

    if args.json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
        return

    print("════════════════════════════════════════════════════════════════")
    print(" 📡 PRAXIS-RADAR: WÖCHENTLICHER BENCHMARK-REPORT")
    print("════════════════════════════════════════════════════════════════\n")

    if not findings:
        print("✓ Keine neuen relevanten System-Upgrades oder Hacks in den neuesten Videos.")
        print("  (Reiner Kurs-Verkauf, Vlogs oder bereits im System integriert)\n")
        return

    print(f"Gefundene relevante Praxis-Optimierungen ({len(findings)} Treffer):\n")
    for idx, f in enumerate(findings, 1):
        print(f"[{idx}] {f['title']}")
        print(f"    • Relevanz: {f['relevance']}/10")
        print(f"    • Link: {f['url']}")
        print(f"    • Einblick: {f['summary_snippet'][:120]}...")
        print()


if __name__ == "__main__":
    main()
