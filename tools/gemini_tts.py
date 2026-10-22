#!/usr/bin/env python3
"""
Generate speech using Gemini 3.8 Flash TTS / Flash-Lite TTS (Google, cloud API).

NOT local, NOT free — this is a cloud API call billed per Google's Gemini API
pricing, distinct from the fully local/offline tools (piper_tts.py, kokoro_tts.py).
There is a free tier (rate-limited; free-tier requests are used by Google to
improve its products, per Google's terms) — verify current rate limits and
pricing at https://ai.google.dev/gemini-api/docs/pricing before heavy use.

Quality is noticeably higher than Piper: natural prosody, emotional range via
the `style` annotation (e.g. "warm and friendly", "cheerful"), and 130+
languages (Flash) / 100+ (Flash-Lite) with automatic language detection.

Verified live 2026-09-26: German phrase "Guten Morgen zusammen, hier ist das
Testvideo." round-tripped through MLX Whisper at 92-99% word confidence,
matching or exceeding Piper's output quality.

Usage:
    python tools/gemini_tts.py --text "Hallo Welt" --output hallo.wav
    python tools/gemini_tts.py --text "Hallo Welt" --style "cheerful and friendly" --output out.wav
    python tools/gemini_tts.py --text "..." --model gemini-3.8-flash-tts --voice Puck --output out.wav
    python tools/gemini_tts.py --list-voices

Setup:
    Requires GEMINI_API_KEY in the environment (e.g. exported from ~/.secrets).
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

DEFAULT_MODEL = "gemini-3.8-flash-lite-tts"
DEFAULT_VOICE = "Kore"

# Prebuilt voices as documented at ai.google.dev/gemini-api/docs/speech-generation.
# Not an exhaustive list — the Extended Voice Library (GET /v1beta/voices) has more.
VOICES = {
    "Kore": "Warm, neutral (default)",
    "Puck": "Upbeat, energetic",
    "Zephyr": "Bright, breezy",
    "Charon": "Deep, calm",
    "Fenrir": "Bold, assertive",
    "Leda": "Soft, gentle",
    "Orus": "Firm, confident",
    "Aoede": "Melodic, expressive",
    "Callirrhoe": "Easygoing, casual",
    "Autonoe": "Clear, articulate",
}

MODELS = {
    "gemini-3.8-flash-tts": "Flagship — deep creative direction, character design, richest emotional range",
    "gemini-3.8-flash-lite-tts": "Fast, cost-efficient (default) — high-throughput production",
}

# The 5 primary production styles tested for Gemini 3.8 Flash TTS.
# Supports embedded inline expression tags: [laugh], [sigh], [breath], [whisper], [pause].
MODES = {
    "friendly": "warm, friendly, and approachable conversational tone",
    "narration": "clear, engaging documentary storytelling with measured pacing",
    "promote": "high-energy, persuasive commercial announcement style",
    "podcast": "natural, relaxed, dynamic podcast co-host delivery",
    "whisper": "soft, intimate, suspenseful whispering tone",
}


def _get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "Error: GEMINI_API_KEY not set in environment.\n"
            "\n"
            "Add it to ~/.secrets (chmod 600, sourced from ~/.zshrc):\n"
            "  export GEMINI_API_KEY=your_key_here\n"
            "\n"
            "Get a key at https://aistudio.google.com/apikey",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


def generate_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    style: str | None = None,
    mode: str | None = None,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
) -> dict:
    """Generate speech via Gemini TTS. Returns result dict."""
    if model not in MODELS:
        print(f"Warning: Unknown model '{model}', using '{DEFAULT_MODEL}'", file=sys.stderr)
        model = DEFAULT_MODEL

    if mode:
        mode_lower = mode.lower()
        if mode_lower in MODES:
            mode_desc = MODES[mode_lower]
            style = f"{mode_desc}. {style}" if style else mode_desc
        else:
            print(f"Warning: Unknown mode '{mode}', valid modes: {list(MODES.keys())}", file=sys.stderr)

    api_key = _get_api_key()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content_item = {"type": "text", "text": text}
    if style:
        content_item["annotations"] = [{"type": "speech_metadata", "style": style}]

    body = {
        "model": model,
        "input": [{"type": "user_input", "content": [content_item]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }

    if verbose:
        style_note = f", style={style!r}" if style else ""
        print(f"Gemini TTS ({model}, voice={voice}{style_note}): {len(text)} chars...", file=sys.stderr)

    start_time = time.time()
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"Gemini API error {e.code}: {e.read().decode('utf-8', 'replace')[:1000]}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Gemini API request failed: {e.reason}"}
    elapsed_ms = int((time.time() - start_time) * 1000)

    audio_b64 = None
    for step in payload.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for part in step.get("content", []):
            if part.get("type") == "audio" and part.get("data"):
                audio_b64 = part["data"]
    if not audio_b64:
        return {"success": False, "error": f"No audio in response: {json.dumps(payload)[:1000]}"}

    audio_bytes = base64.b64decode(audio_b64)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_wav = tmp.name

    try:
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

    usage = payload.get("usage", {})
    result = {
        "success": True,
        "output": str(output_path),
        "model": model,
        "voice": voice,
        "style": style,
        "inference_time_ms": elapsed_ms,
        "script_chars": len(text),
        "input_tokens": usage.get("total_input_tokens"),
        "output_tokens": usage.get("total_output_tokens"),
    }
    if duration:
        result["duration_seconds"] = round(duration, 2)
        result["duration_frames_30fps"] = int(duration * 30)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Generate speech using Gemini 3.8 Flash TTS (Google, cloud, low-cost)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/gemini_tts.py --text "Hallo Welt" --output hallo.wav
  python tools/gemini_tts.py --text "Hallo Welt" --mode narration --output out.wav
  python tools/gemini_tts.py --text "Das ist ja unglaublich! [laugh] Absolut genial." --mode friendly --output out.wav
  python tools/gemini_tts.py --text "..." --model gemini-3.8-flash-tts --voice Puck --output out.wav
  python tools/gemini_tts.py --list-voices
        """,
    )
    parser.add_argument("--text", "-t", type=str, help="Text to synthesize (supports tags: [laugh], [sigh], [breath], [whisper], [pause])")
    parser.add_argument("--output", "-o", type=str, help="Output audio file (.wav or .mp3)")
    parser.add_argument(
        "--voice", "-v", type=str, default=DEFAULT_VOICE,
        help=f"Voice name (default: {DEFAULT_VOICE}). Use --list-voices to see all.",
    )
    parser.add_argument(
        "--mode", "-m", type=str, choices=list(MODES.keys()),
        help=f"Production delivery preset: friendly, narration, promote, podcast, whisper",
    )
    parser.add_argument(
        "--style", type=str,
        help="Emotional/delivery style annotation, e.g. 'cheerful and friendly', 'calm and serious'",
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"gemini-3.8-flash-tts (best quality) or gemini-3.8-flash-lite-tts (default, cheaper)",
    )
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.list_voices:
        if args.json:
            print(json.dumps({"voices": VOICES, "models": MODELS}, indent=2))
        else:
            print("\nGemini TTS voices (cloud, low-cost — see --list-voices for pricing caveats):\n")
            for name, desc in VOICES.items():
                marker = " ← default" if name == DEFAULT_VOICE else ""
                print(f"  {name:<12} {desc}{marker}")
            print("\nModels:")
            for name, desc in MODELS.items():
                marker = " ← default" if name == DEFAULT_MODEL else ""
                print(f"  {name:<28} {desc}{marker}")
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
        style=args.style,
        mode=args.mode,
        model=args.model,
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
