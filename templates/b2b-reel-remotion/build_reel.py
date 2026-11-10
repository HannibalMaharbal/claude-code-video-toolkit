#!/usr/bin/env python3
"""Build & render B2B Remotion Reels with optional MLX Whisper audio alignment.

Usage:
    uv run templates/b2b-reel-remotion/build_reel.py --preview
    uv run templates/b2b-reel-remotion/build_reel.py --input sample-data.json --output out/licbarska_reel.mp4
    uv run templates/b2b-reel-remotion/build_reel.py --audio voice.mp3 --output out/synced_reel.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Render B2B Remotion Reel")
    parser.add_argument("--input", "-i", type=Path, default=TEMPLATE_DIR / "sample-data.json")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--audio", "-a", type=Path, help="Optional voiceover MP3 to align with Whisper")
    parser.add_argument("--preview", action="store_true", help="Render fast half-resolution preview")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))

    if args.audio and args.audio.is_file():
        captions = align_audio_with_whisper(args.audio)
        if captions:
            data["captions"] = captions
        temp_data = TEMPLATE_DIR / "out" / "_runtime_props.json"
        temp_data.parent.mkdir(parents=True, exist_ok=True)
        temp_data.write_text(json.dumps({"data": data}, indent=2), encoding="utf-8")
        render_reel(temp_data, args.output, preview=args.preview)
    else:
        # Wrap data in { "data": ... } matching Root.tsx defaultProps
        temp_data = TEMPLATE_DIR / "out" / "_runtime_props.json"
        temp_data.parent.mkdir(parents=True, exist_ok=True)
        temp_data.write_text(json.dumps({"data": data}, indent=2), encoding="utf-8")
        render_reel(temp_data, args.output, preview=args.preview)


if __name__ == "__main__":
    main()
