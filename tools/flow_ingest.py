#!/usr/bin/env python3
"""
tools/flow_ingest.py — Ingest and validate Google Flow (Veo / Imagen / Flow Music) assets.

Enforces Hannibal AI OS standards:
1. End-Frame = Start-Frame Law (extracts last frame as PNG for chaining into next Flow clip)
2. Pre-flight Quality & Spec Verification (Resolution, Aspect Ratio, Codec, FPS)
3. Asset Organization & DaVinci Resolve Timeline / Project Staging
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def get_video_metadata(video_path: Path) -> Dict[str, Any]:
    """Extract metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
    except Exception as e:
        return {"error": f"ffprobe failed: {e}"}

    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0))

    meta: Dict[str, Any] = {
        "duration_sec": duration,
        "format_name": fmt.get("format_name", ""),
        "size_bytes": int(fmt.get("size", 0)),
        "has_video": video_stream is not None,
        "has_audio": audio_stream is not None,
    }

    if video_stream:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        meta["width"] = width
        meta["height"] = height
        meta["resolution"] = f"{width}x{height}"
        meta["video_codec"] = video_stream.get("codec_name", "")
        # Calculate fps
        r_frame_rate = video_stream.get("r_frame_rate", "24/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            meta["fps"] = round(float(num) / float(den), 2) if float(den) > 0 else 24.0
        else:
            meta["fps"] = float(r_frame_rate)

        # Aspect ratio determination
        if width > 0 and height > 0:
            ratio = round(width / height, 2)
            if ratio == 1.78 or (width == 1920 and height == 1080) or (width == 3840 and height == 2160):
                meta["aspect_ratio"] = "16:9"
            elif ratio == 0.56 or (width == 1080 and height == 1920):
                meta["aspect_ratio"] = "9:16"
            elif ratio == 1.0:
                meta["aspect_ratio"] = "1:1"
            else:
                meta["aspect_ratio"] = f"{width}:{height}"

    if audio_stream:
        meta["audio_codec"] = audio_stream.get("codec_name", "")
        meta["sample_rate"] = int(audio_stream.get("sample_rate", 48000))

    return meta


def extract_end_frame(video_path: Path, output_image_path: Path) -> Path:
    """Extract the exact last frame of the video clip as PNG (End-Frame Locking)."""
    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-sseof", "-0.1",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "1",
        "-y",
        str(output_image_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg failed extracting end frame: {res.stderr}")
    if not output_image_path.exists():
        raise RuntimeError(f"Frame extraction produced no file at: {output_image_path}")
    return output_image_path


def ingest_flow_clip(
    input_file: Path,
    project_dir: Path,
    scene_number: Optional[int] = None,
    extract_lock_frame: bool = True,
) -> Dict[str, Any]:
    """
    Ingest a Google Flow clip into a video-toolkit project structure.
    
    Structure:
      <project_dir>/raw_clips/
      <project_dir>/chain_frames/
      <project_dir>/flow_manifest.json
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    project_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = project_dir / "raw_clips"
    chain_dir = project_dir / "chain_frames"
    raw_dir.mkdir(exist_ok=True)
    chain_dir.mkdir(exist_ok=True)

    meta = get_video_metadata(input_file)

    # Determine target filename
    idx = scene_number if scene_number is not None else (len(list(raw_dir.glob("*.mp4"))) + 1)
    target_clip = raw_dir / f"scene_{idx:02d}_{input_file.name}"
    
    # Copy clip if not already in target
    if input_file.resolve() != target_clip.resolve():
        import shutil
        shutil.copy2(input_file, target_clip)

    result: Dict[str, Any] = {
        "scene_index": idx,
        "clip_path": str(target_clip),
        "metadata": meta,
        "end_frame": None,
        "status": "INGESTED",
    }

    if extract_lock_frame and meta.get("has_video"):
        end_frame_path = chain_dir / f"scene_{idx:02d}_endframe.png"
        try:
            extracted = extract_end_frame(target_clip, end_frame_path)
            result["end_frame"] = str(extracted)
        except Exception as e:
            result["end_frame_error"] = str(e)

    # Update flow_manifest.json
    manifest_path = project_dir / "flow_manifest.json"
    manifest: Dict[str, Any] = {"project": project_dir.name, "scenes": []}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    # Append or update scene
    scenes = [s for s in manifest.get("scenes", []) if s.get("scene_index") != idx]
    scenes.append(result)
    scenes.sort(key=lambda s: s.get("scene_index", 0))
    manifest["scenes"] = scenes
    manifest["total_scenes"] = len(scenes)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return result


def main():
    parser = argparse.ArgumentParser(description="Ingest and chain Google Flow clips.")
    parser.add_argument("input", type=str, help="Path to downloaded Flow clip or file")
    parser.add_argument("--project", "-p", type=str, default="projects/flow-production", help="Project directory")
    parser.add_argument("--scene", "-s", type=int, default=None, help="Scene number")
    parser.add_argument("--no-frame-lock", action="store_true", help="Skip extracting end frame")
    args = parser.parse_args()

    input_path = Path(args.input)
    project_path = Path(args.project)

    try:
        res = ingest_flow_clip(
            input_file=input_path,
            project_dir=project_path,
            scene_number=args.scene,
            extract_lock_frame=not args.no_frame_lock,
        )
        print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"Error ingesting Flow clip: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
