#!/usr/bin/env python3
"""Focus-driven reframing: never a silent center-crop.

A reframe needs a focus spec (JSON keyframes of a normalized center point,
optionally a bounding box) naming where the crop should follow across time.
Without one, the result is refused outright (needs_human) unless the caller
explicitly opts into a center-crop with a stated reason -- recorded as a
warning, not silently accepted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import platform_profiles
from tools.video_ingest import probe_media


class ReframeError(RuntimeError):
    """A reframe could not be planned or rendered; caller should treat as needs_human."""


def parse_focus_spec(path: Path) -> list[dict[str, Any]]:
    """Read+validate a focus spec: a non-empty, time-sorted list of keyframes."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReframeError(f"Fokus-Spec ist nicht lesbar: {error}") from error
    keyframes = data.get("keyframes") if isinstance(data, dict) else None
    if not isinstance(keyframes, list) or not keyframes:
        raise ReframeError("Fokus-Spec braucht mindestens ein Keyframe.")
    parsed: list[dict[str, Any]] = []
    for entry in keyframes:
        try:
            t, cx, cy = float(entry["t"]), float(entry["cx"]), float(entry["cy"])
        except (KeyError, TypeError, ValueError) as error:
            raise ReframeError(f"Ungültiges Keyframe: {entry!r}") from error
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
            raise ReframeError(f"Fokuspunkt außerhalb [0,1]: cx={cx}, cy={cy}")
        keyframe: dict[str, Any] = {"t": t, "cx": cx, "cy": cy}
        box = entry.get("box")
        if box is not None:
            try:
                keyframe["box"] = {"width": float(box["width"]), "height": float(box["height"])}
            except (KeyError, TypeError, ValueError) as error:
                raise ReframeError(f"Ungültige Box: {box!r}") from error
        parsed.append(keyframe)
    parsed.sort(key=lambda keyframe: cast(float, keyframe["t"]))
    return parsed


def smooth_keyframes(
    keyframes: list[dict[str, Any]], *, alpha: float = 0.5
) -> list[dict[str, Any]]:
    """Exponential smoothing over the keyframe sequence to remove jitter between cuts."""
    if not keyframes:
        return []
    smoothed: list[dict[str, Any]] = [dict(keyframes[0])]
    for keyframe in keyframes[1:]:
        previous = smoothed[-1]
        entry: dict[str, Any] = {
            "t": keyframe["t"],
            "cx": alpha * keyframe["cx"] + (1 - alpha) * previous["cx"],
            "cy": alpha * keyframe["cy"] + (1 - alpha) * previous["cy"],
        }
        if "box" in keyframe:
            entry["box"] = keyframe["box"]
        smoothed.append(entry)
    return smoothed


def focus_at(keyframes: list[dict[str, Any]], t: float) -> tuple[float, float]:
    """Piecewise-linear interpolation of the focus center at time t."""
    if len(keyframes) == 1:
        return keyframes[0]["cx"], keyframes[0]["cy"]
    if t <= keyframes[0]["t"]:
        return keyframes[0]["cx"], keyframes[0]["cy"]
    if t >= keyframes[-1]["t"]:
        return keyframes[-1]["cx"], keyframes[-1]["cy"]
    for start, end in zip(keyframes, keyframes[1:]):
        if start["t"] <= t <= end["t"]:
            span = end["t"] - start["t"]
            ratio = 0.0 if span <= 0 else (t - start["t"]) / span
            return (
                start["cx"] + (end["cx"] - start["cx"]) * ratio,
                start["cy"] + (end["cy"] - start["cy"]) * ratio,
            )
    return keyframes[-1]["cx"], keyframes[-1]["cy"]


def compute_crop_window(
    source_w: int, source_h: int, target_w: int, target_h: int, cx: float, cy: float
) -> tuple[int, int, int, int]:
    """Largest target-aspect box that fits in the source, centered on (cx, cy)."""
    target_ratio = target_w / target_h
    source_ratio = source_w / source_h
    if source_ratio > target_ratio:
        crop_h = source_h
        crop_w = round(crop_h * target_ratio)
    else:
        crop_w = source_w
        crop_h = round(crop_w / target_ratio)
    crop_w = max(2, min(crop_w, source_w))
    crop_h = max(2, min(crop_h, source_h))
    x = round(cx * source_w - crop_w / 2)
    y = round(cy * source_h - crop_h / 2)
    x = max(0, min(x, source_w - crop_w))
    y = max(0, min(y, source_h - crop_h))
    return x, y, crop_w, crop_h


def check_safe_zone(
    keyframes: list[dict[str, Any]], profile: dict[str, Any], source_w: int, source_h: int
) -> list[str]:
    """Report every keyframe whose focus point would land outside the profile's safe zone."""
    safe_zone = profile.get("safe_zone")
    if not safe_zone:
        return []
    target_w = profile["resolution"]["width"]
    target_h = profile["resolution"]["height"]
    warnings: list[str] = []
    for keyframe in keyframes:
        x, y, crop_w, crop_h = compute_crop_window(
            source_w, source_h, target_w, target_h, keyframe["cx"], keyframe["cy"]
        )
        focus_x = (keyframe["cx"] * source_w - x) / crop_w * target_w
        focus_y = (keyframe["cy"] * source_h - y) / crop_h * target_h
        if not (
            safe_zone["x"] <= focus_x <= safe_zone["x"] + safe_zone["width"]
            and safe_zone["y"] <= focus_y <= safe_zone["y"] + safe_zone["height"]
        ):
            warnings.append(
                f"Fokus bei t={keyframe['t']}s liegt außerhalb der Safe-Zone "
                f"({focus_x:.0f},{focus_y:.0f})."
            )
    return warnings


def _run(command: list[str], *, timeout: int = 120) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as error:
        raise ReframeError(f"ffmpeg fehlgeschlagen: {error.stderr[-2000:]}") from error
    except subprocess.TimeoutExpired as error:
        raise ReframeError(f"ffmpeg lief in ein Timeout: {command[0]}") from error


def _segment_bounds(keyframe_times: list[float], duration: float) -> list[float]:
    interior = {t for t in keyframe_times if 0 < t < duration}
    return sorted({0.0, *interior, duration})


def render(
    master_path: Path,
    profile_name: str,
    output_path: Path,
    *,
    focus_spec_path: Path | None = None,
    allow_center_crop: bool = False,
    allow_center_crop_reason: str | None = None,
) -> dict[str, Any]:
    """Render a profile-shaped crop that follows the focus spec. Never a silent center-crop."""
    profile = platform_profiles.get_profile(profile_name)
    target_w, target_h = profile["resolution"]["width"], profile["resolution"]["height"]

    warnings: list[str] = []
    if focus_spec_path is None:
        if not allow_center_crop:
            raise ReframeError(
                "Kein Fokus-Spec vorhanden; ein stiller Center-Crop wird nicht automatisch "
                "durchgeführt (needs_human). Mit --allow-center-crop und einer Begründung "
                "explizit erlauben."
            )
        if not allow_center_crop_reason or not allow_center_crop_reason.strip():
            raise ReframeError("--allow-center-crop braucht eine Begründung.")
        keyframes = [{"t": 0.0, "cx": 0.5, "cy": 0.5}]
        warnings.append(f"Center-Crop ohne Fokus-Spec erlaubt: {allow_center_crop_reason}")
    else:
        keyframes = smooth_keyframes(parse_focus_spec(focus_spec_path))

    metadata = probe_media(master_path)
    source_w, source_h = int(cast(int, metadata["width"])), int(cast(int, metadata["height"]))
    duration = float(cast(float, metadata["duration"]))

    if focus_spec_path is not None:
        safe_zone_warnings = check_safe_zone(keyframes, profile, source_w, source_h)
        if safe_zone_warnings:
            raise ReframeError(
                "Fokus verlässt die Safe-Zone (needs_human): " + "; ".join(safe_zone_warnings)
            )

    bounds = _segment_bounds([keyframe["t"] for keyframe in keyframes], duration)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="reframe-") as work_dir:
        work = Path(work_dir)
        segment_paths: list[Path] = []
        for index, (start, end) in enumerate(zip(bounds, bounds[1:])):
            midpoint = (start + end) / 2
            cx, cy = focus_at(keyframes, midpoint)
            x, y, crop_w, crop_h = compute_crop_window(
                source_w, source_h, target_w, target_h, cx, cy
            )
            segment_path = work / f"segment-{index}.mp4"
            _run(
                [
                    "ffmpeg", "-y", "-ss", f"{start}", "-to", f"{end}", "-i", str(master_path),
                    "-vf", f"crop={crop_w}:{crop_h}:{x}:{y},scale={target_w}:{target_h}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(segment_path),
                ]
            )
            segment_paths.append(segment_path)

        if len(segment_paths) == 1:
            segment_paths[0].replace(output_path)
        else:
            concat_list = work / "concat.txt"
            concat_list.write_text(
                "".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8"
            )
            _run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output_path),
                ]
            )

    return {
        "output_path": str(output_path),
        "profile": profile_name,
        "segments": len(bounds) - 1,
        "warnings": warnings,
        "center_crop": focus_spec_path is None,
    }


def register_reframe_output(
    master_asset_id: str, output_path: Path, *, focus_spec_path: Path | None = None
) -> dict[str, Any]:
    """Register the focus spec (if any) as EDITABLE_SOURCE and the output as VARIANT."""
    from tools import asset_record

    parents = [master_asset_id]
    if focus_spec_path is not None:
        spec_record = asset_record.register_asset(focus_spec_path, role="EDITABLE_SOURCE")
        parents.append(str(spec_record["asset_id"]))
    return asset_record.register_derived(
        output_path, parents=parents, role="VARIANT", tool="reframe", operation="focus_crop"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Focus-driven reframing (no silent center-crop).")
    parser.add_argument("master_video", type=Path)
    parser.add_argument("profile")
    parser.add_argument("output", type=Path)
    parser.add_argument("--focus", type=Path, help="Focus spec JSON with keyframes.")
    parser.add_argument("--allow-center-crop", action="store_true")
    parser.add_argument("--reason", help="Required justification with --allow-center-crop.")
    parser.add_argument("--master-asset-id", help="Register the output as a VARIANT of this id.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = render(
            args.master_video,
            args.profile,
            args.output,
            focus_spec_path=args.focus,
            allow_center_crop=args.allow_center_crop,
            allow_center_crop_reason=args.reason,
        )
        if args.master_asset_id:
            record = register_reframe_output(
                args.master_asset_id, args.output, focus_spec_path=args.focus
            )
            result["asset_id"] = record["asset_id"]
    except (ReframeError, platform_profiles.PlatformProfileError) as error:
        print(f"Reframe: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
