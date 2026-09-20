#!/usr/bin/env python3
"""Deterministic local scene and timeline analysis for an ingest package."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class AnalysisError(RuntimeError):
    """An analysis package is incomplete or contains an invalid timeline."""


def _number(value: object, label: str) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError) as error:
        raise AnalysisError(f"Ungültiger {label}-Wert.") from error
    if not math.isfinite(number):
        raise AnalysisError(f"Ungültiger {label}-Wert.")
    return number


def _duration(start: float, end: float) -> float:
    return round(end - start, 6)


def validate_timeline(duration: float, entries: list[dict[str, object]]) -> None:
    """Reject invalid or overlapping intervals in one common video timebase."""
    if duration <= 0:
        raise AnalysisError("Video-Dauer muss größer als null sein.")
    previous_end = 0.0
    for entry in entries:
        start = _number(entry.get("start"), "Startzeit")
        end = _number(entry.get("end"), "Endzeit")
        if start < 0 or end > duration + 0.000001 or start >= end:
            raise AnalysisError("Timeline enthält einen ungültigen Zeitbereich.")
        if start < previous_end - 0.000001:
            raise AnalysisError("Timeline-Intervalle überlappen sich.")
        previous_end = end


def build_scenes(duration: float, boundaries: list[float]) -> list[dict[str, object]]:
    """Build contiguous visual scenes from validated cut timestamps."""
    if duration <= 0:
        raise AnalysisError("Video-Dauer muss größer als null sein.")
    cuts = sorted({round(value, 6) for value in boundaries if 0 < value < duration})
    starts = [0.0, *cuts]
    ends = [*cuts, duration]
    scenes = [
        {
            "scene_id": f"scene_{index:03d}",
            "start": start,
            "end": end,
            "duration": _duration(start, end),
        }
        for index, (start, end) in enumerate(zip(starts, ends), start=1)
        if end > start
    ]
    validate_timeline(duration, scenes)
    return scenes


def _transcript_segments(payload: object) -> list[dict[str, object]]:
    segments = payload.get("segments") if isinstance(payload, dict) else payload
    if not isinstance(segments, list):
        raise AnalysisError("Transcript benötigt eine Segmentliste.")
    normalized: list[dict[str, object]] = []
    previous_end = 0.0
    for index, raw in enumerate(segments, start=1):
        if not isinstance(raw, dict):
            raise AnalysisError("Transcript enthält ein ungültiges Segment.")
        start = _number(raw.get("start"), "Transcript-Startzeit")
        end = _number(raw.get("end"), "Transcript-Endzeit")
        text = str(raw.get("text", "")).strip()
        if start < 0 or start >= end or start < previous_end - 0.000001:
            raise AnalysisError("Transcript enthält ungültige oder überlappende Timestamps.")
        if not text:
            raise AnalysisError("Transcript enthält ein leeres Segment.")
        normalized.append(
            {"segment_id": f"segment_{index:03d}", "start": start, "end": end, "text": text}
        )
        previous_end = end
    return normalized


def align_transcript_to_scenes(
    scenes: list[dict[str, object]], transcript: object
) -> list[dict[str, object]]:
    """Attach complete transcript segments to every visual scene they overlap.

    A segment crossing a visual cut is intentionally referenced by both scenes;
    the canonical transcript remains untouched and each overlap records its own
    time range, so no text is silently truncated.
    """
    segments = _transcript_segments(transcript)
    aligned: list[dict[str, object]] = []
    for scene in scenes:
        start = _number(scene.get("start"), "Szenenstart")
        end = _number(scene.get("end"), "Szenenende")
        pieces: list[dict[str, object]] = []
        for segment in segments:
            overlap_start = max(start, _number(segment["start"], "Transcript-Startzeit"))
            overlap_end = min(end, _number(segment["end"], "Transcript-Endzeit"))
            if overlap_end <= overlap_start:
                continue
            pieces.append(
                {
                    **segment,
                    "overlap_start": overlap_start,
                    "overlap_end": overlap_end,
                    "overlap_duration": _duration(overlap_start, overlap_end),
                }
            )
        text = " ".join(str(piece["text"]) for piece in pieces)
        scene_duration = end - start
        coverage = sum(
            _number(piece["overlap_duration"], "Transcript-Überlappungsdauer") for piece in pieces
        )
        aligned.append(
            {
                **scene,
                "transcript_segment_ids": [str(piece["segment_id"]) for piece in pieces],
                "transcript_segments": pieces,
                "transcript_text": text,
                "speech_coverage": round(min(coverage / scene_duration, 1.0), 6),
                "word_count": len(text.split()),
                "character_count": len(text),
                "words_per_second": round(len(text.split()) / scene_duration, 6),
                "characters_per_second": round(len(text) / scene_duration, 6),
            }
        )
    return aligned


def _normalize_silences(
    duration: float, silences: list[dict[str, object]]
) -> list[dict[str, object]]:
    clipped: list[dict[str, object]] = []
    for raw in silences:
        start = max(0.0, _number(raw.get("start"), "Stille-Startzeit"))
        end = min(duration, _number(raw.get("end"), "Stille-Endzeit"))
        if end <= start:
            continue
        if clipped and start <= _number(clipped[-1]["end"], "Stille-Endzeit"):
            clipped[-1]["end"] = max(_number(clipped[-1]["end"], "Stille-Endzeit"), end)
            clipped[-1]["duration"] = _duration(
                _number(clipped[-1]["start"], "Stille-Startzeit"),
                _number(clipped[-1]["end"], "Stille-Endzeit"),
            )
        else:
            clipped.append({"start": start, "end": end, "duration": _duration(start, end)})
    validate_timeline(duration, clipped)
    return clipped


def build_audio_timeline(
    duration: float, silences: list[dict[str, object]]
) -> dict[str, list[dict[str, object]]]:
    """Use silence intervals to compute their contiguous complement as speech."""
    normalized = _normalize_silences(duration, silences)
    speech: list[dict[str, object]] = []
    cursor = 0.0
    for silence in normalized:
        end = _number(silence["start"], "Stille-Startzeit")
        if end > cursor:
            speech.append({"start": cursor, "end": end, "duration": _duration(cursor, end)})
        cursor = _number(silence["end"], "Stille-Endzeit")
    if cursor < duration:
        speech.append({"start": cursor, "end": duration, "duration": _duration(cursor, duration)})
    validate_timeline(duration, speech)
    return {"speech_segments": speech, "silence_segments": normalized}


def build_chapter_candidates(
    scenes: list[dict[str, object]], silences: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Return measurable chapter boundaries; no semantic confidence is claimed."""
    candidates: list[dict[str, object]] = [
        {
            "start": 0.0,
            "reason": ["video_start"],
            "confidence_inputs": {"scene_boundary": True, "preceding_silence_duration": 0.0},
        }
    ]
    for scene in scenes[1:]:
        start = _number(scene["start"], "Szenenstart")
        adjacent = [
            _number(silence["duration"], "Stille-Dauer")
            for silence in silences
            if _number(silence["start"], "Stille-Startzeit")
            <= start
            <= _number(silence["end"], "Stille-Endzeit")
            or abs(_number(silence["end"], "Stille-Endzeit") - start) <= 0.5
        ]
        reasons = ["scene_change"]
        if adjacent:
            reasons.append("silence")
        candidates.append(
            {
                "start": start,
                "reason": reasons,
                "confidence_inputs": {
                    "scene_boundary": True,
                    "preceding_silence_duration": max(adjacent, default=0.0),
                },
            }
        )
    return candidates


def _clip_text(
    start: float, end: float, segments: list[dict[str, object]]
) -> tuple[str, list[str]]:
    overlaps = [
        segment
        for segment in segments
        if _number(segment["start"], "Transcript-Startzeit") < end
        and _number(segment["end"], "Transcript-Endzeit") > start
    ]
    return " ".join(str(segment["text"]) for segment in overlaps), [
        str(segment["segment_id"]) for segment in overlaps
    ]


def build_clip_candidates(
    speech_segments: list[dict[str, object]],
    transcript: object,
    *,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[dict[str, object]]:
    """Build bounded candidates from speech blocks, preferring transcript ends."""
    if min_duration <= 0 or max_duration < min_duration:
        raise AnalysisError("Ungültige minimale oder maximale Clip-Dauer.")
    segments = _transcript_segments(transcript)
    candidates: list[dict[str, object]] = []
    for speech in speech_segments:
        start = _number(speech.get("start"), "Sprach-Startzeit")
        end = _number(speech.get("end"), "Sprach-Endzeit")
        cursor = start
        while end - cursor >= min_duration:
            limit = min(end, cursor + max_duration)
            phrase_ends = [
                _number(segment["end"], "Transcript-Endzeit")
                for segment in segments
                if cursor + min_duration <= _number(segment["end"], "Transcript-Endzeit") <= limit
            ]
            candidate_end = max(phrase_ends, default=limit)
            if (
                end - candidate_end < min_duration
                and candidate_end != end
                and end - cursor <= max_duration
            ):
                candidate_end = end
            if candidate_end - cursor < min_duration or candidate_end <= cursor:
                break
            text, ids = _clip_text(cursor, candidate_end, segments)
            candidates.append(
                {
                    "start": cursor,
                    "end": candidate_end,
                    "duration": _duration(cursor, candidate_end),
                    "transcript": text,
                    "transcript_segment_ids": ids,
                    "reasons": ["speech_block", "natural_end_pause"],
                }
            )
            cursor = candidate_end
    return candidates


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        raise AnalysisError(f"Lokale Medienanalyse fehlgeschlagen: {command[0]}") from error


def detect_scene_boundaries(video_path: Path, *, threshold: float) -> list[float]:
    """Detect visual cuts with FFmpeg's local scene-change filter."""
    if not 0 < threshold <= 1:
        raise AnalysisError("Scene-Threshold muss zwischen 0 und 1 liegen.")
    result = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video_path),
            "-an",
            "-vf",
            f"select=gt(scene\\,{threshold}),showinfo",
            "-f",
            "null",
            "-",
        ]
    )
    return sorted({float(value) for value in re.findall(r"pts_time:([\d.]+)", result.stderr)})


def extract_representative_frames(
    video_path: Path, package_dir: Path, scenes: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Write exactly one midpoint JPEG per scene in a controlled package folder."""
    frame_dir = package_dir / "scene_frames"
    if frame_dir.exists():
        raise AnalysisError("scene_frames existiert bereits; Analysepaket nicht überschrieben.")
    frame_dir.mkdir(parents=True)
    frames: list[dict[str, object]] = []
    try:
        for scene in scenes:
            timestamp = round(
                (_number(scene["start"], "Szenenstart") + _number(scene["end"], "Szenenende")) / 2,
                6,
            )
            target = frame_dir / f"{scene['scene_id']}.jpg"
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-n",
                    "-ss",
                    f"{timestamp:.6f}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(target),
                ]
            )
            if not target.is_file() or target.stat().st_size <= 0:
                raise AnalysisError("FFmpeg erzeugte keinen repräsentativen Frame.")
            scene["representative_frame"] = str(target.relative_to(package_dir))
            scene["representative_frame_timestamp"] = timestamp
            frames.append(
                {
                    "scene_id": scene["scene_id"],
                    "timestamp": timestamp,
                    "path": str(target.relative_to(package_dir)),
                }
            )
    except AnalysisError:
        shutil.rmtree(frame_dir, ignore_errors=True)
        raise
    return frames


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisError(f"{label} ist nicht lesbar.") from error
    if not isinstance(payload, dict):
        raise AnalysisError(f"{label} muss ein JSON-Objekt sein.")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def analyze_package(
    package_dir: Path,
    *,
    scene_threshold: float = 0.3,
    min_clip_duration: float = 15.0,
    max_clip_duration: float = 60.0,
) -> dict[str, object]:
    """Extend an existing ingest ``analysis.json`` with deterministic timeline data."""
    root = package_dir.expanduser().resolve()
    analysis_path = root / "analysis.json"
    metadata = _read_json(root / "metadata.json", "metadata.json")
    existing = _read_json(analysis_path, "analysis.json")
    local_path = metadata.get("local_path")
    if not isinstance(local_path, str):
        raise AnalysisError("metadata.json enthält keinen lokalen Medienpfad.")
    media_path = Path(local_path)
    if not media_path.is_file():
        raise AnalysisError("Lokale Mediendatei aus metadata.json fehlt.")
    duration = _number(metadata.get("duration"), "Mediendauer")
    if duration <= 0:
        raise AnalysisError("Video-Dauer muss größer als null sein.")
    if metadata.get("video_codec") is None:
        raise AnalysisError("Visuelle Szenenanalyse benötigt einen Videostream.")
    transcript_path = root / "transcript.json"
    transcript = (
        _read_json(transcript_path, "transcript.json")
        if transcript_path.is_file()
        else {"segments": []}
    )
    boundaries = detect_scene_boundaries(media_path, threshold=scene_threshold)
    scenes = align_transcript_to_scenes(build_scenes(duration, boundaries), transcript)
    audio_timeline: dict[str, list[dict[str, object]]]
    if metadata.get("audio_codec") is None:
        audio_timeline = {
            "speech_segments": [],
            "silence_segments": [],
            "unknown_segments": [{"start": 0.0, "end": duration, "duration": duration}],
        }
    else:
        try:
            from tools import silence_cutter as silence_tools
        except ModuleNotFoundError:  # Direct `python tools/video_analyze.py` execution.
            import silence_cutter as silence_tools  # type: ignore[no-redef]

        raw_silences = silence_tools.detect_silences(str(media_path))
        audio_timeline = build_audio_timeline(
            duration,
            [
                {"start": item.start, "end": item.end, "duration": item.duration}
                for item in raw_silences
            ],
        )
        audio_timeline["unknown_segments"] = []
    frames = extract_representative_frames(media_path, root, scenes)
    chapters = build_chapter_candidates(scenes, audio_timeline["silence_segments"])
    clips = build_clip_candidates(
        audio_timeline["speech_segments"],
        transcript,
        min_duration=min_clip_duration,
        max_duration=max_clip_duration,
    )
    timeline = {
        "duration": duration,
        "scenes": scenes,
        "speech_segments": audio_timeline["speech_segments"],
        "silence_segments": audio_timeline["silence_segments"],
        "unknown_segments": audio_timeline["unknown_segments"],
        "frames": frames,
        "chapters": chapters,
        "clip_candidates": clips,
    }
    extended = {
        **existing,
        "metadata": metadata,
        "timeline": timeline,
        "scenes": scenes,
        "speech_segments": audio_timeline["speech_segments"],
        "silence_segments": audio_timeline["silence_segments"],
        "chapter_candidates": chapters,
        "clip_candidates": clips,
        "semantic_analysis": {"status": "not_run"},
    }
    _write_json(analysis_path, extended)
    return extended


def main() -> int:
    parser = argparse.ArgumentParser(description="Create deterministic local scene intelligence")
    parser.add_argument(
        "--input", type=Path, required=True, help="Existing ingest analysis-package directory"
    )
    parser.add_argument(
        "--scenes", action="store_true", help="Accepted for explicit CLI workflow clarity"
    )
    parser.add_argument(
        "--align-transcript", action="store_true", help="Accepted for explicit CLI workflow clarity"
    )
    parser.add_argument(
        "--clip-candidates", action="store_true", help="Accepted for explicit CLI workflow clarity"
    )
    parser.add_argument("--scene-threshold", type=float, default=0.3)
    parser.add_argument("--min-clip-duration", type=float, default=15.0)
    parser.add_argument("--max-clip-duration", type=float, default=60.0)
    args = parser.parse_args()
    try:
        report = analyze_package(
            args.input,
            scene_threshold=args.scene_threshold,
            min_clip_duration=args.min_clip_duration,
            max_clip_duration=args.max_clip_duration,
        )
    except AnalysisError as error:
        print(f"Video analysis: FAIL — {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
