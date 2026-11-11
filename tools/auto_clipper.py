#!/usr/bin/env python3
"""YouTube Longform-to-Shorts Auto-Clipper Pipeline.

Repurposes long-form videos (webinars, YouTube videos, client interviews) into
high-retention vertical 9:16 Shorts/Reels (30-60s) using local MLX Whisper,
retention scoring, and the Remotion B2B render engine.

Usage:
    # 1. Inspect & detect top highlight clips (0 € local processing):
    uv run tools/auto_clipper.py --input podcast.mp4 --num-clips 3

    # 2. Extract & reframe vertical clips:
    uv run tools/auto_clipper.py --input podcast.mp4 --cut --autocrop
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "b2b-reel-remotion"
EXPORT_DIR = Path(os.path.expanduser("~/Hannibal/00_INBOX/Zu_Bearbeiten/Videos"))

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

HIGH_RETENTION_KEYWORDS = {
    "fehler", "rendite", "verlust", "millionen", "strategie", "geheimnis",
    "problem", "ergebnis", "wahrheit", "achtung", "warum", "niemals", "wichtig",
    "zinsen", "immobilien", "gewinn", "kapital", "bank", "kaufpreis", "investor"
}


@dataclass
class ClipCandidate:
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    hook_text: str
    full_transcript: str
    retention_score: float
    word_count: int
    type: str = "video"


def score_segment(text: str, duration_sec: float) -> float:
    """Scores clip viability based on keyword density, pacing, and duration."""
    if duration_sec < 20.0 or duration_sec > 65.0:
        return 0.0

    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0

    wpm = (len(words) / duration_sec) * 60.0
    pacing_score = 100.0 - abs(wpm - 150.0)  # Ideal narration pace: ~140-160 WPM
    pacing_score = max(0.0, min(100.0, pacing_score))

    kw_hits = sum(1 for w in words if w in HIGH_RETENTION_KEYWORDS)
    kw_score = min(100.0, (kw_hits / max(1, len(words) * 0.05)) * 100.0)

    # First sentence hook strength
    first_sentence = text.split(".")[0] if "." in text else text[:60]
    hook_question = 20.0 if "?" in first_sentence else 0.0

    return round((pacing_score * 0.4) + (kw_score * 0.4) + hook_question, 1)


def parse_srt_or_segments(srt_content: str) -> list[dict[str, Any]]:
    """Parse SRT text or json into timed segments."""
    segments = []
    blocks = srt_content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3 and "-->" in lines[1]:
            time_match = re.match(
                r"(\d+):(\d+):(\d+)[\.,](\d+)\s+-->\s+(\d+):(\d+):(\d+)[\.,](\d+)", lines[1]
            )
            if time_match:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, time_match.groups())
                start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
                end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
                text = " ".join(lines[2:])
                segments.append({"start": start, "end": end, "text": text})
    return segments


def find_top_clips(
    segments: list[dict[str, Any]],
    target_duration: float = 40.0,
    max_clips: int = 3,
    media_type: str = "video",
) -> list[ClipCandidate]:
    candidates: list[ClipCandidate] = []
    n = len(segments)

    for i in range(n):
        window_text = []
        start_time = segments[i]["start"]
        end_time = start_time

        for j in range(i, n):
            window_text.append(segments[j]["text"])
            end_time = segments[j]["end"]
            dur = end_time - start_time
            if dur >= target_duration * 0.75:
                # Evaluate this window
                combined = " ".join(window_text)
                score = score_segment(combined, dur)
                if score > 40.0:
                    candidates.append(
                        ClipCandidate(
                            index=0,
                            start_sec=round(start_time, 2),
                            end_sec=round(end_time, 2),
                            duration_sec=round(dur, 2),
                            hook_text=combined[:80] + ("..." if len(combined) > 80 else ""),
                            full_transcript=combined,
                            retention_score=score,
                            word_count=len(combined.split()),
                            type=media_type,
                        )
                    )
                if dur >= target_duration * 1.35:
                    break

    # Sort descending by score and eliminate overlapping intervals
    candidates.sort(key=lambda c: c.retention_score, reverse=True)
    selected: list[ClipCandidate] = []
    for cand in candidates:
        overlap = any(
            not (cand.end_sec <= s.start_sec or cand.start_sec >= s.end_sec)
            for s in selected
        )
        if not overlap:
            cand.index = len(selected) + 1
            selected.append(cand)
            if len(selected) >= max_clips:
                break

    return selected


def cut_clip_with_ffmpeg(
    input_video: Path,
    start_sec: float,
    duration_sec: float,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    is_audio = input_video.suffix.lower() in AUDIO_EXTENSIONS
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", str(input_video),
    ]
    if is_audio:
        cmd += ["-vn", "-c:a", "copy" if input_video.suffix.lower() == output_path.suffix.lower() else "aac"]
    else:
        cmd += ["-c:v", "libx264", "-c:a", "aac"]
    cmd += [
        "-avoid_negative_ts", "make_zero",
        str(output_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg cutting failed: {res.stderr}")
    return output_path


def validate_autocrop_input(input_path: Path, autocrop: bool) -> None:
    """Ensure --autocrop is only used with video files containing visual streams."""
    if autocrop and input_path.suffix.lower() in AUDIO_EXTENSIONS:
        raise ValueError(
            f"--autocrop erfordert eine Video-Eingabe (.mp4, .mov, .mkv); "
            f"Audiodateien ({input_path.suffix}) besitzen keine Videospur für Smart-Autocrop."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YouTube Longform-to-Shorts Auto-Clipper")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input video, audio or SRT file.")
    parser.add_argument("--srt", type=Path, help="Optional separate SRT file.")
    parser.add_argument("--num-clips", type=int, default=3, help="Number of highlights to find.")
    parser.add_argument("--target-duration", type=float, default=40.0, help="Target clip duration in seconds.")
    parser.add_argument("--cut", action="store_true", help="Cut raw clips using ffmpeg.")
    parser.add_argument("--autocrop", action="store_true", help="Automatically reframe cut clips to 9:16 vertical using Smart Face-Centering.")
    parser.add_argument("--json", action="store_true", help="Output JSON only.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        validate_autocrop_input(args.input, args.autocrop)
        segments = []
        if args.srt and args.srt.is_file():
            segments = parse_srt_or_segments(args.srt.read_text(encoding="utf-8"))
        elif args.input.suffix.lower() == ".srt":
            segments = parse_srt_or_segments(args.input.read_text(encoding="utf-8"))
        else:
            # Transcribe with MLX Whisper if input is audio/video
            toolkit_root = Path(__file__).resolve().parents[1]
            whisper_bin = toolkit_root / ".venv" / "bin" / "mlx_whisper"
            if not whisper_bin.is_file():
                whisper_bin = Path(sys.executable).parent / "mlx_whisper"

            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                cmd = [
                    str(whisper_bin),
                    str(args.input),
                    "--output-format", "srt",
                    "--output-dir", tmpdir,
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                srt_file = Path(tmpdir) / f"{args.input.stem}.srt"
                if srt_file.is_file():
                    segments = parse_srt_or_segments(srt_file.read_text(encoding="utf-8"))

        if not segments:
            print("Keine Transkript-Segmente gefunden.", file=sys.stderr)
            return 1

        is_audio = args.input.suffix.lower() in AUDIO_EXTENSIONS
        media_type = "audio" if is_audio else "video"
        clips = find_top_clips(
            segments,
            target_duration=args.target_duration,
            max_clips=args.num_clips,
            media_type=media_type,
        )

        if (args.cut or args.autocrop) and (args.input.suffix.lower() in VIDEO_EXTENSIONS or is_audio):
            for c in clips:
                clip_ext = args.input.suffix.lower() if is_audio else ".mp4"
                clip_out = EXPORT_DIR / f"{args.input.stem}_clip_{c.index:02d}{clip_ext}"
                cut_clip_with_ffmpeg(args.input, c.start_sec, c.duration_sec, clip_out)
                if args.autocrop and args.input.suffix.lower() in VIDEO_EXTENSIONS:
                    from tools.smart_autocrop import smart_autocrop_video
                    smart_autocrop_video(
                        input_video=clip_out,
                        output_dir=EXPORT_DIR,
                        profile_name="youtube_short",
                        render_video=True,
                    )

        if args.json:
            print(json.dumps([asdict(c) for c in clips], indent=2, ensure_ascii=False))
        else:
            print("=" * 70)
            print(" YOUTUBE LONG-TO-SHORTS AUTO-CLIPPER")
            print("=" * 70)
            print(f"Quelle:              {args.input}")
            print(f"Gefundene Highlights: {len(clips)}")
            print("-" * 70)
            for c in clips:
                print(f"#{c.index:02d} | Zeit: {c.start_sec}s - {c.end_sec}s ({c.duration_sec}s) | Score: {c.retention_score}/100")
                print(f"     Hook: \"{c.hook_text}\"")
            print("=" * 70)
        return 0
    except Exception as err:
        print(f"Auto-Clipper: ERROR — {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
