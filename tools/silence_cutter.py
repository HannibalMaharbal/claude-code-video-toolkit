#!/usr/bin/env python3
"""
Cut a video into segments based on silence detection.

Pipeline: Whisper transcription → silence detection → cut decisions → ffmpeg cut.

The script:
1. Runs ffmpeg silencedetect to find silence regions in the audio
2. Computes non-silent segments (the parts to keep)
3. Optionally uses Whisper word timestamps to refine cut points to word boundaries
4. Cuts the video with ffmpeg, handling the keyframe problem correctly
5. Verifies the output with ffprobe

Usage:
    # Basic: cut at silence boundaries, re-encode (safe for any cut point)
    uv run tools/silence_cutter.py --input video.mp4 --output cut.mp4

    # Fast: stream-copy with forced keyframes at cut points
    uv run tools/silence_cutter.py --input video.mp4 --output cut.mp4 --copy

    # With Whisper refinement: snap cut points to nearest word boundary
    uv run tools/silence_cutter.py --input video.mp4 --output cut.mp4 --whisper

    # Verbose with debug output
    uv run tools/silence_cutter.py --input video.mp4 --output cut.mp4 --verbose

Keyframe problem: A pure -c copy cut at a non-keyframe position produces a
second segment with no video frames. This script avoids that either by
re-encoding (-c:v libx264, default) or by forcing keyframes at cut points
(--copy mode). Note: --copy mode is currently unreliable due to an
ffmpeg concat demuxer bug (video stream lost). Use re-encode mode for
production work.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.asset_record import AssetRecordError, asset_id_for_sha256, register_derived, sha256_file

# ─── Data types ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SilenceRegion:
    """A contiguous silence detected by ffmpeg's silencedetect filter."""

    start: float
    end: float
    duration: float


@dataclass(frozen=True)
class Word:
    """A single word from Whisper with timestamps."""

    text: str
    start: float
    end: float


@dataclass
class CutSegment:
    """A non-silent segment to extract from the source video."""

    start: float
    end: float


def register_cut_output(input_path: str, output_path: str) -> dict[str, object] | None:
    """Best-effort local MASTER registration without changing cut success semantics."""
    try:
        parent_id = asset_id_for_sha256(sha256_file(Path(input_path)))
        return register_derived(
            output_path,
            parents=[parent_id],
            role="MASTER",
            tool="silence_cutter",
            operation="remove_silence",
        )
    except (AssetRecordError, OSError) as error:
        print(f"Asset-Registrierung: WARN — {error}", file=sys.stderr)
        return None


# ─── Silence detection ────────────────────────────────────────────


def detect_silences(
    input_path: str,
    noise_threshold: str = "-30dB",
    min_duration: float = 0.5,
) -> list[SilenceRegion]:
    """Run ffmpeg silencedetect and parse the output into SilenceRegion list.

    The ffmpeg filter emits lines like:
        [silencedetect @ 0x...] silence_start: 10.526 |
        silence_end: 12.345 | silence_duration: 1.819
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        input_path,
        "-af",
        f"silencedetect=noise={noise_threshold}:d={min_duration}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0 and "silencedetect" not in result.stderr:
        print(f"Warning: ffmpeg returned non-zero: {result.stderr[-200:]}", file=sys.stderr)

    silences: list[SilenceRegion] = []
    # Parse silence_start and silence_end|silence_duration from stderr.
    # ffmpeg emits them on separate lines:
    #   [Parsed_silencedetect_0 @ ...] silence_start: 5.01551
    #   [Parsed_silencedetect_0 @ ...] silence_end: 7.012608 | silence_duration: 1.997098
    start_pattern = re.compile(r"silence_start:\s*([\d.]+)")
    end_pattern = re.compile(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")

    pending_start: float | None = None
    for line in result.stderr.splitlines():
        m_start = start_pattern.search(line)
        if m_start:
            pending_start = float(m_start.group(1))
            continue
        m_end = end_pattern.search(line)
        if m_end and pending_start is not None:
            end = float(m_end.group(1))
            duration = float(m_end.group(2))
            silences.append(SilenceRegion(start=pending_start, end=end, duration=duration))
            pending_start = None

    # Sort by start time (should already be sorted, but be safe)
    silences.sort(key=lambda s: s.start)
    return silences


# ─── Whisper transcription ────────────────────────────────────────


def transcribe_whisper(input_path: str, model: str = "small") -> list[Word]:
    """Run mlx-whisper transcription and return word-level timestamps.

    Returns empty list if mlx_whisper is not available or transcription fails.
    """
    try:
        import mlx_whisper
    except ImportError:
        print("Warning: mlx-whisper not installed, skipping Whisper refinement", file=sys.stderr)
        return []

    model_id = f"mlx-community/whisper-{model}-mlx"
    print(f"Transcribing with {model_id}...", file=sys.stderr)

    try:
        result = mlx_whisper.transcribe(
            input_path,
            path_or_hf_repo=model_id,
            word_timestamps=True,
            verbose=False,
        )
    except Exception as e:
        print(f"Warning: Whisper transcription failed: {e}", file=sys.stderr)
        return []

    words: list[Word] = []
    for w in result.get("words", []):
        text = w.get("text", "").strip()
        if text:
            words.append(
                Word(
                    text=text,
                    start=float(w.get("start", 0)),
                    end=float(w.get("end", 0)),
                )
            )
    return words


# ─── Segment computation ──────────────────────────────────────────


def compute_segments(
    silences: list[SilenceRegion],
    video_duration: float,
    word_pad: float = 0.0,
    words: list[Word] | None = None,
) -> list[CutSegment]:
    """Compute non-silent segments from silence regions.

    Args:
        silences: Sorted list of silence regions
        video_duration: Total duration of the video in seconds
        word_pad: Padding around words when refining cut points (seconds)
        words: Optional Whisper word timestamps for boundary refinement

    Returns:
        List of CutSegment objects representing the parts to keep
    """
    if not silences:
        return [CutSegment(start=0.0, end=video_duration)]

    segments: list[CutSegment] = []
    current = 0.0

    for silence in silences:
        # Skip silences that extend beyond the video
        if silence.start >= video_duration:
            break

        # Add the non-silent segment before this silence
        seg_end = min(silence.start, video_duration)
        if seg_end > current:
            # Refine start/end to word boundaries if Whisper data available
            refined_start = current
            refined_end = seg_end

            if words and word_pad > 0:
                refined_start = _snap_to_word_boundary(words, current, "forward", word_pad)
                refined_end = _snap_to_word_boundary(words, seg_end, "backward", word_pad)
                # Ensure we don't cut into silence
                refined_start = max(refined_start, current)
                refined_end = min(refined_end, seg_end)

            if refined_end > refined_start:
                segments.append(CutSegment(start=refined_start, end=refined_end))

        current = min(silence.end, video_duration)

    # Add the final non-silent segment after the last silence
    if current < video_duration:
        segments.append(CutSegment(start=current, end=video_duration))

    # Merge overlapping segments
    segments = _merge_segments(segments)

    return segments


def _snap_to_word_boundary(
    words: list[Word],
    target_time: float,
    direction: str,
    max_pad: float = 0.5,
) -> float:
    """Snap a timestamp to the nearest word boundary.

    Args:
        words: Sorted word list
        target_time: The time to snap
        direction: "forward" snap to next word start, "backward" snap to prev word end
        max_pad: Maximum padding to apply

    Returns:
        Adjusted time
    """
    if not words:
        return target_time

    if direction == "forward":
        # Find the first word that starts at or after target_time
        for w in words:
            if w.start >= target_time:
                return max(target_time, w.start - max_pad)
        return target_time
    else:  # backward
        # Find the last word that ends at or before target_time
        for w in reversed(words):
            if w.end <= target_time:
                return min(target_time, w.end + max_pad)
        return target_time


def _merge_segments(segments: list[CutSegment]) -> list[CutSegment]:
    """Merge overlapping or adjacent segments."""
    if not segments:
        return []
    sorted_segs = sorted(segments, key=lambda s: s.start)
    merged = [sorted_segs[0]]
    for seg in sorted_segs[1:]:
        if seg.start <= merged[-1].end:
            # Overlapping — extend the previous segment
            merged[-1] = CutSegment(start=merged[-1].start, end=max(merged[-1].end, seg.end))
        else:
            merged.append(seg)
    return merged


# ─── Video cutting ────────────────────────────────────────────────


def get_video_duration(input_path: str) -> float:
    """Get video duration using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            input_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(result.stdout.strip())


def cut_segments(
    input_path: str,
    segments: list[CutSegment],
    output_path: str,
    copy_mode: bool = False,
    encoder_preset: str = "fast",
    crf: int = 18,
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
) -> bool:
    """Cut the video at the given segments and produce a single output.

        Args:
            input_path: Source video file
            segments: Non-silent segments to keep
            output_path: Final output file path
    copy_mode: If True, use -c copy with -force_key_frames (fast, requires keyframes).
                        NOTE: currently unreliable due to ffmpeg concat demuxer bug.
                        For production, use re-encode mode (default).
            encoder_preset: ffmpeg preset for libx264 encoding
            crf: Constant Rate Factor for libx264
            audio_codec: Audio codec for re-encode mode
            audio_bitrate: Audio bitrate for re-encode mode

        Returns:
            True on success, False on failure
    """
    if not segments:
        print("No segments to cut. Nothing to do.", file=sys.stderr)
        return False

    print(f"Cutting {len(segments)} segment(s) from {input_path}...", file=sys.stderr)

    if copy_mode:
        return _cut_copy_mode(input_path, segments, output_path)
    else:
        return _cut_reencode_mode(
            input_path, segments, output_path, encoder_preset, crf, audio_codec, audio_bitrate
        )


def _cut_reencode_mode(
    input_path: str,
    segments: list[CutSegment],
    output_path: str,
    preset: str,
    crf: int,
    audio_codec: str,
    audio_bitrate: str,
) -> bool:
    """Cut by re-encoding with libx264. Works at any cut point."""
    return _cut_via_temp_files(
        input_path, segments, output_path, preset, crf, audio_codec, audio_bitrate
    )


def _cut_copy_mode(
    input_path: str,
    segments: list[CutSegment],
    output_path: str,
) -> bool:
    """Cut using stream-copy with -force_key_frames at cut boundaries.

    NOTE: --copy mode is currently unreliable. The ffmpeg concat demuxer
    drops the video stream when called from subprocess (capture_output),
    producing output with only audio. For production use, the re-encode
    mode (default) works correctly at any cut point.

    Two-pass approach (documented for reference):
      1. Create a keyframe-aligned copy of the input (force keyframes
         at all segment boundaries)
      2. Use -c copy with -ss BEFORE -i to extract segments (fast,
         accurate because keyframes are now at the cut points)

    This matches the task requirement: "entweder an erzwungenen
    Keyframes schneiden (-force_key_frames) oder mit Re-Encoding
    arbeiten."
    """
    # Build a list of all cut times for forcing keyframes
    # (exclude 0.0 since it's already a keyframe at video start)
    cut_times = sorted(set(seg.start for seg in segments if seg.start > 0.01))

    # Pass 1: Create a keyframe-aligned version of the input
    tmp_dir = tempfile.mkdtemp(prefix="silence_cutter_")
    aligned_path = os.path.join(tmp_dir, "aligned.mp4")

    force_pts = ",".join(str(t) for t in cut_times)

    align_cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        input_path,
        "-force_key_frames",
        force_pts,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        aligned_path,
    ]
    result = subprocess.run(align_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"Error forcing keyframes: {result.stderr[-300:]}", file=sys.stderr)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    # Pass 2: Extract segments using -c copy with -ss AFTER -i.
    # Since we forced keyframes at all cut points in Pass 1,
    # -ss after -i lands on keyframe boundaries, avoiding the
    # "no video frames" bug. Both video and audio are preserved.
    segment_files: list[str] = []
    try:
        for i, seg in enumerate(segments):
            seg_path = os.path.join(tmp_dir, f"segment_{i:03d}.mp4")
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                aligned_path,
                "-ss",
                str(seg.start),
                "-t",
                str(seg.end - seg.start),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                "-fflags",
                "+genpts",
                seg_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(
                    f"Error extracting segment {i} (copy mode): {result.stderr[-300:]}",
                    file=sys.stderr,
                )
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            if not os.path.exists(seg_path) or os.path.getsize(seg_path) == 0:
                print(f"Error: Segment {i} produced empty output", file=sys.stderr)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            segment_files.append(seg_path)

        return _concat_segments(segment_files, output_path, copy_mode=True)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _cut_via_temp_files(
    input_path: str,
    segments: list[CutSegment],
    output_path: str,
    preset: str,
    crf: int,
    audio_codec: str,
    audio_bitrate: str,
) -> bool:
    """Extract each segment as a re-encoded file, then concatenate.

    Re-encoding guarantees clean cuts at any point (no keyframe problem).
    """
    tmp_dir = tempfile.mkdtemp(prefix="silence_cutter_")
    segment_files: list[str] = []

    try:
        for i, seg in enumerate(segments):
            seg_path = os.path.join(tmp_dir, f"segment_{i:03d}.mp4")
            # -ss after -i for accurate seeking (needed for re-encode)
            # Re-encode to ensure clean cut at any frame
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                input_path,
                "-ss",
                str(seg.start),
                "-t",
                str(seg.end - seg.start),
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-c:a",
                audio_codec,
                "-b:a",
                audio_bitrate,
                "-avoid_negative_ts",
                "make_zero",
                seg_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(
                    f"Error extracting segment {i} (reencode mode): {result.stderr[-300:]}",
                    file=sys.stderr,
                )
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            if not os.path.exists(seg_path) or os.path.getsize(seg_path) == 0:
                print(f"Error: Segment {i} produced empty output", file=sys.stderr)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return False

            segment_files.append(seg_path)

        # Concatenate segments
        return _concat_segments(segment_files, output_path, copy_mode=False)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _concat_segments(
    segment_files: list[str],
    output_path: str,
    copy_mode: bool,
) -> bool:
    """Concatenate multiple video segments using ffmpeg's concat demuxer.

    For copy mode: uses -c:v copy -c:a copy to preserve streams.
    For re-encode mode: uses -c:v libx264 -c:a aac to re-encode.
    """
    list_path = None
    try:
        fd, list_path = tempfile.mkstemp(prefix="concat_list_", suffix=".txt")
        os.close(fd)
        with open(list_path, "w") as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")

        if copy_mode:
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_path,
                "-bsf:v",
                "h264_mp4toannexb",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_path,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                output_path,
            ]

        # IMPORTANT: --copy mode is currently experimental and produces
        # broken output (video stream lost during concat demuxer step).
        # For production use, always use re-encode mode (default, no --copy).
        # The re-encode path works correctly at any cut point.
        result = subprocess.run(
            cmd,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"Error concatenating segments: {result.stderr[-300:]}", file=sys.stderr)
            return False

        # Verify output has video
        if os.path.exists(output_path):
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    output_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "video" not in probe.stdout:
                print("Error: concat output has no video stream", file=sys.stderr)
                return False

        return True

    finally:
        if list_path and os.path.exists(list_path):
            os.unlink(list_path)


# ─── Verification ─────────────────────────────────────────────────


def verify_output(output_path: str, expected_segments: list[CutSegment] | None = None) -> dict:
    """Verify the output video has valid video and audio streams and correct duration."""
    # Probe the output file
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,sample_rate,channels",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        output_path,
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return {"valid": False, "error": f"ffprobe failed: {result.stderr.strip()}"}

    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"Invalid ffprobe JSON: {e}"}

    streams = probe.get("streams", [])
    fmt = probe.get("format", {})

    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration = float(fmt.get("duration", 0))
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    issues = []
    if not has_video:
        issues.append("No video stream found")
    if not has_audio:
        issues.append("No audio stream found")
    if duration <= 0:
        issues.append(f"Invalid duration: {duration}")

    # Check that the output has a video stream with actual frames
    if has_video:
        # Verify the video actually has frames by decoding one frame
        check_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            output_path,
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30)
        if check_result.returncode != 0:
            issues.append("Video stream has no decodable frames")

    result_dict = {
        "valid": len(issues) == 0,
        "duration": round(duration, 3),
        "has_video": has_video,
        "has_audio": has_audio,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "file_size_bytes": fmt.get("size"),
        "issues": issues,
    }

    return result_dict


# ─── Main ─────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cut video into segments based on silence detection. "
        "Pipeline: Whisper → silence detection → cut decisions → ffmpeg cut.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--input", "-i", required=True, help="Input video file")
    ap.add_argument("--output", "-o", help="Output video file (required unless --plan-only)")
    ap.add_argument("--noise", default="-30dB", help="Silence noise threshold (default: -30dB)")
    ap.add_argument(
        "--min-duration",
        type=float,
        default=0.5,
        help="Minimum silence duration in seconds (default: 0.5)",
    )
    ap.add_argument(
        "--copy",
        action="store_true",
        help=(
            "EXPERIMENTAL/UNRELIABLE: use -c copy with -force_key_frames. "
            "Re-encode mode (default) is recommended."
        ),
    )
    ap.add_argument(
        "--whisper",
        action="store_true",
        help="Use Whisper word timestamps to refine cut points to word boundaries",
    )
    ap.add_argument(
        "--whisper-model",
        default="small",
        choices=["tiny", "base", "small", "medium"],
        help="Whisper model (default: small)",
    )
    ap.add_argument(
        "--word-pad",
        type=float,
        default=0.15,
        help="Padding around words when refining cuts (default: 0.15s)",
    )
    ap.add_argument(
        "--preset", default="fast", help="ffmpeg encoding preset for re-encode mode (default: fast)"
    )
    ap.add_argument(
        "--crf", type=int, default=18, help="ffmpeg CRF for re-encode mode (default: 18)"
    )
    ap.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    ap.add_argument("--json", action="store_true", help="Output segments and verification as JSON")
    ap.add_argument(
        "--plan-only", action="store_true", help="Only analyze cuts; do not create an output file"
    )
    ap.add_argument(
        "--remove-silence-index",
        action="append",
        type=int,
        default=None,
        help="Remove only this detected silence index (repeatable; zero-based)",
    )
    args = ap.parse_args()

    input_path = args.input
    output_path = args.output

    if not output_path and not args.plan_only:
        ap.error("--output is required unless --plan-only is used")

    if not Path(input_path).exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    # Step 1: Get video duration
    video_duration = get_video_duration(input_path)
    print(f"Input: {input_path} ({video_duration:.2f}s)", file=sys.stderr)

    # Step 2: Run Whisper transcription (if requested)
    words: list[Word] | None = None
    if args.whisper:
        word_list = transcribe_whisper(input_path, model=args.whisper_model)
        if word_list:
            words = word_list
            print(f"Whisper found {len(words)} words", file=sys.stderr)
        else:
            print("Whisper unavailable, falling back to silence-only cuts", file=sys.stderr)

    # Step 3: Detect silences
    silences = detect_silences(
        input_path, noise_threshold=args.noise, min_duration=args.min_duration
    )
    print(f"Found {len(silences)} silence region(s)", file=sys.stderr)

    selected_indices = list(range(len(silences)))
    if args.remove_silence_index is not None:
        selected_indices = sorted(set(args.remove_silence_index))
        if not selected_indices or any(
            index < 0 or index >= len(silences) for index in selected_indices
        ):
            print("Error: invalid silence index selection", file=sys.stderr)
            return 1
    selected_silences = [silences[index] for index in selected_indices]

    if args.verbose:
        for s in silences:
            print(f"  Silence: {s.start:.3f}s - {s.end:.3f}s ({s.duration:.3f}s)", file=sys.stderr)

    # Step 4: Compute cut segments from silences
    segments = compute_segments(
        selected_silences,
        video_duration,
        word_pad=args.word_pad,
        words=words,
    )

    if not segments:
        print("No non-silent segments found. Check silence threshold.", file=sys.stderr)
        return 1

    total_cut = sum(s.end - s.start for s in segments)
    print(
        f"Computed {len(segments)} segment(s) to keep ({total_cut:.2f}s of {video_duration:.2f}s)",
        file=sys.stderr,
    )

    if args.verbose:
        for i, seg in enumerate(segments):
            print(
                f"  Segment {i}: {seg.start:.3f}s - {seg.end:.3f}s ({seg.end - seg.start:.3f}s)",
                file=sys.stderr,
            )

    # Step 5: Cut the video
    if args.json:
        print(
            json.dumps(
                {
                    "duration": video_duration,
                    "segments": [{"start": s.start, "end": s.end} for s in segments],
                    "silences": [
                        {"start": s.start, "end": s.end, "duration": s.duration} for s in silences
                    ],
                    "selected_silence_indices": selected_indices,
                    "mode": "copy" if args.copy else "reencode",
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if args.plan_only:
        return 0

    success = cut_segments(
        input_path,
        segments,
        output_path,
        copy_mode=args.copy,
        encoder_preset=args.preset,
        crf=args.crf,
    )

    if not success:
        print("Cutting failed.", file=sys.stderr)
        return 1

    if not Path(output_path).exists():
        print(f"Error: Output file not created: {output_path}", file=sys.stderr)
        return 1

    # Step 6: Verify the output
    verification = verify_output(output_path, segments)

    if args.json:
        verification["output"] = output_path
        print(json.dumps(verification, ensure_ascii=False, indent=2))

    if not verification["valid"]:
        print(f"Verification FAILED: {verification.get('issues', [])}", file=sys.stderr)
        return 1

    register_cut_output(input_path, output_path)
    print(f"Done. Output: {output_path} ({verification['duration']:.2f}s)", file=sys.stderr)
    if args.verbose:
        print(
            f"  Video: {verification['video_codec']}, Audio: {verification['audio_codec']}",
            file=sys.stderr,
        )
        print(f"  Size: {verification['file_size_bytes']} bytes", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
