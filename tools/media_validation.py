#!/usr/bin/env python3
"""Deterministic local acceptance checks for rendered audio and video."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MediaValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaReport:
    kind: str
    duration: float
    codec: str
    details: dict[str, int | float | str]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise MediaValidationError(f"Medienprüfung fehlgeschlagen: {command[0]}") from error


def _probe(path: Path) -> dict[str, Any]:
    result = _run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise MediaValidationError("ffprobe lieferte kein gültiges JSON") from error


def _duration(probe: dict[str, Any]) -> float:
    try:
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise MediaValidationError("Keine gültige Mediendauer gefunden") from error
    if duration <= 0:
        raise MediaValidationError("Mediendauer muss größer als null sein")
    return duration


def validate_audio(path: Path, max_silence_seconds: float = 5.0) -> MediaReport:
    probe = _probe(path)
    stream = next(
        (item for item in probe.get("streams", []) if item.get("codec_type") == "audio"), None
    )
    if stream is None:
        raise MediaValidationError("Keine Audiospur gefunden")
    try:
        sample_rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        codec = str(stream["codec_name"])
    except (KeyError, TypeError, ValueError) as error:
        raise MediaValidationError("Unvollständige Audiospur-Metadaten") from error
    if sample_rate < 16_000 or channels not in {1, 2}:
        raise MediaValidationError("Nicht unterstützte Sample-Rate oder Kanalzahl")

    analysis = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true,silencedetect=noise=-50dB:d=0.5",
            "-f",
            "null",
            "-",
        ]
    )
    integrated = re.findall(r"I:\s*(-?\d+(?:\.\d+)?) LUFS", analysis.stderr)
    silences = [
        float(value)
        for value in re.findall(r"silence_duration:\s*(\d+(?:\.\d+)?)", analysis.stderr)
    ]
    if not integrated:
        raise MediaValidationError("Lautheit konnte nicht ermittelt werden")
    loudness = float(integrated[-1])
    if loudness < -40 or loudness > -5:
        raise MediaValidationError(f"Lautheit außerhalb des Abnahmebereichs: {loudness} LUFS")
    longest_silence = max(silences, default=0.0)
    if longest_silence > max_silence_seconds:
        raise MediaValidationError(f"Zu lange Stille: {longest_silence}s")
    return MediaReport(
        "audio",
        _duration(probe),
        codec,
        {
            "sampleRate": sample_rate,
            "channels": channels,
            "loudnessLufs": loudness,
            "longestSilenceSeconds": longest_silence,
        },
    )


def validate_video(path: Path) -> MediaReport:
    probe = _probe(path)
    stream = next(
        (item for item in probe.get("streams", []) if item.get("codec_type") == "video"), None
    )
    if stream is None:
        raise MediaValidationError("Keine Videospur gefunden")
    try:
        width = int(stream["width"])
        height = int(stream["height"])
        codec = str(stream["codec_name"])
        numerator, denominator = str(stream["avg_frame_rate"]).split("/", maxsplit=1)
        frame_rate = float(numerator) / float(denominator)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise MediaValidationError("Unvollständige Videospur-Metadaten") from error
    if width <= 0 or height <= 0 or frame_rate <= 0:
        raise MediaValidationError("Ungültige Auflösung oder Framerate")
    _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"])
    _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"])
    _run(["ffmpeg", "-v", "error", "-sseof", "-0.01", "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"])
    return MediaReport(
        "video",
        _duration(probe),
        codec,
        {
            "container": str(probe.get("format", {}).get("format_name", "")),
            "width": width,
            "height": height,
            "frameRate": frame_rate,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a final audio or video artifact")
    parser.add_argument("kind", choices=["audio", "video"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if not args.path.is_file():
        parser.error(f"Datei nicht gefunden: {args.path}")
    report = validate_audio(args.path) if args.kind == "audio" else validate_video(args.path)
    print(json.dumps(report.__dict__, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
