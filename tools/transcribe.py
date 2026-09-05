#!/usr/bin/env python3
"""
Free audio/video transcription using mlx-whisper (Apple Silicon optimized).

Usage:
    python tools/transcribe.py --input video.mp4
    python tools/transcribe.py --input audio.mp3 --model large-v3
    python tools/transcribe.py --input video.mp4 --language de --output transcript.txt
    python tools/transcribe.py --input video.mp4 --json

Models (free, downloads on first use):
    tiny    — fastest, ~39M params
    base    — fast, ~74M params
    small   — balanced (default)
    medium  — high quality
    large-v3 — best quality, slower
"""

import argparse
import json
import sys
from pathlib import Path


def transcribe(input_path: str, model: str = "small", language: str | None = None,
               word_timestamps: bool = True, verbose: bool = True) -> dict | None:
    try:
        import mlx_whisper
    except ImportError:
        print("Error: mlx-whisper not installed. Run: pip install mlx-whisper", file=sys.stderr)
        return None

    if not Path(input_path).exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return None

    model_id = f"mlx-community/whisper-{model}-mlx"
    if verbose:
        print(f"Transcribing with {model_id}...", file=sys.stderr)

    try:
        result = mlx_whisper.transcribe(
            input_path,
            path_or_hf_repo=model_id,
            language=language,
            word_timestamps=word_timestamps,
            verbose=False,
        )
        return result
    except Exception as e:
        print(f"Transcription error: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Free transcription using mlx-whisper (Apple Silicon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input", "-i", required=True, help="Audio or video file")
    parser.add_argument("--model", "-m", default="small",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model (default: small)")
    parser.add_argument("--language", "-l", help="Language code (e.g. 'en', 'de'). Auto if not set.")
    parser.add_argument("--output", "-o", help="Save transcript to file")
    parser.add_argument("--words", action="store_true", default=True,
                        help="Include word-level timestamps (default: on)")
    parser.add_argument("--json", action="store_true", help="Output full JSON result")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    result = transcribe(
        args.input,
        model=args.model,
        language=args.language,
        word_timestamps=args.words,
        verbose=not args.quiet,
    )

    if not result:
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        text = result.get("text", "").strip()
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            if not args.quiet:
                print(f"Saved: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
