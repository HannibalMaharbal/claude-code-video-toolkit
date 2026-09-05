#!/usr/bin/env python3
"""
Generate speech using Kokoro TTS (local, Apple Silicon optimized).

Best open-source TTS. Runs locally — no API key, no cold start, no cloud cost.
First run downloads model files (~300MB, cached in ~/.cache/huggingface/).

Voices: American Female (af_*), American Male (am_*), British Female (bf_*), British Male (bm_*)

Usage:
    python tools/kokoro_tts.py --text "Hello world" --output hello.mp3
    python tools/kokoro_tts.py --text "Hello world" --voice af_heart --output hello.mp3
    python tools/kokoro_tts.py --text "Hello" --voice am_michael --speed 0.95 --output hello.mp3
    python tools/kokoro_tts.py --list-voices

Setup:
    pip install kokoro-onnx soundfile huggingface_hub
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VOICES = {
    "af_heart":    ("American Female", "warm, natural — best overall quality"),
    "af_alloy":    ("American Female", "clear, neutral"),
    "af_aoede":    ("American Female", "bright, expressive"),
    "af_bella":    ("American Female", "soft, friendly"),
    "af_jessica":  ("American Female", "professional, authoritative"),
    "af_kore":     ("American Female", "smooth, calm"),
    "af_nicole":   ("American Female", "conversational, energetic"),
    "af_nova":     ("American Female", "crisp, modern"),
    "af_river":    ("American Female", "relaxed, intimate"),
    "af_sarah":    ("American Female", "warm, trustworthy"),
    "af_sky":      ("American Female", "light, cheerful"),
    "am_adam":     ("American Male",   "deep, authoritative"),
    "am_echo":     ("American Male",   "smooth, engaging"),
    "am_eric":     ("American Male",   "clear, friendly"),
    "am_fenrir":   ("American Male",   "dramatic, powerful"),
    "am_liam":     ("American Male",   "casual, approachable"),
    "am_michael":  ("American Male",   "professional, measured — good for demos"),
    "am_onyx":     ("American Male",   "deep, resonant"),
    "am_puck":     ("American Male",   "energetic, playful"),
    "am_santa":    ("American Male",   "warm, cheerful"),
    "bf_alice":    ("British Female",  "refined, clear"),
    "bf_emma":     ("British Female",  "warm, natural"),
    "bf_isabella": ("British Female",  "elegant, expressive"),
    "bf_lily":     ("British Female",  "soft, gentle"),
    "bm_daniel":   ("British Male",    "authoritative, polished"),
    "bm_fable":    ("British Male",    "storytelling, warm"),
    "bm_george":   ("British Male",    "professional, trustworthy"),
    "bm_lewis":    ("British Male",    "clear, confident"),
}

DEFAULT_VOICE = "am_michael"
MODEL_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
CACHE_DIR = Path.home() / ".cache" / "kokoro-onnx"


def _lang(voice: str) -> str:
    """Derive lang code from voice prefix."""
    if voice.startswith(("bf_", "bm_")):
        return "en-gb"
    return "en-us"


def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress indication."""
    import urllib.request
    print(f"  Downloading {dest.name}...", file=sys.stderr)
    urllib.request.urlretrieve(url, dest)


def _get_model_paths() -> tuple[str, str]:
    """Download model files if needed and return (model_path, voices_path)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = CACHE_DIR / "kokoro-v1.0.onnx"
    voices_path = CACHE_DIR / "voices-v1.0.bin"

    if not model_path.exists():
        _download_file(f"{MODEL_BASE}/kokoro-v1.0.onnx", model_path)
    if not voices_path.exists():
        _download_file(f"{MODEL_BASE}/voices-v1.0.bin", voices_path)

    return str(model_path), str(voices_path)


def _get_kokoro(model_path: str, voices_path: str):
    """Load Kokoro ONNX pipeline."""
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        print(
            "Error: kokoro-onnx not installed.\n"
            "\n"
            "Install it:\n"
            "  pip install kokoro-onnx soundfile huggingface_hub\n"
            "\n"
            "First run downloads model files (~300MB, cached automatically).",
            file=sys.stderr,
        )
        sys.exit(1)

    from kokoro_onnx import Kokoro
    return Kokoro(model_path, voices_path)


def generate_audio(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    verbose: bool = True,
) -> dict:
    """Generate speech and save to MP3/WAV. Returns result dict."""
    try:
        import soundfile as sf
    except ImportError:
        print("Error: soundfile not installed. Run: pip install soundfile", file=sys.stderr)
        sys.exit(1)

    start_time = time.time()

    if voice not in VOICES:
        print(f"Warning: Unknown voice '{voice}', using '{DEFAULT_VOICE}'", file=sys.stderr)
        voice = DEFAULT_VOICE

    model_cached = (CACHE_DIR / "kokoro-v1.0.onnx").exists()

    if verbose:
        vtype, vdesc = VOICES[voice]
        print(f"Kokoro TTS: {voice} ({vdesc}), {len(text)} chars...", file=sys.stderr)
        if not model_cached:
            print("  (First run: downloading model files ~300MB...)", file=sys.stderr)

    model_path, voices_path = _get_model_paths()
    kokoro = _get_kokoro(model_path, voices_path)

    samples, sample_rate = kokoro.create(
        text,
        voice=voice,
        speed=speed,
        lang=_lang(voice),
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = tmp.name

    try:
        sf.write(tmp_wav, samples, sample_rate)

        if output_path.suffix.lower() == ".mp3":
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_wav, "-q:a", "2", str(output_path)],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                return {"success": False, "error": f"ffmpeg error: {proc.stderr}"}
        else:
            import shutil
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
        description="Generate speech using Kokoro TTS (local, Apple Silicon optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/kokoro_tts.py --text "Hello world" --output hello.mp3
  python tools/kokoro_tts.py --text "Hello" --voice am_michael --output hello.mp3
  python tools/kokoro_tts.py --text "Hello" --voice bm_george --speed 0.9 --output slow.mp3
  python tools/kokoro_tts.py --list-voices
        """,
    )
    parser.add_argument("--text", "-t", type=str, help="Text to synthesize")
    parser.add_argument("--output", "-o", type=str, help="Output audio file (.mp3 or .wav)")
    parser.add_argument(
        "--voice", "-v", type=str, default=DEFAULT_VOICE,
        help=f"Voice name (default: {DEFAULT_VOICE}). Use --list-voices to see all.",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="Speech speed multiplier (default: 1.0, range: 0.5–2.0)",
    )
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.list_voices:
        if args.json:
            print(json.dumps({"voices": [
                {"id": v, "type": info[0], "description": info[1],
                 "default": v == DEFAULT_VOICE}
                for v, info in VOICES.items()
            ]}, indent=2))
        else:
            print("\nKokoro TTS voices (local, no API key needed):\n")
            current_type = None
            for voice_id, (voice_type, desc) in VOICES.items():
                if voice_type != current_type:
                    print(f"  {voice_type}:")
                    current_type = voice_type
                marker = " ← default" if voice_id == DEFAULT_VOICE else ""
                print(f"    {voice_id:<16} {desc}{marker}")
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
