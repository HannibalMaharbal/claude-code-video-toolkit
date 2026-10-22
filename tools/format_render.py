#!/usr/bin/env python3
"""Render a clean video master plus a format-adaptive scene layout locally."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.format_layout import FormatLayoutError, resolve_scene_file
from tools.video_ingest import probe_media

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = REPO_ROOT / "tools" / "remotion" / "format-adaptive" / "index.ts"
REMOTION_BIN = REPO_ROOT / "node_modules" / ".bin" / "remotion"
COMPOSITION_ID = "FormatAdaptive"


class FormatRenderError(RuntimeError):
    pass


def render(
    video: Path, scene_layout: Path, profile_name: str, output: Path, *, timeout: int = 300
) -> dict[str, Any]:
    if not REMOTION_BIN.is_file():
        raise FormatRenderError("Remotion-CLI fehlt lokal; es wird nichts installiert.")
    if not video.is_file():
        raise FormatRenderError(f"Video nicht gefunden: {video}")
    resolved = resolve_scene_file(scene_layout, profile_name)
    if resolved["issues"]:
        raise FormatRenderError("Layout-QC fehlgeschlagen: " + "; ".join(resolved["issues"]))
    metadata = probe_media(video)
    fps = float(cast(float, metadata.get("fps") or 30))
    duration = float(cast(float, metadata["duration"]))
    props = {
        "videoSrc": video.name,
        "videoFps": fps,
        "videoWidth": resolved["width"],
        "videoHeight": resolved["height"],
        "videoDurationInFrames": max(1, round(duration * fps)),
        "elements": resolved["elements"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="format-adaptive-") as work_dir:
        work = Path(work_dir)
        public_dir = work / "public"
        public_dir.mkdir()
        shutil.copy2(video, public_dir / video.name)
        props_path = work / "props.json"
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
        raise FormatRenderError(f"Remotion-Render fehlgeschlagen: {result.stderr[-4000:]}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Render format-adaptive scene text locally.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--scene-layout", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = render(args.video, args.scene_layout, args.profile, args.output)
    except (FormatLayoutError, FormatRenderError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
