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
import contextlib
import json
import re
import subprocess
import sys
from pathlib import Path


def _segments_from_transcript(payload: object) -> list[dict[str, object]]:
    """Accept mlx-whisper's result object or the existing timestamped list format."""
    if isinstance(payload, dict):
        segments = payload.get("segments")
    else:
        segments = payload
    if not isinstance(segments, list):
        raise ValueError(
            "Transcript muss eine Segmentliste oder ein Objekt mit 'segments' enthalten."
        )
    if not all(isinstance(segment, dict) for segment in segments):
        raise ValueError("Jedes Transcript-Segment muss ein Objekt sein.")
    return segments


def _as_seconds(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        raise ValueError("Timestamp muss numerisch sein.")
    return float(value)


def _last_sentence_boundary(text: str, limit: int) -> int | None:
    for index in range(limit - 1, -1, -1):
        char = text[index]
        if char == ".":
            after = text[index + 1 :].strip()
            if after and after[0].isupper():
                return index
        elif char in ("!", "?", "\u2026"):
            return index
    return None


def _last_clause_boundary(text: str, limit: int) -> int | None:
    for index in range(limit - 1, -1, -1):
        char = text[index]
        if char in ",;:\u2014\u2013":
            if char == "," and index > 0 and index < len(text) - 1:
                if text[index - 1].isdigit() and text[index + 1].isdigit():
                    continue
            return index
    return None


def _last_word_boundary(text: str, limit: int) -> int | None:
    for index in range(limit - 1, -1, -1):
        if text[index].isspace():
            return index
    return None


def _split_cue_text(text: str, max_chars: int) -> list[str]:
    """Split a too-long cue into chunks up to max_chars.

    Break points are preferred in this order: sentence-ending punctuation,
    clause punctuation, then word boundaries. Words are never broken in the
    middle; a single word longer than max_chars is kept verbatim as its own
    chunk so the deterministic QC can flag it instead of corrupting it.
    """
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        limit = min(max_chars, len(remaining))
        boundary = _last_sentence_boundary(remaining, limit)
        if boundary is None:
            boundary = _last_clause_boundary(remaining, limit)
        if boundary is None:
            boundary = _last_word_boundary(remaining, limit)
        if boundary is None:
            boundary = remaining.find(" ")
            if boundary == -1:
                chunks.append(remaining)
                remaining = ""
            else:
                chunks.append(remaining[:boundary].strip())
                remaining = remaining[boundary + 1 :].strip()
        else:
            chunks.append(remaining[: boundary + 1].strip())
            remaining = remaining[boundary + 1 :].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _split_oversized_cue(
    cue: dict[str, object], max_chars: int
) -> list[dict[str, object]]:
    """Subdivide one too-long cue, spreading its time range proportionally.

    Sub-cues stay contiguous (no artificial overlaps), stay within the
    original cue's time range, keep start < end and preserve the text
    verbatim in order.
    """
    text = str(cue.get("text", "")).strip()
    start = _as_seconds(cue["start"])
    end = _as_seconds(cue["end"])
    if len(text) <= max_chars or end <= start:
        return [cue]
    chunks = _split_cue_text(text, max_chars)
    if len(chunks) <= 1:
        return [cue]
    total_chars = sum(len(chunk) for chunk in chunks)
    duration = end - start
    chunk_count = len(chunks)
    minimum_duration = 0.1
    weights = [len(chunk) / total_chars for chunk in chunks]
    available_duration = duration - minimum_duration * chunk_count
    if available_duration >= 0:
        durations = [minimum_duration + available_duration * weight for weight in weights]
    else:
        # The source range cannot satisfy the QC minimum for every cue. Keep
        # all cues inside it and let QC report the unavoidable short duration.
        durations = [duration * weight for weight in weights]
    sub: list[dict[str, object]] = []
    running = start
    for chunk, chunk_duration in zip(chunks, durations):
        chunk_end = running + chunk_duration
        if chunk_end <= running:
            chunk_end = min(start + duration, running + 0.001)
        sub.append({"text": chunk, "start": running, "end": chunk_end})
        running = chunk_end
    sub[-1]["end"] = end
    return sub


def build_subtitle_cues(
    payload: object, max_chars: int = 42, max_duration: float = 6.0
) -> list[dict[str, object]]:
    """Compose timestamped transcript segments into readable subtitle cues."""
    if max_chars < 1 or max_duration <= 0:
        raise ValueError("max_chars und max_duration müssen positiv sein.")

    cues: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for segment in _segments_from_transcript(payload):
        text = str(segment.get("text", "")).strip()
        try:
            start = _as_seconds(segment["start"])
            end = _as_seconds(segment["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Jedes Segment benötigt numerische start/end-Timestamps.") from error
        candidate = text if current is None else f"{current['text']} {text}".strip()
        if current is not None and (
            len(candidate) > max_chars or end - _as_seconds(current["start"]) > max_duration
        ):
            cues.append(current)
            current = None
            candidate = text
        if current is None:
            current = {"text": candidate, "start": start, "end": end}
        else:
            current["text"] = candidate
            current["end"] = end
    if current is not None:
        cues.append(current)
    subdivided: list[dict[str, object]] = []
    for cue in cues:
        subdivided.extend(_split_oversized_cue(cue, max_chars))
    return subdivided


def _timestamp(seconds: float, separator: str) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{separator}{milliseconds:03}"


def validate_subtitle_cues(
    cues: list[dict[str, object]],
    max_chars: int = 42,
    min_duration: float = 0.1,
    max_duration: float = 8.0,
) -> list[str]:
    """Return all deterministic SRT/VTT QC failures; an empty list is PASS."""
    errors: list[str] = []
    previous_end: float | None = None
    for index, cue in enumerate(cues, start=1):
        text = str(cue.get("text", "")).strip()
        try:
            start = _as_seconds(cue["start"])
            end = _as_seconds(cue["end"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"Cue {index}: kaputte Timestamps.")
            continue
        if not text:
            errors.append(f"Cue {index}: leeren Text erkannt.")
        if start < 0 or start >= end:
            errors.append(f"Cue {index}: Startzeit muss vor Endzeit liegen.")
        if previous_end is not None and start < previous_end:
            errors.append(f"Cue {index}: überschneidet vorherigen Cue.")
        duration = end - start
        if duration < min_duration:
            errors.append(f"Cue {index}: extrem kurze Dauer ({duration:.3f}s).")
        if duration > max_duration:
            errors.append(f"Cue {index}: extrem lange Dauer ({duration:.3f}s).")
        if any(len(line) > max_chars for line in text.splitlines()):
            errors.append(f"Cue {index}: Zeile länger als {max_chars} Zeichen.")
        previous_end = end
    return errors


def write_srt(cues: list[dict[str, object]], output_path: Path) -> None:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        start = _timestamp(_as_seconds(cue["start"]), ",")
        end = _timestamp(_as_seconds(cue["end"]), ",")
        blocks.append(f"{index}\n{start} --> {end}\n{cue['text']}")
    output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_vtt(cues: list[dict[str, object]], output_path: Path) -> None:
    blocks = []
    for cue in cues:
        start = _timestamp(_as_seconds(cue["start"]), ".")
        end = _timestamp(_as_seconds(cue["end"]), ".")
        blocks.append(f"{start} --> {end}\n{cue['text']}")
    output_path.write_text("WEBVTT\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")


def _parse_subtitle_timestamp(value: str, separator: str) -> float | None:
    match = re.fullmatch(
        rf"(\d{{2,}}):(\d{{2}}):(\d{{2}}){re.escape(separator)}(\d{{3}})", value
    )
    if match is None:
        return None
    hours, minutes, seconds, milliseconds = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        return None
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def validate_subtitle_file(path: Path) -> list[str]:
    """Validate SRT/WebVTT structure and cue quality without external software."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return [f"Subtitle-Datei nicht lesbar: {error}"]

    is_vtt = path.suffix.lower() == ".vtt"
    errors: list[str] = []
    if is_vtt:
        content = content.removeprefix("\ufeff")
        if not content.startswith("WEBVTT\n"):
            return ["VTT: fehlender WEBVTT-Header."]
        content = content.removeprefix("WEBVTT\n").lstrip("\n")
    elif path.suffix.lower() != ".srt":
        return ["Subtitle-Datei muss die Endung .srt oder .vtt haben."]

    blocks = [block for block in content.strip().split("\n\n") if block.strip()]
    if not blocks:
        return ["Subtitle-Datei enthält keine Cues."]

    separator = "." if is_vtt else ","
    cues: list[dict[str, object]] = []
    for index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if is_vtt:
            timestamp_index = 0 if " --> " in lines[0] else 1
            if timestamp_index == 1 and len(lines) < 3:
                errors.append(f"Cue {index}: ungültige .vtt-Timestamp-Zeile.")
                continue
        else:
            timestamp_index = 1
            if not lines or lines[0] != str(index):
                errors.append(f"Cue {index}: ungültige SRT-Nummerierung.")
        timestamp_line = lines[timestamp_index] if len(lines) > timestamp_index else ""
        text_lines = lines[timestamp_index + 1 :]
        try:
            start_text, end_text = timestamp_line.split(" --> ", maxsplit=1)
        except ValueError:
            errors.append(f"Cue {index}: ungültige {'.vtt' if is_vtt else '.srt'}-Timestamp-Zeile.")
            continue
        start = _parse_subtitle_timestamp(start_text, separator)
        end = _parse_subtitle_timestamp(end_text, separator)
        if start is None or end is None:
            errors.append(f"Cue {index}: ungültige {'.vtt' if is_vtt else '.srt'}-Timestamp-Zeile.")
            continue
        cues.append({"text": "\n".join(text_lines), "start": start, "end": end})
    return errors + validate_subtitle_cues(cues)


def _escape_subtitle_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ffmpeg_supports_subtitle_burn_in() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return bool(re.search(r"\bsubtitles\b", result.stdout))


def burn_in_subtitles(video_path: Path, subtitle_path: Path, output_path: Path) -> None:
    """Burn a locally QC-passed SRT/VTT file into a video using installed FFmpeg."""
    if not video_path.is_file():
        raise ValueError(f"Video-Datei nicht gefunden: {video_path}")
    errors = validate_subtitle_file(subtitle_path)
    if errors:
        raise ValueError("Subtitle QC fehlgeschlagen: " + "; ".join(errors))
    if not _ffmpeg_supports_subtitle_burn_in():
        raise RuntimeError("Der installierte FFmpeg-Build enthält keinen subtitles/libass-Filter.")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"subtitles=filename='{_escape_subtitle_filter_path(subtitle_path)}'",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-c:a",
                "copy",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg ist für den Burn-In nicht verfügbar.") from error
    except subprocess.CalledProcessError as error:
        detail = (
            error.stderr.strip().splitlines()[-1]
            if error.stderr
            else "unbekannter FFmpeg-Fehler"
        )
        raise RuntimeError(f"FFmpeg-Burn-In fehlgeschlagen: {detail}") from error


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
        with contextlib.redirect_stdout(sys.stderr):
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", "-i", help="Audio or video file")
    source.add_argument(
        "--transcript-json",
        type=Path,
        help="Existing timestamped transcript JSON (mlx-whisper object or segment list)",
    )
    source.add_argument(
        "--subtitle-file",
        type=Path,
        help="Existing .srt or .vtt file to QC (optionally burn into a video)",
    )
    parser.add_argument("--model", "-m", default="small",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model (default: small)")
    parser.add_argument(
        "--language", "-l", help="Language code (e.g. 'en', 'de'). Auto if not set."
    )
    parser.add_argument("--output", "-o", help="Save transcript to file")
    parser.add_argument("--words", action="store_true", default=True,
                        help="Include word-level timestamps (default: on)")
    parser.add_argument("--json", action="store_true", help="Output full JSON result")
    parser.add_argument("--srt", type=Path, help="Write validated SRT subtitles")
    parser.add_argument("--vtt", type=Path, help="Write validated WebVTT subtitles")
    parser.add_argument("--subtitle-qc", action="store_true", help="Run deterministic subtitle QC")
    parser.add_argument("--burn-in", type=Path, help="Video to receive QC-passed burned subtitles")
    parser.add_argument("--burn-in-output", type=Path, help="Output path for --burn-in")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    if (args.burn_in is None) != (args.burn_in_output is None):
        parser.error("--burn-in and --burn-in-output must be used together")

    if args.subtitle_file:
        if args.srt or args.vtt:
            parser.error("--subtitle-file cannot be combined with --srt or --vtt")
        errors = validate_subtitle_file(args.subtitle_file)
        if errors:
            print("Subtitle QC: FAIL", file=sys.stderr)
            print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
            sys.exit(1)
        if args.burn_in:
            try:
                burn_in_subtitles(args.burn_in, args.subtitle_file, args.burn_in_output)
            except (RuntimeError, ValueError) as error:
                print(f"Burn-In error: {error}", file=sys.stderr)
                sys.exit(1)
        if not args.quiet:
            print("Subtitle QC: PASS", file=sys.stderr)
        return

    if args.transcript_json:
        try:
            result = json.loads(args.transcript_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Transcript JSON error: {error}", file=sys.stderr)
            sys.exit(1)
    else:
        result = transcribe(
            args.input,
            model=args.model,
            language=args.language,
            word_timestamps=args.words,
            verbose=not args.quiet,
        )

    if not result:
        sys.exit(1)

    if args.srt or args.vtt or args.subtitle_qc:
        try:
            cues = build_subtitle_cues(result)
            errors = validate_subtitle_cues(cues)
        except ValueError as error:
            cues = []
            errors = [str(error)]
        if not cues and not errors:
            errors.append(
                "Transcript enthält keine Segmente — keine Untertitel erzeugt."
            )
        if errors:
            print("Subtitle QC: FAIL", file=sys.stderr)
            print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
            sys.exit(1)
        if args.srt:
            write_srt(cues, args.srt)
            errors.extend(validate_subtitle_file(args.srt))
        if args.vtt:
            write_vtt(cues, args.vtt)
            errors.extend(validate_subtitle_file(args.vtt))
        if errors:
            print("Subtitle QC: FAIL", file=sys.stderr)
            print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
            sys.exit(1)
        if args.burn_in:
            subtitle_path = args.srt or args.vtt
            if subtitle_path is None:
                parser.error("--burn-in requires --srt, --vtt, or --subtitle-file")
            try:
                burn_in_subtitles(args.burn_in, subtitle_path, args.burn_in_output)
            except (RuntimeError, ValueError) as error:
                print(f"Burn-In error: {error}", file=sys.stderr)
                sys.exit(1)
        if args.subtitle_qc and not args.quiet:
            print(f"Subtitle QC: PASS ({len(cues)} cues)", file=sys.stderr)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if isinstance(result, dict):
            text = str(result.get("text", "")).strip()
        else:
            text = " ".join(str(segment.get("text", "")).strip() for segment in result).strip()
        print(text)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            if not args.quiet:
                print(f"Saved: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
