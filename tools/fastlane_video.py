#!/usr/bin/env python3
"""
Fastlane Workspace Video Editor.

Executes direct workspace video processing without heavy NLE suites:
1. Silence/dead-air trimming via silence_cutter.py
2. Automated local transcription via transcribe.py (Apple Silicon MLX Whisper)
3. Subtitle rendering via local Remotion (subtitle_burn.py)

Usage:
    python tools/fastlane_video.py --input raw.mp4 --output final.mp4 --trim-silence
    python tools/fastlane_video.py --input raw.mp4 --output final.mp4 --trim-silence --burn-subtitles
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PYTHON_BIN = sys.executable
SILENCE_CUTTER = TOOLS_DIR / "silence_cutter.py"
TRANSCRIBE = TOOLS_DIR / "transcribe.py"
SUBTITLE_BURN = TOOLS_DIR / "subtitle_burn.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot Fastlane workspace video processing.")
    parser.add_argument("--input", "-i", required=True, type=Path, help="Input video file (.mp4, .mov)")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Output processed video file")
    parser.add_argument("--trim-silence", action="store_true", help="Remove dead air and silent pauses")
    parser.add_argument("--burn-subtitles", action="store_true", help="Generate and burn subtitles locally")
    parser.add_argument("--language", "-l", default="de", help="Language for transcription (default: de)")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Error: Input video '{args.input}' not found.")

    current_video = args.input.resolve()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Step 1: Trim silence if requested
        if args.trim_silence:
            print("▶ Trimming silent pauses...", file=sys.stderr)
            trimmed_file = tmp_path / "trimmed.mp4"
            cmd_cut = [
                PYTHON_BIN,
                str(SILENCE_CUTTER),
                "--input", str(current_video),
                "--output", str(trimmed_file),
            ]
            subprocess.run(cmd_cut, check=True)
            current_video = trimmed_file

        # Step 2: Burn subtitles if requested
        if args.burn_subtitles:
            print("▶ Transcribing audio with local Whisper...", file=sys.stderr)
            vtt_file = tmp_path / "subs.vtt"
            cmd_trans = [
                PYTHON_BIN,
                str(TRANSCRIBE),
                "--input", str(current_video),
                "--language", args.language,
                "--output", str(vtt_file),
            ]
            subprocess.run(cmd_trans, check=True)

            print("▶ Burning subtitles with local Remotion...", file=sys.stderr)
            subbed_file = tmp_path / "subbed.mp4"
            cmd_burn = [
                PYTHON_BIN,
                str(SUBTITLE_BURN),
                "--input", str(current_video),
                "--subtitles", str(vtt_file),
                "--output", str(subbed_file),
            ]
            subprocess.run(cmd_burn, check=True)
            current_video = subbed_file

        # Final move
        args.output.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(current_video, args.output)
        print(f"✓ Video ready: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
