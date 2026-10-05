#!/usr/bin/env python3
"""
Shared local video engine for Creator Studio: LTX-2.5 via the `ltx-2-mlx`
runtime (native MLX, no ComfyUI/GGUF/PyTorch stack). Replaces Wan 2.2 TI2V-5B.

All five Creator Studio video features (Video erstellen, Storyboard, Story
9:16, Produkt-Varianten, Video verlaengern) call this ONE adapter instead of
implementing their own LTX invocation.

CLI contract matches the removed wan_mlx_adapter.py so callers needed only
their wrapper-path constant changed:
    python tools/ltx25_mlx_adapter.py --prompt "..." --output clip.mp4 \
        --mode two-stage --frames 97 --frame-rate 24 \
        --width 704 --height 480 [--image photo.jpg] [--seed 42]

LTX-2.5 natively uses 8n+1 frames and canvas dimensions divisible by 32.
This project's own frame convention (seconds*24+1) and every configured
canvas size already satisfy both (24n+1 = 8*(3n)+1; every width/height in
use is a multiple of 32), so --frames/--width/--height pass through
unchanged, no retiming/rescaling step needed on this side.

Runtime pin (per the model card at ~/AI-Modelle/ltx-2.5-mlx-q8/README.md):
    https://github.com/MrMoferFRAN/ltx-2-mlx, branch `ltx25`,
    commit 57952288076766abe27dda3a774b2c24f7346977.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RUNTIME_DIR = Path.home() / "AI-Modelle" / "ltx-2-mlx"
MODEL_PATH = Path.home() / "AI-Modelle" / "ltx-2.5-mlx-q8"
MODE_FLAGS = {
    "distilled": "--distilled",
    "two-stage": "--two-stage",
    "two-stages-hq": "--two-stages-hq",
    "one-stage": "--one-stage",
}


def _resolve_model() -> str:
    return str(MODEL_PATH)


def generate_video(
    prompt: str,
    output_path: str,
    mode: str = "distilled",
    width: int = 704,
    height: int = 480,
    frames: int = 97,
    frame_rate: int = 24,
    seed: int | None = None,
    image: str | None = None,
    verbose: bool = True,
) -> dict:
    if mode not in MODE_FLAGS:
        return {"success": False, "error": f"Unknown mode '{mode}', expected one of {sorted(MODE_FLAGS)}"}
    if width % 32 or height % 32:
        return {"success": False, "error": f"LTX-2.5 braucht Breite/Höhe durch 32 teilbar, bekommen: {width}x{height}."}
    if (frames - 1) % 8:
        return {"success": False, "error": f"LTX-2.5 braucht Frames der Form 8n+1, bekommen: {frames}."}
    if mode in ("two-stage", "two-stages-hq", "one-stage") and not (MODEL_PATH / "transformer-dev.safetensors").is_file():
        return {"success": False, "error": f"Modus '{mode}' braucht transformer-dev.safetensors, fehlt unter {MODEL_PATH}."}

    uv = shutil.which("uv")
    if not uv:
        return {"success": False, "error": "uv ist nicht installiert/im PATH."}
    if not RUNTIME_DIR.is_dir():
        return {"success": False, "error": f"ltx-2-mlx-Runtime fehlt unter {RUNTIME_DIR}."}
    if not MODEL_PATH.is_dir():
        return {"success": False, "error": f"LTX-2.5-Modell fehlt unter {MODEL_PATH}."}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    task = "image-to-video" if image else "text-to-video"

    cmd = [
        uv, "run", "ltx-2-mlx", "generate",
        "--model", _resolve_model(),
        MODE_FLAGS[mode],
        "--low-ram",
        "--prompt", prompt,
        "--width", str(width),
        "--height", str(height),
        "--frames", str(frames),
        "--frame-rate", str(frame_rate),
        "--output", str(output_path),
    ]
    if image:
        cmd += ["--image", image]
    if seed is not None:
        cmd += ["--seed", str(seed)]

    if verbose:
        print(
            f"LTX-2.5 ({mode}, {task}, {width}x{height}, {frames}f @ {frame_rate}fps)...",
            file=sys.stderr,
        )

    start_time = time.time()
    proc = subprocess.run(cmd, cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=4 * 60 * 60)
    elapsed_ms = int((time.time() - start_time) * 1000)

    if proc.returncode != 0:
        return {"success": False, "error": (proc.stderr or proc.stdout).strip()[-2000:]}
    if not output_path.exists() or output_path.stat().st_size == 0:
        return {"success": False, "error": f"ltx-2-mlx reported success but {output_path} was not created"}

    return {
        "success": True,
        "output": str(output_path),
        "mode": mode,
        "width": width,
        "height": height,
        "frames": frames,
        "frame_rate": frame_rate,
        "seed": seed,
        "inference_time_ms": elapsed_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", default="distilled", choices=sorted(MODE_FLAGS))
    parser.add_argument("--frames", type=int, default=97)
    parser.add_argument("--frame-rate", type=int, default=24)
    parser.add_argument("--width", type=int, default=704)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--image", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    result = generate_video(
        prompt=args.prompt, output_path=args.output, mode=args.mode,
        width=args.width, height=args.height, frames=args.frames,
        frame_rate=args.frame_rate, seed=args.seed, image=args.image,
    )
    print(json.dumps(result))
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
