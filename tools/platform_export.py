#!/usr/bin/env python3
"""Platform variant export: reframe + loudness + encode + thumbnail + technical QC.

An UNVERIFIED profile still produces a variant (so it can be reviewed), but
the result is flagged as a draft; release_package.py (Schritt 8) is what
actually refuses to ship a draft, by re-checking the profile's own status.
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

from tools import asset_record, platform_profiles, qc_pipeline, reframe
from tools.media_validation import MediaValidationError, validate_audio
from tools.video_ingest import probe_media

LOUDNESS_TOLERANCE_LUFS = 2.0
FPS_TOLERANCE = 0.5


class PlatformExportError(RuntimeError):
    """A platform variant could not be built."""


def _run(command: list[str], *, timeout: int = 180) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as error:
        raise PlatformExportError(f"ffmpeg fehlgeschlagen: {error.stderr[-2000:]}") from error
    except subprocess.TimeoutExpired as error:
        raise PlatformExportError(f"ffmpeg lief in ein Timeout: {command[0]}") from error


def check_against_profile(output_path: Path, profile: dict[str, Any]) -> list[dict[str, str]]:
    """Technical QC checks: duration, file size, fps, resolution, codec, loudness."""
    metadata = probe_media(output_path)
    problems: list[str] = []
    duration = float(cast(float, metadata["duration"]))
    if profile["max_duration_s"] is not None and duration > profile["max_duration_s"]:
        problems.append(f"Dauer {duration:.1f}s > Limit {profile['max_duration_s']}s")
    size = output_path.stat().st_size
    if size > profile["max_file_size_bytes"]:
        problems.append(f"Dateigröße {size}B > Limit {profile['max_file_size_bytes']}B")
    if profile["fps"] is not None:
        fps = metadata.get("fps")
        if fps is None or abs(float(cast(float, fps)) - profile["fps"]) > FPS_TOLERANCE:
            problems.append(f"fps {fps} weicht von Ziel {profile['fps']} ab")
    width, height = metadata.get("width"), metadata.get("height")
    target = profile["resolution"]
    if (width, height) != (target["width"], target["height"]):
        problems.append(
            f"Auflösung {width}x{height} != Ziel {target['width']}x{target['height']}"
        )
    codec = metadata.get("video_codec")
    if profile["codec"] and codec != profile["codec"]:
        problems.append(f"Codec {codec} != Ziel {profile['codec']}")
    checks: list[dict[str, str]] = [
        {
            "name": "technical",
            "status": "fail" if problems else "pass",
            "evidence": "; ".join(problems) if problems else "Profilgrenzen eingehalten.",
        }
    ]

    if profile["loudness_target_lufs"] is not None:
        try:
            report = validate_audio(output_path)
        except MediaValidationError as error:
            checks.append({"name": "audio", "status": "fail", "evidence": str(error)})
        else:
            lufs = float(cast(float, report.details["loudnessLufs"]))
            target_lufs = float(profile["loudness_target_lufs"])
            if abs(lufs - target_lufs) > LOUDNESS_TOLERANCE_LUFS:
                checks.append(
                    {
                        "name": "audio",
                        "status": "fail",
                        "evidence": f"{lufs} LUFS weicht von Ziel {target_lufs} LUFS ab.",
                    }
                )
            else:
                checks.append({"name": "audio", "status": "pass", "evidence": f"{lufs} LUFS."})
    else:
        checks.append({"name": "audio", "status": "not_run", "evidence": "Kein Loudness-Ziel."})
    return checks


def make_variant(
    project_id: str,
    master_asset_id: str,
    profile_name: str,
    *,
    focus_spec_path: Path | None = None,
    allow_center_crop: bool = False,
    allow_center_crop_reason: str | None = None,
    burn_subtitles_path: Path | None = None,
    subtitle_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reframe, normalize loudness, encode, thumbnail, register, and technically QC."""
    profile = platform_profiles.get_profile(profile_name)
    if profile["media_type"] != "video":
        raise PlatformExportError(f"Profil {profile_name!r} ist kein Video-Profil.")
    is_draft = profile["status"] != "VERIFIED"

    master_record, _path = asset_record.load_asset_record(master_asset_id)
    master_path = asset_record.ASSET_ROOT / str(master_record["path"])

    fps = profile["fps"]
    codec = profile["codec"]
    container = profile["container"]
    loudness_target = profile["loudness_target_lufs"]

    with tempfile.TemporaryDirectory(prefix="platform-export-") as work_dir:
        work = Path(work_dir)
        reframed_path = work / "reframed.mp4"
        reframe_result = reframe.render(
            master_path,
            profile_name,
            reframed_path,
            focus_spec_path=focus_spec_path,
            allow_center_crop=allow_center_crop,
            allow_center_crop_reason=allow_center_crop_reason,
        )

        normalized_path = work / "normalized.mp4"
        if loudness_target is not None:
            _run(
                [
                    "ffmpeg", "-y", "-i", str(reframed_path),
                    "-af", f"loudnorm=I={loudness_target}:TP=-1.5:LRA=11",
                    "-c:v", "copy", str(normalized_path),
                ]
            )
        else:
            reframed_path.replace(normalized_path)

        if burn_subtitles_path is not None:
            from tools.subtitle_burn import burn_in

            burned_path = work / "burned.mp4"
            burn_in(normalized_path, burn_subtitles_path, burned_path, style=subtitle_style or {})
            pre_encode_path = burned_path
        else:
            pre_encode_path = normalized_path

        output_path = work / f"variant.{container}"
        _run(
            [
                "ffmpeg", "-y", "-i", str(pre_encode_path),
                "-r", str(fps), "-c:v", codec, "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(output_path),
            ]
        )

        thumbnail_path: Path | None = None
        thumbnail_requirements = profile.get("thumbnail_requirements")
        if thumbnail_requirements and thumbnail_requirements.get("required"):
            thumbnail_path = work / "thumbnail.jpg"
            _run(["ffmpeg", "-y", "-i", str(output_path), "-frames:v", "1", str(thumbnail_path)])

        parents = [master_asset_id]
        if focus_spec_path is not None:
            spec_record = asset_record.register_asset(focus_spec_path, role="EDITABLE_SOURCE")
            parents.append(str(spec_record["asset_id"]))
        if burn_subtitles_path is not None:
            srt_record = asset_record.register_asset(burn_subtitles_path)
            parents.append(str(srt_record["asset_id"]))

        variant_record = asset_record.register_derived(
            output_path,
            parents=parents,
            role="VARIANT",
            tool="platform_export",
            operation=f"variant_{profile_name}",
        )

        thumbnail_record = None
        if thumbnail_path is not None:
            thumbnail_record = asset_record.register_derived(
                thumbnail_path,
                parents=[str(variant_record["asset_id"])],
                role="VARIANT",
                tool="platform_export",
                operation=f"thumbnail_{profile_name}",
            )

        checks = check_against_profile(output_path, profile)
        verdict = qc_pipeline.write_verdict(project_id, str(variant_record["asset_id"]), checks)

    return {
        "variant_asset_id": variant_record["asset_id"],
        "thumbnail_asset_id": thumbnail_record["asset_id"] if thumbnail_record else None,
        "profile": profile_name,
        "draft": is_draft,
        "verdict_id": verdict["verdict_id"],
        "verdict_overall": verdict["overall"],
        "reframe_warnings": reframe_result["warnings"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a platform-shaped variant.")
    commands = parser.add_subparsers(dest="command", required=True)

    make_cmd = commands.add_parser("make-variant", help="Build one platform variant.")
    make_cmd.add_argument("project_id")
    make_cmd.add_argument("--master", required=True, dest="master_asset_id")
    make_cmd.add_argument("--profile", required=True)
    make_cmd.add_argument("--focus", type=Path)
    make_cmd.add_argument("--allow-center-crop", action="store_true")
    make_cmd.add_argument("--reason")
    make_cmd.add_argument("--burn-subtitles", type=Path)
    make_cmd.add_argument("--style", type=Path, help="Subtitle style JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        style = json.loads(args.style.read_text(encoding="utf-8")) if args.style else None
        result = make_variant(
            args.project_id,
            args.master_asset_id,
            args.profile,
            focus_spec_path=args.focus,
            allow_center_crop=args.allow_center_crop,
            allow_center_crop_reason=args.reason,
            burn_subtitles_path=args.burn_subtitles,
            subtitle_style=style,
        )
    except (PlatformExportError, platform_profiles.PlatformProfileError) as error:
        print(f"Platform-Export: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
