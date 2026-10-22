#!/usr/bin/env python3
"""Burn SRT/VTT subtitles into a video with a local Remotion composition.

FFmpeg on this machine has no libass/subtitles filter (see AI_HANDOFF.md),
so burn-in goes through Remotion instead: parse cues -> build render props
(video path, cues in ms, a style block with the font embedded as a data
URI) -> render with the already-installed local Remotion CLI (no npx, no
network). The composition itself never fetches anything remote.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.transcribe import _parse_subtitle_timestamp, validate_subtitle_file
from tools.video_ingest import probe_media

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = REPO_ROOT / "tools" / "remotion" / "subtitle-burn" / "index.ts"
REMOTION_BIN = REPO_ROOT / "node_modules" / ".bin" / "remotion"
COMPOSITION_ID = "SubtitleBurn"


class SubtitleBurnError(RuntimeError):
    """Subtitles could not be parsed, rendered, or registered."""


def parse_subtitle_cues(path: Path) -> list[dict[str, object]]:
    """Parse a validated SRT/VTT file into {text, start, end} cues in seconds."""
    errors = validate_subtitle_file(path)
    if errors:
        raise SubtitleBurnError("Subtitle-QC fehlgeschlagen: " + "; ".join(errors))

    is_vtt = path.suffix.lower() == ".vtt"
    content = path.read_text(encoding="utf-8").removeprefix("﻿")
    if is_vtt:
        content = content.removeprefix("WEBVTT\n").lstrip("\n")
    separator = "." if is_vtt else ","
    blocks = [block for block in content.strip().split("\n\n") if block.strip()]

    cues: list[dict[str, object]] = []
    for block in blocks:
        lines = block.splitlines()
        timestamp_index = (0 if " --> " in lines[0] else 1) if is_vtt else 1
        timestamp_line = lines[timestamp_index]
        text_lines = lines[timestamp_index + 1 :]
        start_text, end_text = timestamp_line.split(" --> ", maxsplit=1)
        start = _parse_subtitle_timestamp(start_text, separator)
        end = _parse_subtitle_timestamp(end_text, separator)
        assert start is not None and end is not None  # validate_subtitle_file already proved this
        cues.append({"text": "\n".join(text_lines), "start": start, "end": end})
    return cues


def _font_data_uri(font_file: str | None) -> str | None:
    if not font_file:
        return None
    font_path = Path(font_file).expanduser()
    if not font_path.is_file():
        raise SubtitleBurnError(f"font_file nicht gefunden: {font_file}")
    mime, _ = mimetypes.guess_type(font_path.name)
    mime = mime or "font/ttf"
    return f"data:{mime};base64,{base64.b64encode(font_path.read_bytes()).decode('ascii')}"


def build_props(
    video: Path, cues: list[dict[str, object]], style: dict[str, Any]
) -> dict[str, Any]:
    """Build the Remotion render props: video framing, cues in ms, and a style block."""
    metadata = probe_media(video)
    fps = float(cast(float, metadata.get("fps") or 30))
    duration = float(cast(float, metadata["duration"]))
    width = int(cast(int, metadata["width"]))
    height = int(cast(int, metadata["height"]))
    return {
        "videoSrc": video.name,
        "videoFps": fps,
        "videoWidth": width,
        "videoHeight": height,
        "videoDurationInFrames": max(1, round(duration * fps)),
        "cues": [
            {
                "text": cue["text"],
                "startMs": round(float(cast(float, cue["start"])) * 1000),
                "endMs": round(float(cast(float, cue["end"])) * 1000),
            }
            for cue in cues
        ],
        "style": {
            "fontFamily": style.get("font_family", "Arial"),
            "fontDataUri": _font_data_uri(style.get("font_file")),
            "fontSizePx": style.get("size_px", 42),
            "color": style.get("color", "#ffffff"),
            "strokeColor": style.get("stroke_color", "#000000"),
            "strokeWidthPx": style.get("stroke_width_px", 2),
            "position": style.get("position", "bottom"),
            "offsetPx": style.get("offset_px", 64),
            "backgroundBox": style.get("background_box"),
            "safeArea": style.get("safe_area"),
        },
    }


def burn_in(
    video: Path,
    subtitles: Path,
    output: Path,
    *,
    style: dict[str, Any] | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Render subtitles burned into video via the local Remotion CLI. No egress."""
    if not REMOTION_BIN.is_file():
        raise SubtitleBurnError("Remotion-CLI fehlt lokal; keine Installation wird gestartet.")
    cues = parse_subtitle_cues(subtitles)
    if not cues:
        raise SubtitleBurnError("Subtitle-Datei enthält keine Cues.")
    props = build_props(video, cues, style or {})

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="subtitle-burn-") as work:
        public_dir = Path(work) / "public"
        public_dir.mkdir()
        shutil.copy2(video, public_dir / video.name)
        props_path = Path(work) / "props.json"
        props_path.write_text(json.dumps(props), encoding="utf-8")
        result = subprocess.run(
            [
                str(REMOTION_BIN),
                "render",
                str(ENTRY_POINT),
                COMPOSITION_ID,
                str(output),
                f"--props={props_path}",
                f"--public-dir={public_dir}",
                "--codec=h264",
                "--log=error",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    if result.returncode != 0 or not output.is_file():
        raise SubtitleBurnError(f"Remotion-Render fehlgeschlagen: {result.stderr[-4000:]}")
    return props


def register_burn_output(video: Path, subtitles: Path, output: Path) -> dict[str, Any]:
    """Register the output as a MASTER derived from the video and subtitle assets."""
    from tools import asset_record

    video_record = asset_record.register_asset(video)
    subtitle_record = asset_record.register_asset(subtitles)
    return asset_record.register_derived(
        output,
        parents=[str(video_record["asset_id"]), str(subtitle_record["asset_id"])],
        role="MASTER",
        tool="remotion",
        operation="subtitle_burn_in",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Burn SRT/VTT subtitles into a video (Remotion).")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--style", type=Path, help="Optional style JSON.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-register", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    style = json.loads(args.style.read_text(encoding="utf-8")) if args.style else {}
    try:
        burn_in(args.video, args.subtitles, args.output, style=style)
        if not args.no_register:
            record = register_burn_output(args.video, args.subtitles, args.output)
            print(json.dumps(record, ensure_ascii=False))
    except SubtitleBurnError as error:
        print(f"Subtitle-Burn: ERROR — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
