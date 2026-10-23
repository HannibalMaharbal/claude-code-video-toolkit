#!/usr/bin/env python3
"""Local SeedVR2 video restoration/upscaling adapter for Apple Silicon.

The adapter wraps the installed ``mflux-upscale-seedvr2`` CLI and the pinned
local 4-bit SeedVR2 3B checkpoint. It never downloads models, never uses a
cloud provider, and never overwrites an existing output.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

MODEL_PATH = Path.home() / "AI-Modelle" / "SeedVR2-MLX-4bit"
COLOR_CORRECTIONS = ("wavelet", "lab", "off")
GUARDED_OVERRIDE_SYSTEM_RESERVE_BYTES = 2 * (1000**3)
GUARDED_OVERRIDE_MIN_AVAILABLE_BYTES = 13 * (1000**3)
MODEL_RESIDENCY_FACTOR = 1.25
SEEDVR2_INNER_DIM = 2560
METAL_EMPIRICAL_WORKING_SET_FACTOR = 24.0
VERIFIED_MAX_OUTPUT_WIDTH = 640
VERIFIED_MAX_OUTPUT_HEIGHT = 352
VERIFIED_MAX_CHUNK_FRAMES = 5


def _missing_model_files(model_path: Path) -> list[str]:
    """Return missing checkpoint files referenced by each MLX shard index."""
    missing: list[str] = []
    for component in ("transformer", "vae"):
        index_path = model_path / component / "model.safetensors.index.json"
        if not index_path.is_file():
            missing.append(str(index_path.relative_to(model_path)))
            continue
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            shards = set(index["weight_map"].values())
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            missing.append(f"{component}/model.safetensors.index.json (ungültig)")
            continue
        for shard in sorted(shards):
            path = model_path / component / shard
            if not path.is_file() or path.stat().st_size == 0:
                missing.append(f"{component}/{shard}")
    return missing


def _host_available_memory_bytes() -> int | None:
    """Measure reclaimable macOS memory using the same fields as mlx-gen."""
    try:
        proc = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True, timeout=5)
        lines = proc.stdout.splitlines()
        page_size = int(lines[0].split("page size of", 1)[1].split("bytes", 1)[0].strip(" )"))
        counts: dict[str, int] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            digits = value.strip().rstrip(".")
            if digits.isdigit():
                counts[key.strip()] = int(digits)
        pages = sum(
            counts.get(name, 0) for name in ("Pages free", "Pages inactive", "Pages speculative")
        )
        return page_size * pages if page_size > 0 and pages > 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def _probe_video_size(source: Path) -> tuple[int, int] | None:
    """Return source ``(width, height)`` using the local ffprobe binary."""
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    try:
        proc = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        stream = json.loads(proc.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        return (width, height) if width > 0 and height > 0 else None
    except (
        OSError,
        ValueError,
        IndexError,
        KeyError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ):
        return None


def _resolved_output_size(
    source_size: tuple[int, int], resolution: str
) -> tuple[int, int] | None:
    """Mirror SeedVR2's resize then center-crop-to-16 output geometry."""
    width, height = source_size
    scale_match = re.fullmatch(r"(\d+(?:\.\d+)?)x", resolution.strip(), re.IGNORECASE)
    try:
        if scale_match:
            scale = float(scale_match.group(1))
        else:
            scale = float(resolution) / min(width, height)
    except ValueError:
        return None
    if scale <= 0:
        return None
    output_width = max(2, round(width * scale))
    output_height = max(2, round(height * scale))
    output_width -= output_width % 16
    output_height -= output_height % 16
    if output_width <= 0 or output_height <= 0:
        return None
    return output_width, output_height


def _estimated_working_set_bytes(*, frame_count: int, width: int, height: int) -> int:
    """Replicate mlx-gen 0.38.0's SeedVR2 3B working-set estimator."""
    latent_height = max(1, height // 8)
    latent_width = max(1, width // 8)
    patch_tokens_per_frame = max(1, (latent_height // 2) * (latent_width // 2))
    video_tokens = frame_count * patch_tokens_per_frame
    qkv_bytes = video_tokens * 3 * SEEDVR2_INNER_DIM * 2
    processed_video_bytes = frame_count * height * width * 3 * 4
    decoded_video_bytes = frame_count * height * width * 3 * 2
    latent_bytes = frame_count * latent_height * latent_width * 16 * 2
    return int(
        (qkv_bytes * 2.0)
        + processed_video_bytes
        + decoded_video_bytes
        + (latent_bytes * 4)
    )


def _resident_model_bytes(model_path: Path) -> int:
    """Conservatively estimate resident model memory from local weight files."""
    weight_bytes = sum(path.stat().st_size for path in model_path.rglob("*.safetensors"))
    return int(weight_bytes * MODEL_RESIDENCY_FACTOR)


def enhance_video(
    input_path: str,
    output_path: str,
    *,
    resolution: str = "1x",
    softness: float = 0.0,
    color_correction: str = "wavelet",
    temporal_chunk_size: int = 49,
    temporal_chunk_overlap: int = 16,
    cache_limit_gb: float = 1.0,
    start_seconds: float = 0.0,
    max_frames: int | None = None,
    seed: int | None = None,
    drop_audio: bool = False,
    guarded_memory_override: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    source = Path(input_path)
    target = Path(output_path)
    if not source.is_file():
        return {"success": False, "error": f"Eingabevideo fehlt: {source}"}
    if target.exists():
        return {"success": False, "error": f"Ausgabe existiert bereits: {target}"}
    if not MODEL_PATH.is_dir():
        return {"success": False, "error": f"SeedVR2-Modell fehlt: {MODEL_PATH}"}
    missing = _missing_model_files(MODEL_PATH)
    if missing:
        preview = ", ".join(missing[:4])
        return {
            "success": False,
            "error": f"SeedVR2-Modell ist unvollständig ({preview}).",
        }
    if not (0.0 <= softness <= 1.0):
        return {"success": False, "error": "--softness muss zwischen 0.0 und 1.0 liegen."}
    if color_correction not in COLOR_CORRECTIONS:
        return {
            "success": False,
            "error": f"Unbekannte Farbkorrektur: {color_correction}",
        }
    if temporal_chunk_size < 5 or (temporal_chunk_size - 1) % 4:
        return {
            "success": False,
            "error": "--temporal-chunk-size muss der Form 4n+1 entsprechen.",
        }
    if not 0 <= temporal_chunk_overlap < temporal_chunk_size:
        return {
            "success": False,
            "error": "--temporal-chunk-overlap muss kleiner als die Chunk-Größe sein.",
        }
    if temporal_chunk_overlap % 4:
        return {
            "success": False,
            "error": "--temporal-chunk-overlap muss durch 4 teilbar sein.",
        }
    if cache_limit_gb <= 0:
        return {"success": False, "error": "--mlx-cache-limit-gb muss positiv sein."}
    if start_seconds < 0 or (max_frames is not None and max_frames <= 0):
        return {"success": False, "error": "Ungültiger Videoausschnitt."}
    available_memory = None
    memory_plan = None
    if guarded_memory_override:
        if cache_limit_gb > 1.0:
            return {
                "success": False,
                "error": "Guarded Override erlaubt maximal 1 GB MLX-Cache.",
            }
        if max_frames is None or max_frames > VERIFIED_MAX_CHUNK_FRAMES:
            return {
                "success": False,
                "error": (
                    "Guarded Override ist derzeit auf explizit höchstens 5 Frames "
                    "Gesamtlänge begrenzt."
                ),
            }
        source_size = _probe_video_size(source)
        output_size = (
            None if source_size is None else _resolved_output_size(source_size, resolution)
        )
        if source_size is None or output_size is None:
            return {
                "success": False,
                "error": (
                    "Guarded Override benötigt eine messbare Video- und Zielauflösung; "
                    "ffprobe oder --resolution lieferte keine sichere Geometrie."
                ),
            }
        available_memory = _host_available_memory_bytes()
        if available_memory is None:
            return {
                "success": False,
                "error": "Guarded Override kann den verfügbaren RAM nicht sicher messen.",
            }
        effective_chunk_frames = temporal_chunk_size
        if max_frames is not None:
            effective_chunk_frames = min(effective_chunk_frames, max_frames)
        padded_chunk_frames = 1 if effective_chunk_frames == 1 else (
            effective_chunk_frames + (4 - ((effective_chunk_frames - 1) % 4)) % 4
        )
        output_width, output_height = output_size
        if output_width * output_height > source_size[0] * source_size[1]:
            return {
                "success": False,
                "error": (
                    "SeedVR2-Upscaling (>1x) ist auf diesem 24-GB-Mac gesperrt: "
                    "ein realer 640x360→1280x720-Metal-Test endete mit OOM. "
                    "Quellgrößen-Restauration bis 1x bleibt verfügbar."
                ),
            }
        if (
            output_width > VERIFIED_MAX_OUTPUT_WIDTH
            or output_height > VERIFIED_MAX_OUTPUT_HEIGHT
            or temporal_chunk_size > VERIFIED_MAX_CHUNK_FRAMES
        ):
            return {
                "success": False,
                "error": (
                    "Guarded Override überschreitet den real verifizierten Bereich "
                    "von maximal 640x352, Chunk 5 und insgesamt 5 Frames."
                ),
            }
        working_bytes = _estimated_working_set_bytes(
            frame_count=padded_chunk_frames,
            width=output_width,
            height=output_height,
        )
        resident_bytes = _resident_model_bytes(MODEL_PATH)
        calibrated_working_bytes = int(working_bytes * METAL_EMPIRICAL_WORKING_SET_FACTOR)
        required_available = max(
            GUARDED_OVERRIDE_MIN_AVAILABLE_BYTES,
            resident_bytes
            + calibrated_working_bytes
            + GUARDED_OVERRIDE_SYSTEM_RESERVE_BYTES,
        )
        memory_plan = {
            "source_size": f"{source_size[0]}x{source_size[1]}",
            "output_size": f"{output_width}x{output_height}",
            "chunk_frames": padded_chunk_frames,
            "estimated_working_gb": round(working_bytes / (1000**3), 2),
            "calibrated_working_gb": round(calibrated_working_bytes / (1000**3), 2),
            "resident_model_gb": round(resident_bytes / (1000**3), 2),
            "required_available_gb": round(required_available / (1000**3), 2),
            "available_gb": round(available_memory / (1000**3), 2),
        }
        if available_memory < required_available:
            return {
                "success": False,
                "error": (
                    "Guarded Override verweigert diese Arbeitslast: "
                    f"benötigt {required_available / (1000**3):.2f} GB verfügbaren RAM, "
                    f"gemessen {available_memory / (1000**3):.2f} GB "
                    f"({output_width}x{output_height}, {padded_chunk_frames} Frames)."
                ),
                "memory_plan": memory_plan,
            }

    executable = shutil.which("mflux-upscale-seedvr2")
    if not executable:
        return {
            "success": False,
            "error": "mflux-upscale-seedvr2 ist nicht installiert/im PATH.",
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        executable,
        "--model",
        str(MODEL_PATH),
        "--video-path",
        str(source),
        "--resolution",
        resolution,
        "--softness",
        str(softness),
        "--color-correction",
        color_correction,
        "--temporal-chunk-size",
        str(temporal_chunk_size),
        "--temporal-chunk-overlap",
        str(temporal_chunk_overlap),
        "--mlx-cache-limit-gb",
        str(cache_limit_gb),
        "--low-ram",
        "--no-replace",
        "--output",
        str(target),
    ]
    if start_seconds:
        cmd += ["--start-seconds", str(start_seconds)]
    if max_frames is not None:
        cmd += ["--max-frames", str(max_frames)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if drop_audio:
        cmd.append("--drop-audio")
    if guarded_memory_override:
        cmd.append("--force-unsafe-video-memory")

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "input": str(source),
            "output": str(target),
            "command": cmd,
            "guarded_memory_override": guarded_memory_override,
            "available_memory_gb": (
                None if available_memory is None else round(available_memory / (1000**3), 2)
            ),
            "memory_plan": memory_plan,
        }
    if verbose:
        print(
            f"SeedVR2 lokal ({resolution}, {color_correction}, "
            f"chunk {temporal_chunk_size}/{temporal_chunk_overlap})...",
            file=sys.stderr,
        )

    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "SeedVR2 wurde nach 120 Minuten kontrolliert abgebrochen.",
        }
    if proc.returncode != 0:
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout).strip()[-3000:],
        }
    if not target.is_file() or target.stat().st_size == 0:
        return {
            "success": False,
            "error": f"SeedVR2 meldete Erfolg, erzeugte aber keine Ausgabe: {target}",
        }
    return {
        "success": True,
        "input": str(source),
        "output": str(target),
        "resolution": resolution,
        "color_correction": color_correction,
        "processing_time_seconds": round(time.monotonic() - started, 2),
        "guarded_memory_override": guarded_memory_override,
        "memory_plan": memory_plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Lokales Eingabevideo")
    parser.add_argument("--output", required=True, help="Neuer Ausgabepfad")
    parser.add_argument("--resolution", default="1x", help="Zielgröße, z. B. 1x oder 2x")
    parser.add_argument("--softness", type=float, default=0.0)
    parser.add_argument("--color-correction", choices=COLOR_CORRECTIONS, default="wavelet")
    parser.add_argument("--temporal-chunk-size", type=int, default=49)
    parser.add_argument("--temporal-chunk-overlap", type=int, default=16)
    parser.add_argument("--mlx-cache-limit-gb", type=float, default=1.0)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--drop-audio", action="store_true")
    parser.add_argument(
        "--guarded-memory-override",
        action="store_true",
        help=(
            "Pass mlx-gen's override only after a workload-specific preflight reproduces "
            "its estimator, applies the measured Metal safety factor, and reserves model "
            "residency plus 2 GB for the system; upscaling above 1x is blocked"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = enhance_video(
        args.input,
        args.output,
        resolution=args.resolution,
        softness=args.softness,
        color_correction=args.color_correction,
        temporal_chunk_size=args.temporal_chunk_size,
        temporal_chunk_overlap=args.temporal_chunk_overlap,
        cache_limit_gb=args.mlx_cache_limit_gb,
        start_seconds=args.start_seconds,
        max_frames=args.max_frames,
        seed=args.seed,
        drop_audio=args.drop_audio,
        guarded_memory_override=args.guarded_memory_override,
        dry_run=args.dry_run,
        verbose=not args.json,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["success"]:
        print(result.get("output", "Dry-run erfolgreich."))
    else:
        print(f"Fehler: {result['error']}", file=sys.stderr)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
