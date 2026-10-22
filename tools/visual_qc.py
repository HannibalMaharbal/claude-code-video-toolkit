#!/usr/bin/env python3
"""Objective local visual checks; semantic judgement remains separate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.format_layout import resolve_scene_file
from tools.transcribe import validate_subtitle_file
from tools.video_ingest import probe_media


def _filter_events(path: Path, filter_name: str) -> str:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            filter_name,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.stderr


def check(
    video: Path,
    profile: dict[str, Any],
    *,
    scene_layout: Path | None = None,
    subtitles: Path | None = None,
) -> list[dict[str, str]]:
    metadata = probe_media(video)
    expected = profile["resolution"]
    checks: list[dict[str, str]] = [
        {
            "name": "frame",
            "status": "pass"
            if (metadata.get("width"), metadata.get("height"))
            == (expected["width"], expected["height"])
            else "fail",
            "evidence": f"{metadata.get('width')}x{metadata.get('height')}",
        }
    ]
    black = _filter_events(video, "blackdetect=d=0.5:pix_th=0.10")
    checks.append(
        {
            "name": "black_frames",
            "status": "fail" if "black_start:" in black else "pass",
            "evidence": "blackdetect",
        }
    )
    frozen = _filter_events(video, "freezedetect=n=0.003:d=3")
    checks.append(
        {
            "name": "freeze_frames",
            "status": "fail" if "freeze_start:" in frozen else "pass",
            "evidence": "freezedetect",
        }
    )
    if scene_layout is None:
        checks.append(
            {
                "name": "text_safe_area",
                "status": "not_run",
                "evidence": "Kein formatadaptives Scene-Layout.",
            }
        )
    else:
        resolved = (
            resolve_scene_file(scene_layout, str(profile.get("name", "")))
            if profile.get("name")
            else None
        )
        issues = resolved["issues"] if resolved else ["Profilname fehlt"]
        checks.append(
            {
                "name": "text_safe_area",
                "status": "fail" if issues else "pass",
                "evidence": "; ".join(issues) or "Text innerhalb Frame und Safe Area.",
            }
        )
    if subtitles is None:
        checks.append(
            {
                "name": "subtitle_layout",
                "status": "not_run",
                "evidence": "Keine Untertitelquelle.",
            }
        )
    else:
        subtitle_errors = validate_subtitle_file(subtitles)
        checks.append(
            {
                "name": "subtitle_layout",
                "status": "fail" if subtitle_errors else "pass",
                "evidence": "; ".join(subtitle_errors) if subtitle_errors else "Untertitel strukturell valide.",
            }
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic local visual QC.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--scene-layout", type=Path)
    parser.add_argument("--subtitles", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from tools.platform_profiles import get_profile

    profile = {**get_profile(args.profile), "name": args.profile}
    result = check(args.video, profile, scene_layout=args.scene_layout, subtitles=args.subtitles)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
