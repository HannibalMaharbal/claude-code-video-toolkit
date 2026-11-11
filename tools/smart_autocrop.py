#!/usr/bin/env python3
"""Smart Face-Centering & 9:16 Auto-Crop Tool.

Automatically reframes 16:9 landscape video into 9:16 vertical Shorts/Reels:
1. Samples frames at regular time intervals.
2. Tracks faces and subjects using Apple Vision on macOS (or edge-saliency fallback).
3. Applies temporal deadband smoothing to avoid jitter while preserving speaker focus.
4. Enforces platform safe-zones (YouTube Shorts / Instagram Reels).
5. Generates the standard focus_spec.json and renders high-definition 9:16 video.

Usage:
    uv run tools/smart_autocrop.py --input video.mp4 --output-dir ~/Hannibal/00_INBOX/Zu_Bearbeiten/Videos/
    uv run tools/smart_autocrop.py --input video.mp4 --profile youtube_short --spec-only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import platform_profiles, reframe
from tools.video_ingest import probe_media


class AutoCropError(RuntimeError):
    """Raised when face detection or auto-crop rendering fails."""


def _detect_faces_vision_swift(image_paths: list[Path]) -> list[dict[str, Any] | None]:
    """Run Apple Vision face detection on macOS via swift execution."""
    if not image_paths:
        return []

    # Prepare swift script that batches all images in one run
    file_list = "\n".join(str(p.resolve()) for p in image_paths)
    swift_code = """
import Foundation
import Vision
import CoreImage

let inputData = FileHandle.standardInput.readDataToEndOfFile()
guard let inputStr = String(data: inputData, encoding: .utf8) else {
    exit(1)
}

let paths = inputStr.split(separator: "\\n").map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
var allResults: [[[String: Double]]] = []

for path in paths {
    let url = URL(fileURLWithPath: path)
    let request = VNDetectFaceRectanglesRequest()
    let handler = VNImageRequestHandler(url: url, options: [:])
    try? handler.perform([request])
    
    var faces: [[String: Double]] = []
    if let observations = request.results {
        for obs in observations {
            let cx = Double(obs.boundingBox.midX)
            let cy = Double(1.0 - obs.boundingBox.midY)
            let w = Double(obs.boundingBox.width)
            let h = Double(obs.boundingBox.height)
            faces.append(["cx": cx, "cy": cy, "w": w, "h": h])
        }
    }
    allResults.append(faces)
}

let jsonData = try! JSONSerialization.data(withJSONObject: allResults)
print(String(data: jsonData, encoding: .utf8)!)
"""
    try:
        proc = subprocess.run(
            ["swift", "-e", swift_code],
            input=file_list,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            return [None] * len(image_paths)

        raw = json.loads(proc.stdout.strip())
        results: list[dict[str, Any] | None] = []
        for face_list in raw:
            if face_list:
                # Pick the largest face (by area w * h)
                face_list.sort(key=lambda f: f["w"] * f["h"], reverse=True)
                dominant = face_list[0]
                results.append({
                    "cx": float(dominant["cx"]),
                    "cy": float(dominant["cy"]),
                    "box": {"width": float(dominant["w"]), "height": float(dominant["h"])},
                })
            else:
                results.append(None)
        return results
    except Exception:
        return [None] * len(image_paths)


def _detect_subject_saliency_fallback(image_path: Path) -> dict[str, Any]:
    """Fallback: Calculate visual saliency / center of mass via luminance and edges."""
    img = Image.open(image_path).convert("L")
    w, h = img.size
    arr = np.array(img, dtype=np.float32)

    # Compute gradient magnitude (Sobel-like edge energy)
    gy, gx = np.gradient(arr)
    energy = np.sqrt(gx**2 + gy**2)
    total_energy = float(np.sum(energy))

    if total_energy <= 1e-5:
        return {"cx": 0.5, "cy": 0.5, "box": {"width": 0.3, "height": 0.3}}

    # Coordinates
    y_indices, x_indices = np.indices((h, w))
    cx = float(np.sum(x_indices * energy) / total_energy) / w
    cy = float(np.sum(y_indices * energy) / total_energy) / h

    # Clamp to reasonable center frame range
    cx = max(0.2, min(0.8, cx))
    cy = max(0.2, min(0.8, cy))

    return {
        "cx": round(cx, 3),
        "cy": round(cy, 3),
        "box": {"width": 0.35, "height": 0.35},
    }


def sample_frames(video_path: Path, output_dir: Path, sample_interval: float = 1.0) -> list[tuple[float, Path]]:
    """Extract frames from video at sample_interval seconds."""
    meta = probe_media(video_path)
    duration = float(meta["duration"])

    sampled: list[tuple[float, Path]] = []
    fps_filter = f"fps=1/{sample_interval}"
    pattern = str(output_dir / "frame_%04d.jpg")

    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", fps_filter,
        "-q:v", "3",
        pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    extracted_files = sorted(output_dir.glob("frame_*.jpg"))
    for idx, frame_file in enumerate(extracted_files):
        t = round(idx * sample_interval, 2)
        if t <= duration:
            sampled.append((t, frame_file))

    if not sampled and duration > 0:
        # Guarantee at least t=0
        first_frame = output_dir / "frame_0001.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "0", "-i", str(video_path), "-vframes", "1", "-q:v", "3", str(first_frame)],
            check=True, capture_output=True,
        )
        sampled.append((0.0, first_frame))

    return sampled


def build_focus_spec(
    sampled_frames: list[tuple[float, Path]],
    *,
    deadband_threshold: float = 0.04,
    smoothing_alpha: float = 0.4,
    source_ratio: float = 16.0 / 9.0,
    target_ratio: float = 9.0 / 16.0,
) -> list[dict[str, Any]]:
    """Analyze frames and produce smooth, stabilized keyframes."""
    if not sampled_frames:
        return [{"t": 0.0, "cx": 0.5, "cy": 0.5, "box": {"width": 0.3, "height": 0.3}}]

    # Batch detect with Apple Vision
    frame_paths = [path for _, path in sampled_frames]
    vision_results = _detect_faces_vision_swift(frame_paths)

    raw_keyframes: list[dict[str, Any]] = []
    last_cx, last_cy = 0.5, 0.5

    for (t, path), detection in zip(sampled_frames, vision_results):
        if detection is not None:
            cx, cy = detection["cx"], detection["cy"]
            box = detection["box"]
        else:
            fallback = _detect_subject_saliency_fallback(path)
            cx, cy = fallback["cx"], fallback["cy"]
            box = fallback["box"]

        # Deadband dampening: ignore small jitter below threshold
        dist = np.hypot(cx - last_cx, cy - last_cy)
        if dist < deadband_threshold:
            cx, cy = last_cx, last_cy
        else:
            last_cx, last_cy = cx, cy

        raw_keyframes.append({"t": t, "cx": cx, "cy": cy, "box": box})

    # Single smoothing: reframe.render() handles temporal smoothing.
    keyframes = raw_keyframes

    # Derive valid cx crop center range from actual target crop width
    # For 16:9 source and 9:16 target: crop_w_rel = (9/16)/(16/9) = 81/256 ≈ 0.3164
    # half_crop_w ≈ 0.1582. Center must be in [half_crop_w, 1.0 - half_crop_w] so
    # the 9:16 crop window stays within [0.0, 1.0] and faces up to 1.0 remain framed.
    crop_w_rel = min(1.0, target_ratio / source_ratio) if source_ratio > target_ratio else 1.0
    half_crop_w = crop_w_rel / 2.0
    cx_min = round(half_crop_w, 4)
    cx_max = round(1.0 - half_crop_w, 4)

    for kf in keyframes:
        kf["cx"] = round(max(cx_min, min(cx_max, float(kf["cx"]))), 4)
        # cy preserves the true measured vertical position [0, 1]; not artificially clamped
        kf["cy"] = round(max(0.0, min(1.0, float(kf["cy"]))), 4)

    return keyframes


def smart_autocrop_video(
    input_video: Path,
    output_dir: Path,
    *,
    profile_name: str = "youtube_short",
    sample_interval: float = 1.0,
    render_video: bool = True,
    strict_safe_zone: bool = False,
) -> dict[str, Any]:
    """Full pipeline: Sample -> Track -> Build Spec -> Render 9:16 Crop."""
    if not input_video.is_file():
        raise FileNotFoundError(f"Video nicht gefunden: {input_video}")

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="autocrop_"))

    try:
        # Detect source dimensions to derive aspect ratios & check safe zones
        try:
            meta = probe_media(input_video)
            w = meta.get("width")
            h = meta.get("height")
            if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
                raise AutoCropError(f"Ungültige Videoauflösung in Medienmetadaten: {w}x{h}")
            src_w = w
            src_h = h
        except AutoCropError:
            raise
        except Exception as err:
            raise AutoCropError(f"Metadaten des Videos konnten nicht ermittelt werden: {err}") from err
        source_ratio = src_w / max(1, src_h)

        # 1. Sample frames
        frames = sample_frames(input_video, temp_dir, sample_interval=sample_interval)

        # Load target profile
        profile = platform_profiles.get_profile(profile_name)
        target_w = int(profile["resolution"]["width"])
        target_h = int(profile["resolution"]["height"])
        target_ratio = target_w / max(1, target_h)

        # 2. Build Focus Spec
        keyframes = build_focus_spec(
            frames,
            source_ratio=source_ratio,
            target_ratio=target_ratio,
        )

        # Safe-zone audit: inspect without distorting cy measurements
        warnings = reframe.check_safe_zone(keyframes, profile, src_w, src_h)
        if warnings and strict_safe_zone:
            raise AutoCropError(
                f"Safe-Zone-Verletzung erkannt (--strict-safe-zone): {'; '.join(warnings)}"
            )

        spec_data: dict[str, Any] = {
            "version": "1.0",
            "source_video": str(input_video.resolve()),
            "profile": profile_name,
            "keyframes": keyframes,
        }
        if warnings:
            spec_data["warnings"] = warnings

        spec_file = output_dir / f"{input_video.stem}_focus_spec.json"
        spec_file.write_text(json.dumps(spec_data, indent=2), encoding="utf-8")

        rendered_video_path: Path | None = None
        if render_video:
            output_name = f"{input_video.stem}_9x16_crop.mp4"
            rendered_video_path = output_dir / output_name
            reframe.render(
                master_path=input_video,
                profile_name=profile_name,
                output_path=rendered_video_path,
                focus_spec_path=spec_file,
                allow_safe_zone_violation=True,
            )

        status_str = "success_with_warnings" if warnings else "success"
        return {
            "status": status_str,
            "source": str(input_video),
            "profile": profile_name,
            "keyframes_count": len(keyframes),
            "spec_file": str(spec_file),
            "output_video": str(rendered_video_path) if rendered_video_path else None,
            "warnings": warnings,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Face-Centering & 9:16 Auto-Crop")
    parser.add_argument("--input", required=True, type=Path, help="Pfad zum 16:9 Quellvideo")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "Hannibal" / "00_INBOX" / "Zu_Bearbeiten" / "Videos",
        help="Ausgabeordner",
    )
    parser.add_argument(
        "--profile",
        default="youtube_short",
        choices=["youtube_short", "instagram_reel", "tiktok"],
        help="Zielprofil für 9:16 Reframing",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Sampling-Intervall in Sekunden (Default: 1.0)",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help="Nur die focus_spec.json erzeugen, nicht rendern",
    )
    parser.add_argument(
        "--strict-safe-zone",
        action="store_true",
        help="Bricht bei Safe-Zone-Verletzung mit Fehler ab und rendert nicht",
    )
    args = parser.parse_args()

    try:
        result = smart_autocrop_video(
            input_video=args.input,
            output_dir=args.output_dir,
            profile_name=args.profile,
            sample_interval=args.interval,
            render_video=not args.spec_only,
            strict_safe_zone=args.strict_safe_zone,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"Fehler beim Smart-AutoCrop: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
