#!/usr/bin/env python3
"""HANNIBAL AI OS — Unified Master Media Pipeline.

Connects the 4-pillar video architecture into a single automated command:
  1. Video Engine: LTX-2.5 MLX (0 € Lokal-First) or Cloud Soul-ID via Higgsfield.
  2. Hardware Finishing: Apple Silicon VideoToolbox Lanczos-3 CAS 1080p.
  3. Audio Pipeline: Optional Gemini 3.8 Flash TTS + Sidechain Music Ducking (-14 LUFS).
  4. Final Delivery: Ready-to-publish 1080p Master MP4.

Usage:
  # 1. Minimal 0-€ local generation:
  python3 tools/master_pipeline.py --prompt "Cinematic luxury car" --output out/car.mp4

  # 2. Key-Visual to Video (FLUX image input):
  python3 tools/master_pipeline.py --prompt "Camera dolly out" --image img.png -o out.mp4

  # 3. Full Commercial with Voiceover and Music:
  python3 tools/master_pipeline.py \\
      --prompt "Modern architecture showcase" \\
      --voice-text "Willkommen in der Zukunft des Wohnens. [pause] Exklusiv bei Licbarska." \\
      --voice-mode promote \\
      --music assets/audio/corporate_beat.mp3 \\
      --target-lufs -14.0 \\
      --output out/commercial.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    TOOLKIT_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(TOOLKIT_ROOT))
else:
    TOOLKIT_ROOT = Path(__file__).resolve().parents[1]

from tools.audio_mix import mix  # noqa: E402
from tools.ltx25_mlx_adapter import generate_video  # noqa: E402


def run_voiceover(
    text: str,
    output_path: Path,
    mode: str = "promote",
    voice: str = "Puck",
) -> bool:
    """Generate professional voiceover using Gemini 3.8 Flash TTS."""
    tts_script = TOOLKIT_ROOT / "tools" / "gemini_tts.py"
    if not tts_script.is_file():
        return False

    cmd = [
        sys.executable,
        str(tts_script),
        "--text",
        text,
        "--mode",
        mode,
        "--voice",
        voice,
        "--output",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0


def run_pipeline(
    prompt: str,
    output_path: str,
    *,
    image: str | None = None,
    end_image: str | None = None,
    continue_from: str | None = None,
    voice_text: str | None = None,
    voice_mode: str = "promote",
    music: str | None = None,
    provider: str = "local",
    duration: int = 4,
    target_lufs: float = -14.0,
    verbose: bool = True,
) -> dict[str, Any]:
    """Execute the full multi-modal pipeline from prompt to finished master."""
    start_time = time.time()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hannibal-pipeline-") as tmp_dir:
        tmp = Path(tmp_dir)
        video_draft = tmp / "draft_1080p.mp4"

        # 1. Video Generation & Hardware CAS 1080p Sharpening
        if verbose:
            print(
                f"[Säule 1/2] Generiere Video ({provider.upper()}, "
                f"1080p CAS Schärfung)...",
                file=sys.stderr,
            )

        if provider == "local":
            frames = duration * 24 + 1
            # Ensure frames match 8n+1
            remainder = (frames - 1) % 8
            if remainder != 0:
                frames += 8 - remainder

            v_res = generate_video(
                prompt=prompt,
                output_path=str(video_draft),
                mode="distilled",
                frames=frames,
                image=image,
                end_image=end_image,
                continue_from=continue_from,
                sharpen=True,
                verbose=verbose,
            )
            if not v_res.get("success"):
                return {
                    "success": False,
                    "error": f"Video-Generierung fehlgeschlagen: {v_res.get('error')}",
                }
        else:
            # Higgsfield Cloud-Pfad
            cloud_tool = TOOLKIT_ROOT / "tools" / "video_generate.py"
            cmd = [
                sys.executable,
                str(cloud_tool),
                "--provider",
                "higgsfield",
                "--model",
                "seedance_2_mini",
                "--prompt",
                prompt,
                "--output",
                str(video_draft),
                "--duration",
                str(duration),
                "--confirm",
            ]
            if image:
                cmd += ["--image", str(image)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0 or not video_draft.is_file():
                return {
                    "success": False,
                    "error": f"Higgsfield-Generierung fehlgeschlagen: {proc.stderr[:400]}",
                }

        # 2. Audio Pipeline: Optional Voiceover & Sidechain Mix
        voice_file: Path | None = None
        if voice_text:
            if verbose:
                print(
                    f"[Audio] Generiere Voiceover ({voice_mode})...",
                    file=sys.stderr,
                )
            voice_wav = tmp / "voiceover.wav"
            ok_voice = run_voiceover(voice_text, voice_wav, mode=voice_mode)
            if ok_voice:
                voice_file = voice_wav
            elif verbose:
                print(
                    "Warning: Voiceover konnte nicht erzeugt werden (überspringe).",
                    file=sys.stderr,
                )

        music_file = Path(music) if music and Path(music).is_file() else None

        # 3. Audio Mixdown (-14 LUFS Broadcast Gate)
        if voice_file is not None or music_file is not None:
            if verbose:
                print(
                    f"[Mastering] Audio-Mixdown (Target: {target_lufs} LUFS)...",
                    file=sys.stderr,
                )

            # If only music without voice, generate a silent voice anchor for mix()
            dummy_voice = None
            active_voice = voice_file
            if active_voice is None:
                dummy_voice = tmp / "dummy_silence.wav"
                ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "anullsrc=r=48000:cl=mono",
                        "-t",
                        str(duration),
                        str(dummy_voice),
                    ],
                    capture_output=True,
                )
                active_voice = dummy_voice

            mixed_res = mix(
                video=video_draft,
                voiceover=active_voice,
                output=out,
                music=music_file,
                target_lufs=target_lufs,
            )
            audio_status = "mastered"
            final_lufs = mixed_res.get("target_lufs", target_lufs)
        else:
            # Kein Audio angefordert: Draft direkt zum Ziel kopieren
            shutil.copy2(video_draft, out)
            audio_status = "none"
            final_lufs = None

    elapsed_s = round(time.time() - start_time, 2)
    return {
        "success": True,
        "master_video": str(out),
        "resolution": "1920x1080",
        "provider": provider,
        "audio_status": audio_status,
        "target_lufs": final_lufs,
        "elapsed_seconds": elapsed_s,
        "cost_eur": 0.0 if provider == "local" else 0.05,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--prompt", "-p", required=True, help="Video-Szenenbeschreibung")
    parser.add_argument("--output", "-o", required=True, help="Pfad zum finalen Master (.mp4)")
    parser.add_argument("--image", "-i", default=None, help="Startbild (z. B. aus FLUX 3)")
    parser.add_argument("--end-image", default=None, help="Ziel-Endbild (Keyframe-Sandwich)")
    parser.add_argument("--continue-from", default=None, help="Vorherigen Clip fortsetzen")
    parser.add_argument("--voice-text", "-t", default=None, help="Sprechtext für Voiceover")
    parser.add_argument(
        "--voice-mode",
        default="promote",
        choices=["promote", "friendly", "narration", "podcast", "whisper"],
        help="Stimmlage für Gemini TTS (Standard: promote)",
    )
    parser.add_argument("--music", "-m", default=None, help="Hintergrund-Musikdatei (.mp3/.wav)")
    parser.add_argument(
        "--provider",
        default="local",
        choices=["local", "higgsfield"],
        help="Engine: 'local' (LTX-2.5 MLX, 0 €) oder 'higgsfield' (Cloud Soul-ID)",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=4,
        help="Dauer in Sekunden (Standard: 4)",
    )
    parser.add_argument(
        "--target-lufs",
        type=float,
        default=-14.0,
        help="Ziel-Lautheit für Audio-Master (Standard: -14.0 LUFS)",
    )

    args = parser.parse_args()
    result = run_pipeline(
        prompt=args.prompt,
        output_path=args.output,
        image=args.image,
        end_image=args.end_image,
        continue_from=args.continue_from,
        voice_text=args.voice_text,
        voice_mode=args.voice_mode,
        music=args.music,
        provider=args.provider,
        duration=args.duration,
        target_lufs=args.target_lufs,
        verbose=True,
    )

    print(json.dumps(result, indent=2))
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
