#!/usr/bin/env python3
"""Local FFmpeg mix with explicit voiceover > music > SFX priority."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.media_validation import MediaValidationError, validate_audio


class AudioMixError(RuntimeError):
    pass


def mix(
    video: Path,
    voiceover: Path,
    output: Path,
    *,
    music: Path | None = None,
    sfx: Path | None = None,
    target_lufs: float = -14.0,
) -> dict[str, Any]:
    """Create a conservative, speech-prioritized master without external services."""
    for path in (video, voiceover, music, sfx):
        if path is not None and not path.is_file():
            raise AudioMixError(f"Audioquelle fehlt: {path}")
    inputs = ["-i", str(video), "-i", str(voiceover)]
    filters = ["[1:a]aresample=48000,asplit=2[voice_mix][voice_side]"]
    mix_inputs = ["[voice_mix]"]
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        filters.append("[2:a]aresample=48000,volume=0.28[music]")
        filters.append(
            "[music][voice_side]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=450[ducked]"
        )
        mix_inputs.append("[ducked]")
    if sfx:
        index = 3 if music else 2
        inputs += ["-i", str(sfx)]
        filters.append(f"[{index}:a]aresample=48000,volume=0.45[sfx]")
        mix_inputs.append("[sfx]")
    filters.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:normalize=0,loudnorm=I={target_lufs}:TP=-1.5:LRA=11[aout]"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as error:
        raise AudioMixError(f"FFmpeg-Audio-Mix fehlgeschlagen: {error.stderr[-1000:]}") from error
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise AudioMixError("FFmpeg-Audio-Mix fehlgeschlagen") from error
    try:
        report = validate_audio(output)
    except MediaValidationError as error:
        raise AudioMixError(f"Audio-QC fehlgeschlagen: {error}") from error
    return {
        "voiceover": str(voiceover),
        "music_ducked": music is not None,
        "sfx_mixed": sfx is not None,
        "audio_qc": report.details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mix local voiceover, music and SFX.")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--voiceover", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--music", type=Path)
    parser.add_argument("--sfx", type=Path)
    parser.add_argument("--report", type=Path, help="Write the local mix/QC evidence as JSON.")
    args = parser.parse_args()
    try:
        result = mix(args.video, args.voiceover, args.output, music=args.music, sfx=args.sfx)
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text + "\n", encoding="utf-8")
        print(text)
    except AudioMixError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
