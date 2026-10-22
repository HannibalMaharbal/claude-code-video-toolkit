#!/usr/bin/env python3
"""
Generate speech using Piper TTS (local, German, Apple Silicon friendly).

Local, offline German voiceover option — no API key, no cold start, no cloud
cost. Uses the Thorsten high-quality voice by default.

Usage:
    python tools/piper_tts.py --text "Hallo Welt" --output hallo.wav
    python tools/piper_tts.py --text "Hallo Welt" --speed 0.9 --output langsam.wav
    python tools/piper_tts.py --list-voices

Setup:
    Binary:  ~/.local/bin/piper (already installed, on PATH as `piper`)
    Voice:   ~/AI-Modelle/piper/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VOICES = {
    "thorsten": (
        "German Male",
        "Thorsten (high quality) — default local German voice",
        Path.home() / "PROJEKTE" / "AI-Modelle" / "piper" / "de" / "de_DE" / "thorsten" / "high"
        / "de_DE-thorsten-high.onnx",
    ),
}

DEFAULT_VOICE = "thorsten"


def _get_piper_bin() -> str:
    """Resolve the piper binary, erroring out with setup instructions if missing."""
    piper_bin = shutil.which("piper")
    if not piper_bin:
        print(
            "Error: piper binary not found on PATH.\n"
            "\n"
            "Expected at ~/.local/bin/piper. If it's installed elsewhere, add it to PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    return piper_bin


def generate_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    verbose: bool = True,
) -> dict:
    """Generate speech and save to WAV/MP3. Returns result dict.

    `speed` is a multiplier (>1 = faster), matching the convention used by
    kokoro_tts.py and voiceover.py. Piper's native `--length-scale` is the
    inverse (phoneme length, higher = slower), so it's converted internally.
    """
    start_time = time.time()

    if voice not in VOICES:
        print(f"Warning: Unknown voice '{voice}', using '{DEFAULT_VOICE}'", file=sys.stderr)
        voice = DEFAULT_VOICE

    _, vdesc, model_path = VOICES[voice]

    if not model_path.exists():
        return {
            "success": False,
            "error": f"Voice model not found: {model_path}",
        }

    piper_bin = _get_piper_bin()

    if verbose:
        print(f"Piper TTS: {voice} ({vdesc}), {len(text)} chars...", file=sys.stderr)

    length_scale = 1.0 / speed if speed > 0 else 1.0

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        proc = subprocess.run(
            [
                piper_bin,
                "-m", str(model_path),
                "-f", tmp_wav,
                "--length-scale", str(length_scale),
            ],
            input=text,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return {"success": False, "error": f"piper error: {proc.stderr.strip()}"}

        if output_path.suffix.lower() == ".mp3":
            ff = subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_wav, "-q:a", "2", str(output_path)],
                capture_output=True, text=True,
            )
            if ff.returncode != 0:
                return {"success": False, "error": f"ffmpeg error: {ff.stderr}"}
        else:
            shutil.copy(tmp_wav, str(output_path))
    finally:
        Path(tmp_wav).unlink(missing_ok=True)

    elapsed_ms = int((time.time() - start_time) * 1000)

    duration = None
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output_path)],
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            duration = float(probe.stdout.strip())
    except Exception:
        pass

    result = {
        "success": True,
        "output": str(output_path),
        "voice": voice,
        "speed": speed,
        "inference_time_ms": elapsed_ms,
        "script_chars": len(text),
    }
    if duration:
        result["duration_seconds"] = round(duration, 2)
        result["duration_frames_30fps"] = int(duration * 30)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate speech using Piper TTS (local, German)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/piper_tts.py --text "Hallo Welt" --output hallo.wav
  python tools/piper_tts.py --text "Hallo Welt" --speed 0.9 --output langsam.mp3
  python tools/piper_tts.py --list-voices
        """,
    )
    parser.add_argument("--text", "-t", type=str, help="Text to synthesize")
    parser.add_argument("--output", "-o", type=str, help="Output audio file (.wav or .mp3)")
    parser.add_argument(
        "--voice", "-v", type=str, default=DEFAULT_VOICE,
        help=f"Voice name (default: {DEFAULT_VOICE}). Use --list-voices to see all.",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="Speech speed multiplier (default: 1.0, range: 0.5-2.0)",
    )
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.list_voices:
        if args.json:
            print(json.dumps({"voices": [
                {"id": v, "type": info[0], "description": info[1],
                 "model_path": str(info[2]), "default": v == DEFAULT_VOICE}
                for v, info in VOICES.items()
            ]}, indent=2))
        else:
            print("\nPiper TTS voices (local, no API key needed):\n")
            for voice_id, (vtype, desc, model_path) in VOICES.items():
                marker = " ← default" if voice_id == DEFAULT_VOICE else ""
                present = "OK" if model_path.exists() else "MISSING"
                print(f"  {voice_id:<12} {desc}{marker}  [{present}]")
            print()
        return

    if not args.text:
        if not sys.stdin.isatty():
            args.text = sys.stdin.read().strip()
        else:
            print("Error: --text required (or pipe text via stdin)", file=sys.stderr)
            sys.exit(1)

    if not args.output:
        print("Error: --output required", file=sys.stderr)
        sys.exit(1)

    result = generate_audio(
        text=args.text,
        output_path=args.output,
        voice=args.voice,
        speed=args.speed,
        verbose=not args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            print(f"Saved: {args.output}", file=sys.stderr)
            if result.get("duration_seconds"):
                print(
                    f"Duration: {result['duration_seconds']:.2f}s "
                    f"({result['duration_frames_30fps']} frames @ 30fps)",
                    file=sys.stderr,
                )
        else:
            print(f"Error: {result.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
