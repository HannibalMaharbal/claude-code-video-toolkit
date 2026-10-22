#!/usr/bin/env python3
"""Mix a locally supplied music file into a video with FFmpeg; no generation/API."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--music", "-m", type=Path, required=True, help="Existing local audio file")
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--original-volume", type=float, default=1.0)
    parser.add_argument("--music-volume", type=float, default=0.15)
    parser.add_argument("--fade-in", type=float, default=0.0)
    parser.add_argument("--fade-out", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.input.is_file() or not args.music.is_file():
        parser.error("--input und --music müssen lokale Dateien sein")
    if args.output.resolve() in (args.input.resolve(), args.music.resolve()):
        parser.error("--output muss eine neue Datei sein")
    if any(not 0 <= value <= 1 for value in (args.original_volume, args.music_volume)):
        parser.error("Lautstärken müssen zwischen 0 und 1 liegen")
    if args.fade_in < 0 or args.fade_out < 0:
        parser.error("Fade-Zeiten dürfen nicht negativ sein")

    try:
        duration = _duration(args.input)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Video-Dauer konnte nicht gelesen werden: {error}", file=sys.stderr)
        return 1

    if args.dry_run:
        result = {"dry_run": True, "input": str(args.input), "music": str(args.music),
                  "output": str(args.output), "duration_seconds": duration,
                  "local_only": True}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    music_filters = [f"volume={args.music_volume}"]
    if args.fade_in:
        music_filters.append(f"afade=t=in:d={args.fade_in}")
    if args.fade_out:
        music_filters.append(f"afade=t=out:st={max(0, duration-args.fade_out)}:d={args.fade_out}")
    graph = (
        f"[0:a]volume={args.original_volume}[original];"
        f"[1:a]{','.join(music_filters)}[music];"
        "[original][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(args.input),
         "-i", str(args.music), "-filter_complex", graph, "-map", "0:v:0", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(args.output)],
        capture_output=True, text=True,
    )
    if result.returncode:
        print(result.stderr.strip(), file=sys.stderr)
        return 1
    report = {"success": True, "input": str(args.input), "music": str(args.music),
              "output": str(args.output), "local_only": True}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
