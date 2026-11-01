#!/usr/bin/env python3
"""Local FFmpeg mix with explicit voiceover > music > SFX priority."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.media_validation import MediaValidationError, validate_audio


class AudioMixError(RuntimeError):
    pass


_TRUE_PEAK_FILTER_TARGET = -1.8
_TRUE_PEAK_RELEASE_LIMIT = -1.5
_LOUDNESS_TOLERANCE = 0.5


def _parse_loudnorm_measurement(stderr: str) -> dict[str, str]:
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, flags=re.DOTALL)
    if not matches:
        raise AudioMixError("FFmpeg-Lautheitsmessung lieferte keine Messwerte")
    try:
        measurement = json.loads(matches[-1])
    except json.JSONDecodeError as error:
        raise AudioMixError("FFmpeg-Lautheitsmessung lieferte ungültiges JSON") from error
    required = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not required.issubset(measurement):
        raise AudioMixError("FFmpeg-Lautheitsmessung ist unvollständig")
    return {key: str(measurement[key]) for key in required}


def _loudnorm_filter(target_lufs: float, measurement: dict[str, str] | None = None) -> str:
    options = (
        f"loudnorm=I={target_lufs}:TP={_TRUE_PEAK_FILTER_TARGET}:LRA=11"
    )
    if measurement is None:
        return options + ":print_format=json"
    return (
        options
        + f":measured_I={measurement['input_i']}"
        + f":measured_TP={measurement['input_tp']}"
        + f":measured_LRA={measurement['input_lra']}"
        + f":measured_thresh={measurement['input_thresh']}"
        + f":offset={measurement['target_offset']}"
        + ":linear=true:print_format=summary"
    )


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
    filters = []
    mix_inputs = ["[voice_mix]"]
    if music:
        filters.append("[1:a]aresample=48000,asplit=2[voice_mix][voice_side]")
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        filters.append("[2:a]aresample=48000,volume=0.28[music]")
        filters.append(
            "[music][voice_side]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=450[ducked]"
        )
        mix_inputs.append("[ducked]")
    else:
        filters.append("[1:a]aresample=48000[voice_mix]")
    if sfx:
        index = 3 if music else 2
        inputs += ["-i", str(sfx)]
        filters.append(f"[{index}:a]aresample=48000,volume=0.45[sfx]")
        mix_inputs.append("[sfx]")
    premix = (
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:normalize=0,"
        + "aformat=sample_rates=48000:channel_layouts=stereo"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    analysis_filters = [*filters, f"{premix},{_loudnorm_filter(target_lufs)}[aout]"]
    analysis_command = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(analysis_filters),
        "-map",
        "0:v:0",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-shortest",
        "-f",
        "null",
        "-",
    ]
    try:
        analysis = subprocess.run(
            analysis_command, check=True, capture_output=True, text=True, timeout=300
        )
    except subprocess.CalledProcessError as error:
        message = f"FFmpeg-Lautheitsmessung fehlgeschlagen: {error.stderr[-1000:]}"
        raise AudioMixError(message) from error
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise AudioMixError("FFmpeg-Lautheitsmessung fehlgeschlagen") from error
    measurement = _parse_loudnorm_measurement(analysis.stderr)

    final_filters = [
        *filters,
        f"{premix},{_loudnorm_filter(target_lufs, measurement)}[aout]",
    ]
    command = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(final_filters),
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
    loudness = float(report.details["loudnessLufs"])
    true_peak = report.details["truePeakDbfs"]
    if abs(loudness - target_lufs) > _LOUDNESS_TOLERANCE:
        raise AudioMixError(
            f"Audio-QC verfehlt Ziellautheit: {loudness} LUFS statt {target_lufs} LUFS"
        )
    if true_peak != "unavailable" and float(true_peak) > _TRUE_PEAK_RELEASE_LIMIT:
        raise AudioMixError(
            f"Audio-QC überschreitet True-Peak-Limit: {true_peak} dBFS"
        )
    return {
        "voiceover": str(voiceover),
        "music_ducked": music is not None,
        "sfx_mixed": sfx is not None,
        "target_lufs": target_lufs,
        "true_peak_limit_dbfs": _TRUE_PEAK_RELEASE_LIMIT,
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
