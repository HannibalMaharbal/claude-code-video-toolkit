#!/usr/bin/env python3
"""
Generate voiceover audio using local TTS providers.

Usage:
    # From script file (local default provider)
    python tools/voiceover.py --script VOICEOVER-SCRIPT.md --output public/audio/voiceover.mp3

    # From stdin (for AI piping)
    echo "Hello world" | python tools/voiceover.py --output voiceover.mp3

    # JSON output for machine parsing
    python tools/voiceover.py --script script.txt --output out.mp3 --json

    # Per-scene generation (recommended)
    python tools/voiceover.py --scene-dir public/audio/scenes --json

    # With concat for SadTalker narrator
    python tools/voiceover.py --scene-dir public/audio/scenes --concat public/audio/voiceover-concat.mp3

    # Using Piper (local, German)
    python tools/voiceover.py --provider piper --scene-dir public/audio/scenes --json
    python tools/voiceover.py --provider piper --piper-speed 0.9 --script script.txt \\
        --output out.mp3

"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add parent to path for local imports
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    get_brand_dir,
    get_default_voice_provider,
    get_sixtydb_api_key,
    get_sixtydb_voice_id,
    load_brand_voice_config,
)


def parse_args():
    default_provider = get_default_voice_provider()
    parser = argparse.ArgumentParser(
        description="Generate voiceover using local TTS providers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local default provider
  python tools/voiceover.py --script VOICEOVER-SCRIPT.md --output public/audio/voiceover.mp3
  python tools/voiceover.py --scene-dir public/audio/scenes --json

  # Consent-gated local cloned voice: use tools/local_voice.py
        """,
    )
    parser.add_argument(
        "--script",
        "-s",
        type=str,
        help="Path to script file (reads from stdin if not provided)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output audio file path (.mp3). Required for single-file mode.",
    )
    parser.add_argument(
        "--scene-dir",
        type=str,
        help="Directory of .txt scripts to process (per-scene mode). Each .txt generates a .mp3.",
    )
    parser.add_argument(
        "--concat",
        type=str,
        help="Output path for concatenated audio (use with --scene-dir for SadTalker)",
    )

    # Provider selection
    parser.add_argument(
        "--provider",
        type=str,
        default=default_provider,
        choices=["kokoro", "piper", "qwen3-local", "azure"],
        help=f"TTS provider (default: {default_provider}); Azure Arabic requires --confirm-cloud",
    )

    # Legacy-compatible voice parameters (not connected to a cloud provider)
    parser.add_argument(
        "--voice-id",
        "-v",
        type=str,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="local",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--stability",
        type=float,
        default=0.85,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.95,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--style",
        type=float,
        default=0.0,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speech speed multiplier (default: 1.0)",
    )

    # 60db-specific options (stability/similarity/speed are shared, on the 0-1 scale)
    parser.add_argument(
        "--transport",
        type=str,
        default="synthesize",
        choices=["synthesize", "stream", "websocket"],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-enhance",
        dest="enhance",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.set_defaults(enhance=True)

    # Qwen3-TTS-specific options
    parser.add_argument(
        "--speaker",
        type=str,
        default="Ryan",
        help="Qwen3-TTS speaker name (default: Ryan). Use 'python tools/qwen3_tts.py --list-voices' to see options.",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="Auto",
        help="Qwen3-TTS language hint (default: Auto)",
    )
    parser.add_argument(
        "--instruct",
        type=str,
        default="",
        help="Qwen3-TTS emotion/style instruction (e.g., 'Speak warmly'). Overrides --tone.",
    )
    parser.add_argument(
        "--tone",
        type=str,
        default="professional",
        help="Qwen3-TTS tone preset (default: professional). See 'python tools/qwen3_tts.py --list-tones'.",
    )
    parser.add_argument(
        "--ref-audio",
        type=str,
        help="Qwen3-TTS reference audio file for voice cloning",
    )
    parser.add_argument(
        "--ref-text",
        type=str,
        help="Exact transcript of the local voice reference (required with --ref-audio)",
    )
    parser.add_argument(
        "--consent-confirmed",
        action="store_true",
        help="Confirm that you own or have explicit permission to clone the reference voice",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Qwen3-TTS expressiveness (default: model default ~0.7, range: 0.3-1.5)",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        help="Qwen3-TTS nucleus sampling (default: model default ~0.8, range: 0.1-1.0)",
    )

    # Kokoro-specific options
    parser.add_argument(
        "--voice",
        type=str,
        default="am_michael",
        help="Kokoro TTS voice (default: am_michael). Use 'python tools/kokoro_tts.py --list-voices' to see all 28 voices.",
    )

    # Piper-specific options
    parser.add_argument(
        "--piper-voice",
        type=str,
        default="thorsten",
        help="Piper TTS voice (default: thorsten). "
        "Use 'python tools/piper_tts.py --list-voices' to see all.",
    )
    parser.add_argument(
        "--piper-speed",
        type=float,
        default=1.0,
        help="Piper speech speed multiplier (default: 1.0, range: 0.5-2.0)",
    )

    # Gemini TTS-specific options
    parser.add_argument(
        "--gemini-voice",
        type=str,
        default="Kore",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--gemini-style",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default="gemini-3.8-flash-lite-tts",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--azure-locale",
        choices=["ar-TN", "ar-DZ", "ar-MA", "ar-LB", "ar-SY", "ar-EG", "ar-msa"],
        default="ar-TN",
        help="Azure Arabic variety (ar-msa uses a Saudi voice because Azure has no MSA locale)",
    )
    parser.add_argument(
        "--azure-gender",
        choices=["female", "male"],
        default="female",
        help="Azure Arabic voice gender (default: female)",
    )
    parser.add_argument(
        "--confirm-cloud",
        action="store_true",
        help="Confirm sending script text to Azure; usage beyond the free quota may be billed",
    )

    # Cloud GPU provider (for Qwen3-TTS)
    parser.add_argument(
        "--cloud",
        type=str,
        default="modal",
        choices=["runpod", "modal"],
        help=argparse.SUPPRESS,
    )

    # Brand integration
    parser.add_argument(
        "--brand",
        type=str,
        help="Brand name to load voice config from (e.g., 'default', 'digital-samba')",
    )

    # Common options
    parser.add_argument(
        "--max-wpm",
        type=float,
        default=None,
        help="Pace clamp (any provider): takes exceeding this words-per-minute "
             "are slowed with pitch-preserving atempo (floor 0.85x). Try 165. "
             "Results always include wpm + a pacing label for QC.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (for machine parsing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making API calls",
    )
    return parser.parse_args()


def read_script(script_path: str | None) -> str:
    """Read script from file or stdin."""
    if script_path:
        with open(script_path) as f:
            return f.read().strip()
    else:
        if sys.stdin.isatty():
            print("Reading script from stdin (Ctrl+D to end):", file=sys.stderr)
        return sys.stdin.read().strip()


def get_audio_duration(file_path: str) -> float | None:
    """Get audio duration using ffprobe if available."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        pass
    return None


def _apply_pacing_qc(result: dict, script: str, max_wpm: float | None) -> None:
    """Add wpm/pacing fields to a result; clamp pace in place if max_wpm set.

    Provider-agnostic. Qwen3-TTS applies its own pacing QC inside
    qwen3_tts.generate_audio(), so callers pass max_wpm straight through
    there instead of calling this.
    """
    from pacing import clamp_pace, pace_label

    if not result.get("success") or not result.get("output"):
        return
    if max_wpm:
        clamp = clamp_pace(result["output"], script, max_wpm, verbose=False)
        if clamp.get("applied"):
            new_dur = clamp["duration_seconds"]
            result["duration_seconds"] = new_dur
            result["duration_frames_30fps"] = int(new_dur * 30) if new_dur else None
            result["pace_adjusted"] = {
                "original_wpm": clamp["original_wpm"],
                "atempo": clamp["atempo"],
            }
    wpm, label = pace_label(script, result.get("duration_seconds"))
    result["wpm"] = wpm
    result["pacing"] = label


def _pace_note(result: dict) -> str:
    """Human-mode pacing annotation for a per-scene / single-file result line."""
    wpm = result.get("wpm")
    if not wpm:
        return ""
    note = f", {wpm:.0f} wpm"
    if result.get("pace_adjusted"):
        note += f" [clamped from {result['pace_adjusted']['original_wpm']:.0f}]"
    elif result.get("pacing") in ("fast", "slow"):
        note += f" [{result['pacing'].upper()} — try --max-wpm 165]"
    return note


def generate_single_audio_60db(
    script: str,
    output_path: Path,
    voice_id: str | None,
    stability: float,
    similarity: float,
    speed: float,
    enhance: bool,
    transport: str,
    api_key: str | None,
    max_wpm: float | None = None,
) -> dict:
    """Generate a single audio file from script text using 60db. Returns result dict.

    stability/similarity are passed on the unified 0-1 scale and converted to
    60db's native 0-100 inside sixtydb_tts.generate_audio().
    """
    from sixtydb_tts import generate_audio

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = generate_audio(
        text=script,
        output_path=str(output_path),
        voice_id=voice_id,
        stability=stability,
        similarity=similarity,
        speed=speed,
        enhance=enhance,
        transport=transport,
        api_key=api_key,
        verbose=False,
    )
    _apply_pacing_qc(result, script, max_wpm)
    return result


def generate_single_audio_qwen3(
    script: str,
    output_path: Path,
    speaker: str = "Ryan",
    language: str = "Auto",
    instruct: str = "",
    ref_audio: str | None = None,
    ref_text: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    cloud: str = "runpod",
    max_wpm: float | None = None,
) -> dict:
    """Generate a single audio file from script text using Qwen3-TTS. Returns result dict.

    Qwen3-TTS runs its own pacing QC inside qwen3_tts.generate_audio(), so
    max_wpm is passed straight through rather than via _apply_pacing_qc().
    """
    from qwen3_tts import generate_audio

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return generate_audio(
        text=script,
        output_path=str(output_path),
        speaker=speaker,
        language=language,
        instruct=instruct,
        ref_audio=ref_audio,
        ref_text=ref_text,
        verbose=False,
        temperature=temperature,
        top_p=top_p,
        cloud=cloud,
        max_wpm=max_wpm,
    )


def generate_single_audio_kokoro(
    script: str,
    output_path: Path,
    voice: str = "am_michael",
    speed: float = 1.0,
    max_wpm: float | None = None,
) -> dict:
    """Generate a single audio file from script text using Kokoro TTS. Returns result dict."""
    from kokoro_tts import generate_audio

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = generate_audio(
        text=script,
        output_path=str(output_path),
        voice=voice,
        speed=speed,
        verbose=False,
    )
    _apply_pacing_qc(result, script, max_wpm)
    return result


def generate_single_audio_piper(
    script: str,
    output_path: Path,
    voice: str = "thorsten",
    speed: float = 1.0,
    max_wpm: float | None = None,
) -> dict:
    """Generate a single audio file from script text using Piper TTS. Returns result dict."""
    from piper_tts import generate_audio

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = generate_audio(
        text=script,
        output_path=str(output_path),
        voice=voice,
        speed=speed,
        verbose=False,
    )
    _apply_pacing_qc(result, script, max_wpm)
    return result


def generate_single_audio_qwen3_local(
    script: str,
    output_path: Path,
    ref_audio: str,
    ref_text: str,
    language: str,
    consent_confirmed: bool,
) -> dict:
    """Generate a consent-gated cloned voice entirely on the local MLX runtime."""
    from local_voice import generate_audio

    return generate_audio(
        text=script,
        output_path=output_path,
        ref_audio=ref_audio,
        ref_text=ref_text,
        language=language,
        consent_confirmed=consent_confirmed,
    )


def generate_single_audio_gemini(
    script: str,
    output_path: Path,
    voice: str = "Kore",
    style: str | None = None,
    model: str = "gemini-3.8-flash-lite-tts",
    max_wpm: float | None = None,
) -> dict:
    """Generate a single audio file from script text using Gemini TTS. Returns result dict."""
    from gemini_tts import generate_audio

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = generate_audio(
        text=script,
        output_path=str(output_path),
        voice=voice,
        style=style,
        model=model,
        verbose=False,
    )
    _apply_pacing_qc(result, script, max_wpm)
    return result


def generate_single_audio_azure(
    script: str,
    output_path: Path,
    locale: str = "ar-TN",
    gender: str = "female",
    max_wpm: float | None = None,
) -> dict:
    """Generate Arabic speech using an explicitly selected Azure Speech voice."""
    from azure_tts import generate_audio

    result = generate_audio(
        text=script,
        output_path=output_path,
        locale=locale,
        gender=gender,
    )
    if result.get("success"):
        _apply_pacing_qc(result, script, max_wpm)
    return result


def process_scene_directory(
    scene_dir: Path,
    dry_run: bool = False,
    json_output: bool = False,
    # Provider
    provider: str = "kokoro",
    # Shared/legacy parameter slots retained for the existing local providers.
    client=None,
    voice_id: str = "",
    model: str = "local",
    stability: float = 0.85,
    similarity: float = 0.95,
    style: float = 0.0,
    speed: float = 1.0,
    # 60db params
    enhance: bool = True,
    transport: str = "synthesize",
    sixtydb_api_key: str | None = None,
    # Qwen3 params
    speaker: str = "Ryan",
    language: str = "Auto",
    instruct: str = "",
    ref_audio: str | None = None,
    ref_text: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    cloud: str = "runpod",
    # Kokoro params
    voice: str = "am_michael",
    kokoro_speed: float = 1.0,
    # Piper params
    piper_voice: str = "thorsten",
    piper_speed: float = 1.0,
    consent_confirmed: bool = False,
    # Gemini params
    gemini_voice: str = "Kore",
    gemini_style: str | None = None,
    gemini_model: str = "gemini-3.8-flash-lite-tts",
    azure_locale: str = "ar-TN",
    azure_gender: str = "female",
    confirm_cloud: bool = False,
    # Common
    max_wpm: float | None = None,
) -> list[dict]:
    """Process all .txt files in directory, generate .mp3 for each."""
    if provider not in {"kokoro", "piper", "qwen3-local", "azure"}:
        raise ValueError(f"Cloud or paid voice provider disabled: {provider}")
    if provider == "azure" and not dry_run and not confirm_cloud:
        raise ValueError("Azure TTS requires --confirm-cloud for each run")
    txt_files = sorted(scene_dir.glob("*.txt"))

    if not txt_files:
        print(f"Error: No .txt files found in {scene_dir}", file=sys.stderr)
        sys.exit(1)
    if provider == "azure" and not dry_run:
        existing_outputs = [
            str(path.with_suffix(".mp3"))
            for path in txt_files
            if path.with_suffix(".mp3").exists()
        ]
        if existing_outputs:
            raise ValueError(
                "Refusing to overwrite existing Azure output(s): " + ", ".join(existing_outputs)
            )

    results = []
    total_duration = 0.0
    total_chars = 0

    for txt_file in txt_files:
        mp3_file = txt_file.with_suffix(".mp3")
        script = txt_file.read_text().strip()

        if not script:
            print(f"Warning: Empty script in {txt_file.name}, skipping", file=sys.stderr)
            continue

        # Parse per-scene instruct frontmatter: [tone: X] or [instruct: X]
        scene_instruct = instruct
        if provider == "qwen3":
            import re
            first_line = script.split("\n", 1)[0].strip()
            m = re.match(r"^\[(tone|instruct):\s*(.+?)\]\s*$", first_line, re.IGNORECASE)
            if m:
                kind, value = m.group(1).lower(), m.group(2).strip()
                if kind == "tone":
                    from qwen3_tts import resolve_tone
                    scene_instruct = resolve_tone(value, "")
                else:
                    scene_instruct = value
                # Strip the frontmatter line from the script
                script = script.split("\n", 1)[1].strip() if "\n" in script else ""

        total_chars += len(script)

        if dry_run:
            scene_result = {
                "dry_run": True,
                "script": str(txt_file),
                "output": str(mp3_file),
                "script_chars": len(script),
            }
            if provider == "qwen3" and scene_instruct:
                scene_result["instruct"] = scene_instruct
            results.append(scene_result)
            if not json_output:
                tone_note = f" [instruct: {scene_instruct}]" if scene_instruct != instruct else ""
                print(f"  {txt_file.name} → {mp3_file.name} ({len(script)} chars){tone_note}")
        else:
            if not json_output:
                print(f"Generating {mp3_file.name}...", file=sys.stderr)

            if provider == "kokoro":
                result = generate_single_audio_kokoro(
                    script=script,
                    output_path=mp3_file,
                    voice=voice,
                    speed=kokoro_speed,
                    max_wpm=max_wpm,
                )
            elif provider == "qwen3":
                result = generate_single_audio_qwen3(
                    script=script,
                    output_path=mp3_file,
                    speaker=speaker,
                    language=language,
                    instruct=scene_instruct,
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    temperature=temperature,
                    top_p=top_p,
                    cloud=cloud,
                    max_wpm=max_wpm,
                )
            elif provider == "60db":
                result = generate_single_audio_60db(
                    script=script,
                    output_path=mp3_file,
                    voice_id=voice_id or None,
                    stability=stability,
                    similarity=similarity,
                    speed=speed,
                    enhance=enhance,
                    transport=transport,
                    api_key=sixtydb_api_key,
                    max_wpm=max_wpm,
                )
            elif provider == "piper":
                result = generate_single_audio_piper(
                    script=script,
                    output_path=mp3_file,
                    voice=piper_voice,
                    speed=piper_speed,
                    max_wpm=max_wpm,
                )
            elif provider == "qwen3-local":
                result = generate_single_audio_qwen3_local(
                    script=script,
                    output_path=mp3_file,
                    ref_audio=ref_audio or "",
                    ref_text=ref_text or "",
                    language="German" if language == "Auto" else language,
                    consent_confirmed=consent_confirmed,
                )
            elif provider == "gemini":
                result = generate_single_audio_gemini(
                    script=script,
                    output_path=mp3_file,
                    voice=gemini_voice,
                    style=gemini_style,
                    model=gemini_model,
                    max_wpm=max_wpm,
                )
            elif provider == "azure":
                result = generate_single_audio_azure(
                    script=script,
                    output_path=mp3_file,
                    locale=azure_locale,
                    gender=azure_gender,
                    max_wpm=max_wpm,
                )
            else:
                raise ValueError(f"Voice provider disabled: {provider}")
            result["script"] = str(txt_file)
            results.append(result)

            if result.get("duration_seconds"):
                total_duration += result["duration_seconds"]

            if not json_output:
                duration_str = f" ({result.get('duration_seconds', '?')}s{_pace_note(result)})"
                print(f"  {mp3_file.name}{duration_str}", file=sys.stderr)

    return results, total_duration, total_chars


def concat_audio_files(mp3_files: list[Path], output_path: Path) -> dict:
    """Use ffmpeg concat demuxer to join audio files."""
    import subprocess
    import tempfile

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create concat list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for mp3 in mp3_files:
            # FFmpeg concat requires specific format with escaped paths
            escaped_path = str(mp3).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
        concat_list = f.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite output
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Error concatenating audio: {result.stderr}", file=sys.stderr)
            return {"success": False, "error": result.stderr}

        duration = get_audio_duration(str(output_path))
        return {
            "success": True,
            "output": str(output_path),
            "duration_seconds": round(duration, 2) if duration else None,
            "source_files": len(mp3_files),
        }
    finally:
        Path(concat_list).unlink(missing_ok=True)


def main():
    load_dotenv()
    args = parse_args()

    provider = args.provider

    # Validate argument combinations
    if args.scene_dir and args.script:
        print("Error: Cannot use both --scene-dir and --script", file=sys.stderr)
        sys.exit(1)

    if args.concat and not args.scene_dir:
        print("Error: --concat requires --scene-dir", file=sys.stderr)
        sys.exit(1)

    if not args.scene_dir and not args.output:
        print("Error: --output is required for single-file mode", file=sys.stderr)
        sys.exit(1)

    if provider == "azure" and not args.confirm_cloud and not args.dry_run:
        print(
            "Error: Azure TTS sends the script text to Microsoft and may be billed "
            "after the free quota; add --confirm-cloud to continue.",
            file=sys.stderr,
        )
        sys.exit(1)
    if provider == "azure" and not args.dry_run:
        missing = [
            name for name in ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
            if not os.getenv(name)
        ]
        if missing:
            print(
                "Error: Configure Azure Speech credentials first: " + ", ".join(missing),
                file=sys.stderr,
            )
            sys.exit(1)

    if args.ref_audio and not args.ref_text:
        print("Error: --ref-text is required with --ref-audio", file=sys.stderr)
        sys.exit(1)

    # Brand voice config resolution
    if args.brand:
        voice_config = load_brand_voice_config(args.brand)
        if not voice_config:
            print(f"Error: Brand '{args.brand}' not found or has no voice.json", file=sys.stderr)
            sys.exit(1)

        if provider == "qwen3":
            qwen3_cfg = voice_config.get("qwen3", {})
            # Apply clone config if no explicit --ref-audio
            clone_cfg = qwen3_cfg.get("clone", {})
            if clone_cfg and not args.ref_audio:
                brand_dir = get_brand_dir(args.brand)

                if "design" in clone_cfg:
                    # VoiceDesign mode — design a character voice from a brief,
                    # cache it, and use that cached wav as the clone reference.
                    design = clone_cfg["design"]
                    if "seedText" not in design or "instruct" not in design:
                        print(
                            "Error: clone.design requires both 'seedText' and 'instruct'",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    cached_rel = design.get("cachedRef", "assets/voice-design-ref.wav")
                    cached_path = brand_dir / cached_rel

                    if not cached_path.exists():
                        print(
                            f"Designing brand voice for '{args.brand}' (first use)...\n"
                            f"  Instruct: {design['instruct'][:80]}...",
                            file=sys.stderr,
                        )
                        cached_path.parent.mkdir(parents=True, exist_ok=True)

                        from qwen3_tts import generate_audio as _qwen3_generate
                        design_result = _qwen3_generate(
                            text=design["seedText"],
                            output_path=str(cached_path),
                            design_instruct=design["instruct"],
                            language=(design.get("language") or "English"),
                            output_format="wav",
                            verbose=True,
                            cloud=args.cloud,
                        )
                        if not design_result.get("success"):
                            print(
                                f"Error: voice design failed: {design_result.get('error')}",
                                file=sys.stderr,
                            )
                            sys.exit(1)
                        print(f"  Cached designed voice at {cached_path}", file=sys.stderr)

                    args.ref_audio = str(cached_path)
                    args.ref_text = design["seedText"]

                elif "refAudio" in clone_cfg:
                    # Legacy: user-recorded reference audio
                    ref_audio_path = brand_dir / clone_cfg["refAudio"]
                    if ref_audio_path.exists():
                        args.ref_audio = str(ref_audio_path)
                        args.ref_text = clone_cfg.get("refText", "")
                    else:
                        print(
                            f"Warning: Clone ref audio not found: {ref_audio_path}",
                            file=sys.stderr,
                        )
            # Apply speaker/language/instruct defaults from brand
            if qwen3_cfg.get("speaker") and args.speaker == "Ryan":
                args.speaker = qwen3_cfg["speaker"]
            if qwen3_cfg.get("language") and args.language == "Auto":
                args.language = qwen3_cfg["language"]
            if qwen3_cfg.get("instruct") and not args.instruct:
                args.instruct = qwen3_cfg["instruct"]
            if qwen3_cfg.get("tone") and not args.tone and not args.instruct:
                args.tone = qwen3_cfg["tone"]
        elif provider == "kokoro":
            kokoro_cfg = voice_config.get("kokoro", {})
            if kokoro_cfg.get("voice") and args.voice == "am_michael":
                args.voice = kokoro_cfg["voice"]
            if kokoro_cfg.get("speed") and args.speed == 1.0:
                args.speed = kokoro_cfg["speed"]
        elif provider == "60db":
            # Apply 60db voice ID + settings from the brand's `sixtydb` block
            sixtydb_cfg = voice_config.get("sixtydb", {})
            _sixtydb_vid = sixtydb_cfg.get("voiceId")
            if not args.voice_id and _sixtydb_vid and _sixtydb_vid != "YOUR_VOICE_ID_HERE":
                args.voice_id = _sixtydb_vid
            sixtydb_settings = sixtydb_cfg.get("settings", {})
            # Brand settings fill in only when the CLI left a default in place.
            if "stability" in sixtydb_settings and args.stability == 0.85:
                args.stability = sixtydb_settings["stability"]
            if "similarity" in sixtydb_settings and args.similarity == 0.95:
                args.similarity = sixtydb_settings["similarity"]
            if "speed" in sixtydb_settings and args.speed == 1.0:
                args.speed = sixtydb_settings["speed"]
            if "enhance" in sixtydb_settings and args.enhance is True:
                args.enhance = sixtydb_settings["enhance"]

    # Resolve tone preset → instruct text for Qwen3
    if provider == "qwen3" and (args.tone or args.instruct):
        from qwen3_tts import resolve_tone
        args.instruct = resolve_tone(args.tone, args.instruct)

    # Warn if tone/instruct used with clone (clone mode ignores instruct)
    if provider == "qwen3" and args.ref_audio and args.instruct:
        print(
            "Note: --tone/--instruct is ignored when using a cloned voice.\n"
            "  The clone's tone comes from your reference recording.\n"
            "  Tip: Run /voice-clone to record a new reference with a different feel.",
            file=sys.stderr,
        )
        args.instruct = ""

    # Provider-specific setup
    client = None
    voice_id = None
    sixtydb_api_key = None


    # Per-scene mode
    if args.scene_dir:
        scene_dir = Path(args.scene_dir)
        if not scene_dir.is_dir():
            print(f"Error: Scene directory not found: {scene_dir}", file=sys.stderr)
            sys.exit(1)

        if not args.json:
            txt_count = len(list(scene_dir.glob("*.txt")))
            provider_label = {
                "qwen3-local": "Qwen3-TTS lokal", "kokoro": "Kokoro TTS", "piper": "Piper TTS",
                "gemini": "Gemini TTS", "azure": "Azure Arabic TTS",
            }.get(provider, "local TTS")
            print(
                f"Processing {txt_count} scene scripts in {scene_dir} ({provider_label})...",
                file=sys.stderr,
            )

        if args.dry_run:
            if not args.json:
                print("Would generate:")
            results, total_duration, total_chars = process_scene_directory(
                scene_dir=scene_dir,
                dry_run=True,
                json_output=args.json,
                provider=provider,
                client=client,
                voice_id=voice_id or "",
                model=args.model,
                stability=args.stability,
                similarity=args.similarity,
                style=args.style,
                speed=args.speed,
                speaker=args.speaker,
                language=args.language,
                instruct=args.instruct,
                ref_audio=args.ref_audio,
                ref_text=args.ref_text,
                temperature=args.temperature,
                top_p=args.top_p,
                cloud=args.cloud,
                voice=args.voice,
                kokoro_speed=args.speed,
                piper_voice=args.piper_voice,
                piper_speed=args.piper_speed,
                consent_confirmed=args.consent_confirmed,
                gemini_voice=args.gemini_voice,
                gemini_style=args.gemini_style,
                gemini_model=args.gemini_model,
                azure_locale=args.azure_locale,
                azure_gender=args.azure_gender,
                confirm_cloud=args.confirm_cloud,
                enhance=args.enhance,
                transport=args.transport,
                sixtydb_api_key=sixtydb_api_key,
                max_wpm=args.max_wpm,
            )
            result = {
                "dry_run": True,
                "mode": "per_scene",
                "provider": provider,
                "scene_dir": str(scene_dir),
                "total_chars": total_chars,
                "scenes": results,
            }
            if provider == "60db":
                result["voice_id"] = voice_id
                result["transport"] = args.transport
                result["settings"] = {
                    "stability": args.stability,
                    "similarity": args.similarity,
                    "speed": args.speed,
                    "enhance": args.enhance,
                }
            elif provider == "gemini":
                result["voice"] = args.gemini_voice
                result["model"] = args.gemini_model
                if args.gemini_style:
                    result["style"] = args.gemini_style
            elif provider == "azure":
                result["locale"] = args.azure_locale
                result["voice_gender"] = args.azure_gender
            else:
                result["speaker"] = args.speaker
                result["language"] = args.language
                if args.instruct:
                    result["instruct"] = args.instruct
                if args.temperature is not None:
                    result["temperature"] = args.temperature
                if args.top_p is not None:
                    result["top_p"] = args.top_p
            if args.concat:
                result["concat_output"] = args.concat
            if args.json:
                print(json.dumps(result, indent=2))
            return

        # Generate per-scene audio
        results, total_duration, total_chars = process_scene_directory(
            scene_dir=scene_dir,
            dry_run=False,
            json_output=args.json,
            provider=provider,
            client=client,
            voice_id=voice_id or "",
            model=args.model,
            stability=args.stability,
            similarity=args.similarity,
            style=args.style,
            speed=args.speed,
            speaker=args.speaker,
            language=args.language,
            instruct=args.instruct,
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            temperature=args.temperature,
            top_p=args.top_p,
            cloud=args.cloud,
            voice=args.voice,
            kokoro_speed=args.speed,
            piper_voice=args.piper_voice,
            piper_speed=args.piper_speed,
            consent_confirmed=args.consent_confirmed,
            gemini_voice=args.gemini_voice,
            gemini_style=args.gemini_style,
            gemini_model=args.gemini_model,
            azure_locale=args.azure_locale,
            azure_gender=args.azure_gender,
            confirm_cloud=args.confirm_cloud,
            enhance=args.enhance,
            transport=args.transport,
            sixtydb_api_key=sixtydb_api_key,
            max_wpm=args.max_wpm,
        )

        # Build final result
        result = {
            "success": True,
            "mode": "per_scene",
            "provider": provider,
            "scene_dir": str(scene_dir),
            "total_chars": total_chars,
            "total_duration_seconds": round(total_duration, 2),
            "total_duration_frames_30fps": int(total_duration * 30),
            "scenes": results,
        }
        if provider == "60db":
            result["voice_id"] = voice_id
            result["transport"] = args.transport
        elif provider == "azure":
            result["locale"] = args.azure_locale
            result["voice_gender"] = args.azure_gender

        # Concat if requested
        if args.concat:
            mp3_files = [Path(r["output"]) for r in results if r.get("success")]
            if not args.json:
                print(f"\nConcatenating {len(mp3_files)} files...", file=sys.stderr)
            concat_result = concat_audio_files(mp3_files, Path(args.concat))
            result["concat"] = concat_result
            if not args.json and concat_result.get("success"):
                print(f"  {args.concat} ({concat_result.get('duration_seconds')}s)", file=sys.stderr)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\nPer-scene audio generated:", file=sys.stderr)
            print(f"  Total: {total_duration:.1f}s ({int(total_duration * 30)} frames @ 30fps)", file=sys.stderr)
            print(f"  Characters: {total_chars}", file=sys.stderr)
        return

    # Single-file mode (original behavior)
    script = read_script(args.script)
    if not script:
        print("Error: Empty script", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)

    # Dry run mode
    if args.dry_run:
        result = {
            "dry_run": True,
            "mode": "single",
            "provider": provider,
            "script_length": len(script),
            "script_chars": len(script),
            "output": str(output_path),
        }
        if provider == "60db":
            result["voice_id"] = voice_id
            result["transport"] = args.transport
            result["settings"] = {
                "stability": args.stability,
                "similarity": args.similarity,
                "speed": args.speed,
                "enhance": args.enhance,
            }
        elif provider == "gemini":
            result["voice"] = args.gemini_voice
            result["model"] = args.gemini_model
            if args.gemini_style:
                result["style"] = args.gemini_style
        elif provider == "azure":
            result["locale"] = args.azure_locale
            result["voice_gender"] = args.azure_gender
        else:
            result["speaker"] = args.speaker
            result["language"] = args.language
            if args.instruct:
                result["instruct"] = args.instruct
            if args.temperature is not None:
                result["temperature"] = args.temperature
            if args.top_p is not None:
                result["top_p"] = args.top_p
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Would generate voiceover:")
            if provider == "60db":
                print(f"  Voice ID: {voice_id}")
                print(f"  Transport: {args.transport}")
            elif provider == "gemini":
                print(f"  Voice: {args.gemini_voice}")
                print(f"  Model: {args.gemini_model}")
            elif provider == "azure":
                print(f"  Arabic variety: {args.azure_locale}")
                print(f"  Voice gender: {args.azure_gender}")
            else:
                print(f"  Speaker: {args.speaker}")
                print(f"  Language: {args.language}")
            print(f"  Script: {len(script)} characters")
            print(f"  Output: {output_path}")
        return

    # Generate voiceover
    if not args.json:
        provider_label = {
            "kokoro": "Kokoro TTS", "qwen3": "Qwen3-TTS", "60db": "60db", "piper": "Piper TTS",
            "gemini": "Gemini TTS",
            "azure": "Azure Arabic TTS",
        }.get(provider, "local TTS")
        print(f"Generating voiceover ({len(script)} chars, {provider_label})...", file=sys.stderr)

    if provider == "kokoro":
        result = generate_single_audio_kokoro(
            script=script,
            output_path=output_path,
            voice=args.voice,
            speed=args.speed,
            max_wpm=args.max_wpm,
        )
    elif provider == "qwen3":
        result = generate_single_audio_qwen3(
            script=script,
            output_path=output_path,
            speaker=args.speaker,
            language=args.language,
            instruct=args.instruct,
            ref_audio=args.ref_audio,
            ref_text=args.ref_text,
            temperature=args.temperature,
            top_p=args.top_p,
            cloud=args.cloud,
            max_wpm=args.max_wpm,
        )
    elif provider == "60db":
        result = generate_single_audio_60db(
            script=script,
            output_path=output_path,
            voice_id=voice_id,
            stability=args.stability,
            similarity=args.similarity,
            speed=args.speed,
            enhance=args.enhance,
            transport=args.transport,
            api_key=sixtydb_api_key,
            max_wpm=args.max_wpm,
        )
    elif provider == "piper":
        result = generate_single_audio_piper(
            script=script,
            output_path=output_path,
            voice=args.piper_voice,
            speed=args.piper_speed,
            max_wpm=args.max_wpm,
        )
    elif provider == "qwen3-local":
        result = generate_single_audio_qwen3_local(
            script=script,
            output_path=output_path,
            ref_audio=args.ref_audio or "",
            ref_text=args.ref_text or "",
            language="German" if args.language == "Auto" else args.language,
            consent_confirmed=args.consent_confirmed,
        )
    elif provider == "gemini":
        result = generate_single_audio_gemini(
            script=script,
            output_path=output_path,
            voice=args.gemini_voice,
            style=args.gemini_style,
            model=args.gemini_model,
            max_wpm=args.max_wpm,
        )
    elif provider == "azure":
        result = generate_single_audio_azure(
            script=script,
            output_path=output_path,
            locale=args.azure_locale,
            gender=args.azure_gender,
            max_wpm=args.max_wpm,
        )
    else:
        raise ValueError(f"Voice provider disabled: {provider}")

    result["mode"] = "single"
    result["provider"] = provider
    if provider == "kokoro":
        result["voice"] = args.voice
    elif provider == "piper":
        result["voice"] = args.piper_voice
    elif provider == "gemini":
        result["voice"] = args.gemini_voice
        result["model"] = args.gemini_model
        if args.gemini_style:
            result["style"] = args.gemini_style
    elif provider == "azure":
        result["locale"] = args.azure_locale
        result["voice_gender"] = args.azure_gender
    elif provider == "60db":
        result["voice_id"] = voice_id
        result["transport"] = args.transport

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            print(f"Voiceover saved to: {output_path}", file=sys.stderr)
            duration = result.get("duration_seconds")
            if duration:
                frames = int(duration * 30)
                print(
                    f"Duration: {duration:.2f}s ({frames} frames @ 30fps{_pace_note(result)})",
                    file=sys.stderr,
                )
        else:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
