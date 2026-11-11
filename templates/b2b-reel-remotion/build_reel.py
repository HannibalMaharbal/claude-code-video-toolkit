#!/usr/bin/env python3
"""Build & render B2B Remotion Reels with optional MLX Whisper audio alignment.

Usage:
    uv run templates/b2b-reel-remotion/build_reel.py --preview
    uv run templates/b2b-reel-remotion/build_reel.py --input sample-data.json --output out/licbarska_reel.mp4
    uv run templates/b2b-reel-remotion/build_reel.py --audio voice.mp3 --output out/synced_reel.mp4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).resolve().parent
ROOT_DIR = TEMPLATE_DIR.parents[1]
DEFAULT_OUT = TEMPLATE_DIR / "out" / "b2b-reel.mp4"


def align_audio_with_whisper(audio_path: Path) -> list[dict[str, object]]:
    """Generate word-level timestamps using the video-toolkit MLX whisper venv."""
    whisper_bin = ROOT_DIR / ".venv" / "bin" / "mlx_whisper"
    if not whisper_bin.is_file():
        whisper_bin = Path(sys.executable).parent / "mlx_whisper"

    if not whisper_bin.is_file():
        print(f"[warning] mlx_whisper not found at {whisper_bin}. Skipping word alignment.", file=sys.stderr)
        return []

    print(f"[*] Aligning words with MLX Whisper for: {audio_path.name}")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            str(whisper_bin),
            str(audio_path),
            "--word-timestamps", "True",
            "--output-format", "json",
            "--output-dir", tmpdir,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[warning] Whisper failed: {res.stderr}", file=sys.stderr)
            return []

        json_file = Path(tmpdir) / f"{audio_path.stem}.json"
        if not json_file.is_file():
            return []

        data = json.loads(json_file.read_text(encoding="utf-8"))
        words_out = []
        for segment in data.get("segments", []):
            for w in segment.get("words", []):
                words_out.append({
                    "word": w.get("word", "").strip(),
                    "startMs": int(w.get("start", 0) * 1000),
                    "endMs": int(w.get("end", 0) * 1000),
                })
        return words_out


def render_reel(
    data_path: Path,
    output_path: Path,
    preview: bool = False,
    crf: int = 17,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    remotion_bin = ROOT_DIR / "node_modules" / ".bin" / "remotion"
    if not remotion_bin.is_file():
        remotion_bin = Path("npx")
        base_cmd = ["npx", "remotion", "render"]
    else:
        base_cmd = [str(remotion_bin), "render"]

    entry_point = str(TEMPLATE_DIR / "src" / "index.ts")
    comp_id = "B2BReel"

    cmd = base_cmd + [
        entry_point,
        comp_id,
        str(output_path),
        f"--props={str(data_path)}",
        f"--crf={crf}",
    ]
    if preview:
        cmd += ["--scale=0.5", "--crf=23"]

    print(f"[*] Rendering Remotion composition to: {output_path}")
    res = subprocess.run(cmd, cwd=str(TEMPLATE_DIR))
    if res.returncode != 0:
        sys.exit(res.returncode)
    print(f"[SUCCESS] Reel rendered at: {output_path}")


def get_audio_duration(audio_path: Path) -> float:
    """Measure audio duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(res.stdout.strip())
    except Exception as exc:
        raise RuntimeError(
            f"Konnte Audiodauer für {audio_path} nicht via ffprobe ermitteln: {exc}"
        ) from exc

    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(
            f"Ungültige Audiodauer für {audio_path}: {duration}s (muss endlich und > 0 sein)."
        )
    return duration


def validate_audio_src(audio_src: Any) -> str:
    """Validate that audioSrc is a safe relative path under _runtime_voiceover/."""
    if not isinstance(audio_src, str):
        raise ValueError(f"Ungültiger audioSrc-Typ: {type(audio_src)}")
    if "://" in audio_src or audio_src.startswith("/"):
        raise ValueError(f"Ungültiger oder unsicherer audioSrc-Pfad: {audio_src}")
    if not audio_src.startswith("_runtime_voiceover/"):
        raise ValueError(
            f"audioSrc muss ein relativer Pfad unter '_runtime_voiceover/' sein: {audio_src}"
        )
    segments = audio_src.split("/")
    if any(seg in ("..", ".") for seg in segments):
        raise ValueError(f"Ungültiger oder unsicherer audioSrc-Pfad: {audio_src}")
    return audio_src


def prepare_reel_payload(
    input_data: dict[str, Any],
    audio_path: Path | None = None,
    *,
    template_dir: Path = TEMPLATE_DIR,
) -> dict[str, Any]:
    """Prepare reel data payload, align Whisper captions, and copy audio to public/."""
    data = dict(input_data)
    if "audioSrc" in data and data["audioSrc"] is not None:
        validate_audio_src(data["audioSrc"])
    if audio_path and Path(audio_path).is_file():
        audio_file = Path(audio_path)
        audio_duration = get_audio_duration(audio_file)
        if audio_duration > 0:
            current_duration = float(data.get("durationInSeconds", 0))
            required_duration = round(audio_duration + 3.5, 2)
            data["durationInSeconds"] = max(current_duration, required_duration)

        captions = align_audio_with_whisper(audio_file)
        if captions:
            data["captions"] = captions
        voiceover_dir = template_dir / "public" / "_runtime_voiceover"
        voiceover_dir.mkdir(parents=True, exist_ok=True)
        raw_stem = audio_file.stem
        raw_suffix = audio_file.suffix
        clean_stem = re.sub(r"[^A-Za-z0-9._-]", "_", raw_stem)
        if clean_stem in ("..", ".", ""):
            clean_stem = f"audio_{clean_stem}".replace("..", "_")
        clean_suffix = re.sub(r"[^A-Za-z0-9.]", "", raw_suffix) if raw_suffix else ".mp3"
        content_hash = hashlib.sha256(audio_file.read_bytes()).hexdigest()[:10]
        dest_filename = f"{clean_stem}_{content_hash}{clean_suffix}"
        dest_path = voiceover_dir / dest_filename
        shutil.copy2(audio_file, dest_path)
        data["audioSrc"] = validate_audio_src(f"_runtime_voiceover/{dest_filename}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Render B2B Remotion Reel")
    parser.add_argument("--input", "-i", type=Path, default=TEMPLATE_DIR / "sample-data.json")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--audio", "-a", type=Path, help="Optional voiceover MP3 to align with Whisper")
    parser.add_argument("--preview", action="store_true", help="Render fast half-resolution preview")
    args = parser.parse_args()

    input_data = json.loads(args.input.read_text(encoding="utf-8"))
    payload = prepare_reel_payload(input_data, audio_path=args.audio, template_dir=TEMPLATE_DIR)

    temp_data = TEMPLATE_DIR / "out" / "_runtime_props.json"
    temp_data.parent.mkdir(parents=True, exist_ok=True)
    temp_data.write_text(json.dumps({"data": payload}, indent=2), encoding="utf-8")
    render_reel(temp_data, args.output, preview=args.preview)


if __name__ == "__main__":
    main()
