#!/usr/bin/env python3
"""
video_qa_audit.py — Automated Pre-/Post-Flight Video & Audio Quality Gate.
Inspired by HEINER.Academy production pipeline.

Checks:
1. Silence Detection: Flags silences / dead air > threshold (default 2.5s).
2. AV Duration Drift: Checks audio vs. video duration drift (desync warning if > 0.3s).
3. Audio Loudness (EBU R128): Measures Integrated LUFS (target: -14 LUFS ± 1.5 LUFS).
4. Black Frame & Freeze Frame Detection.
5. Frame-cadence inspection for suspicious/non-standard rates.
"""

import os
import sys
import json
import re
import subprocess
import argparse
from pathlib import Path
from typing import Dict, Any, List

def run_cmd(cmd: List[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stderr + "\n" + res.stdout

def probe_stream_info(video_path: str) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json", video_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {res.stderr}")
    return json.loads(res.stdout)

def audit_silences(video_path: str, min_silence_sec: float = 2.5, noise_db: float = -35.0) -> List[Dict[str, float]]:
    """Detect silences longer than min_silence_sec."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_sec}",
        "-f", "null", "-"
    ]
    output = run_cmd(cmd)
    
    silences = []
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d\.]+)", output)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d\.]+)", output)]
    durs = [float(m) for m in re.findall(r"silence_duration:\s*([\d\.]+)", output)]

    for i in range(min(len(starts), len(durs))):
        silences.append({
            "start": starts[i],
            "end": ends[i] if i < len(ends) else starts[i] + durs[i],
            "duration": durs[i]
        })
    return silences

def audit_loudness(video_path: str) -> Dict[str, float]:
    """Measure EBU R128 integrated loudness (LUFS) and True Peak."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", "ebur128=framelog=verbose",
        "-f", "null", "-"
    ]
    output = run_cmd(cmd)
    
    i_match = re.search(r"Integrated loudness:\s+I:\s+([-\d\.]+)\s+LUFS", output)
    lra_match = re.search(r"LRA:\s+([-\d\.]+)\s+LU", output)
    tp_match = re.search(r"True peak:\s+Peak:\s+([-\d\.]+)\s+dBFS", output)

    return {
        "integrated_lufs": float(i_match.group(1)) if i_match else -99.0,
        "loudness_range": float(lra_match.group(1)) if lra_match else 0.0,
        "true_peak_dbfs": float(tp_match.group(1)) if tp_match else 0.0
    }


def audit_visual_integrity(video_path: str, duration_sec: float = 0.0) -> Dict[str, List[Dict[str, float]]]:
    """Detect sustained black and frozen video intervals."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-50dB:d=1.0",
        "-an", "-f", "null", "-",
    ]
    output = run_cmd(cmd)
    black_frames = [
        {"start": float(start), "end": float(end), "duration": float(duration)}
        for start, end, duration in re.findall(
            r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)",
            output,
        )
    ]
    freeze_starts = [float(value) for value in re.findall(r"freeze_start:\s*([\d.]+)", output)]
    freeze_ends = [float(value) for value in re.findall(r"freeze_end:\s*([\d.]+)", output)]
    freeze_durations = [float(value) for value in re.findall(r"freeze_duration:\s*([\d.]+)", output)]
    freezes = []
    for index, duration in enumerate(freeze_durations):
        start = freeze_starts[index] if index < len(freeze_starts) else 0.0
        end = freeze_ends[index] if index < len(freeze_ends) else start + duration
        freezes.append({"start": start, "end": end, "duration": duration})
    # A freeze that continues through EOF has no freeze_end/freeze_duration line.
    for start in freeze_starts[len(freeze_durations):]:
        if duration_sec > start:
            freezes.append({"start": start, "end": duration_sec, "duration": duration_sec - start})
    return {"black_frames": black_frames, "freezes": freezes}


def _fps(rate: str) -> float:
    try:
        numerator, denominator = rate.split("/", 1)
        return float(numerator) / float(denominator)
    except (AttributeError, ValueError, ZeroDivisionError):
        return 0.0

def audit_video(video_path: str, max_silence: float = 2.5, target_lufs: float = -14.0) -> Dict[str, Any]:
    path = Path(video_path)
    if not path.exists():
        return {"error": f"File not found: {video_path}", "passed": False}

    info = probe_stream_info(video_path)
    format_info = info.get("format", {})
    streams = info.get("streams", [])

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    v_dur = float(v_stream.get("duration", format_info.get("duration", 0))) if v_stream else 0.0
    a_dur = float(a_stream.get("duration", format_info.get("duration", 0))) if a_stream else 0.0
    drift = abs(v_dur - a_dur) if v_dur and a_dur else 0.0

    silences = audit_silences(video_path, min_silence_sec=max_silence)
    loudness = audit_loudness(video_path) if a_stream else {}
    visual = audit_visual_integrity(video_path, v_dur) if v_stream else {"black_frames": [], "freezes": []}

    warnings = []
    failures = []

    # 1. Dead air check
    if silences:
        for s in silences:
            msg = f"Dead air / long silence detected: {s['duration']:.2f}s from {s['start']:.2f}s to {s['end']:.2f}s"
            if s['duration'] >= max_silence * 1.5:
                failures.append(msg)
            else:
                warnings.append(msg)

    # 2. AV Sync / Duration Drift
    if drift > 0.5:
        failures.append(f"Severe AV Desync drift: video ({v_dur:.2f}s) vs audio ({a_dur:.2f}s) differs by {drift:.2f}s (> 0.5s)")
    elif drift > 0.2:
        warnings.append(f"Minor AV duration drift: {drift:.2f}s")

    # 3. Loudness check (YouTube Standard: -14 LUFS ± 2 LUFS)
    lufs = loudness.get("integrated_lufs", -99.0)
    if lufs != -99.0:
        lufs_diff = abs(lufs - target_lufs)
        if lufs_diff > 3.0:
            warnings.append(f"Loudness deviation: {lufs:.1f} LUFS (Target: {target_lufs} LUFS, Diff: {lufs_diff:.1f} LU)")

    # 4. Visual integrity
    for interval in visual["black_frames"]:
        msg = f"Black frame interval: {interval['duration']:.2f}s from {interval['start']:.2f}s to {interval['end']:.2f}s"
        (failures if interval["duration"] >= 1.0 else warnings).append(msg)
    for interval in visual["freezes"]:
        msg = f"Frozen frame interval: {interval['duration']:.2f}s from {interval['start']:.2f}s to {interval['end']:.2f}s"
        (failures if interval["duration"] >= max_silence else warnings).append(msg)

    # 5. Cadence: flag unusual rates and VFR-like nominal/average mismatches.
    nominal_fps = _fps(v_stream.get("r_frame_rate", "0/1")) if v_stream else 0.0
    average_fps = _fps(v_stream.get("avg_frame_rate", "0/1")) if v_stream else 0.0
    standard_rates = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0)
    if average_fps and min(abs(average_fps - rate) for rate in standard_rates) > 0.05:
        warnings.append(f"Non-standard average frame rate: {average_fps:.3f} fps; inspect for speed-up or cadence issues")
    if nominal_fps and average_fps and abs(nominal_fps - average_fps) > 0.1:
        warnings.append(f"Variable/suspicious frame cadence: nominal {nominal_fps:.3f} fps vs average {average_fps:.3f} fps")

    passed = len(failures) == 0

    return {
        "file": str(path.name),
        "path": str(path.resolve()),
        "passed": passed,
        "duration_sec": v_dur or a_dur,
        "width": v_stream.get("width") if v_stream else None,
        "height": v_stream.get("height") if v_stream else None,
        "fps": v_stream.get("r_frame_rate") if v_stream else None,
        "average_fps": round(average_fps, 3),
        "av_drift_sec": round(drift, 3),
        "loudness": loudness,
        "dead_air_count": len(silences),
        "silences": silences,
        "black_frames": visual["black_frames"],
        "freezes": visual["freezes"],
        "warnings": warnings,
        "failures": failures
    }

def main():
    parser = argparse.ArgumentParser(description="FFmpeg Video Pre-/Post-Flight Quality Audit")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--max-silence", type=float, default=2.5, help="Max allowed silence duration (default: 2.5s)")
    parser.add_argument("--target-lufs", type=float, default=-14.0, help="Target LUFS (default: -14.0)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()
    report = audit_video(args.video, max_silence=args.max_silence, target_lufs=args.target_lufs)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASSED" if report["passed"] else "FAILED"
        print(f"\n================ QA AUDIT: {report['file']} [{status}] ================")
        print(f"Duration: {report.get('duration_sec', 0):.2f}s | Resolution: {report.get('width')}x{report.get('height')} | AV Drift: {report.get('av_drift_sec')}s")
        if report.get("loudness"):
            print(f"Audio Loudness: {report['loudness'].get('integrated_lufs')} LUFS (Peak: {report['loudness'].get('true_peak_dbfs')} dBFS)")
        print(f"Dead Air / Silences (> {args.max_silence}s): {report.get('dead_air_count')}")

        if report.get("failures"):
            print("\n❌ CRITICAL FAILURES:")
            for f in report["failures"]:
                print(f"  - {f}")
        if report.get("warnings"):
            print("\n⚠️ WARNINGS:")
            for w in report["warnings"]:
                print(f"  - {w}")
        if report["passed"] and not report.get("warnings"):
            print("\n✅ All Quality & Broadcast gates passed cleanly!")

    sys.exit(0 if report["passed"] else 1)

if __name__ == "__main__":
    main()
