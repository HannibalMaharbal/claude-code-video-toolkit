#!/usr/bin/env python3
"""
Generate images locally with Z-Image Turbo via MLX-Gen (Apple Silicon).

Local, offline image generation — no API key, no cloud cost. Uses the
already-cached 4-bit quantized snapshot by default so no model download is
triggered. Text-to-image only (no editing/video — see flux2.py / image_edit.py
for cloud editing, ltx2.py for cloud video).

Usage:
    python tools/z_image.py --prompt "A puffin on a cliff" --output puffin.png
    python tools/z_image.py --prompt "Product shot" --width 1024 --height 1024 --steps 6
    python tools/z_image.py --prompt "..." --seed 42 --output out.png

Setup:
    Requires mlxgen (already installed) and the cached model:
      mlxgen download --model AbstractFramework/z-image-turbo-4bit
    (already present locally as of this integration; not re-triggered here)
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_MODEL = "AbstractFramework/z-image-turbo-4bit"
DEFAULT_STEPS = 9
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024


def _get_mlxgen_bin() -> str:
    mlxgen_bin = shutil.which("mlxgen")
    if not mlxgen_bin:
        print(
            "Error: mlxgen binary not found on PATH.\n"
            "\n"
            "Expected at ~/.local/bin/mlxgen. If it's installed elsewhere, add it to PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    return mlxgen_bin


def generate_image(
    prompt: str,
    output_path: str,
    model: str = DEFAULT_MODEL,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    steps: int = DEFAULT_STEPS,
    seed: int | None = None,
    negative_prompt: str | None = None,
    verbose: bool = True,
) -> dict:
    """Generate an image with Z-Image Turbo via mlxgen. Returns result dict."""
    mlxgen_bin = _get_mlxgen_bin()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        mlxgen_bin, "generate",
        "--model", model,
        "--prompt", prompt,
        "--width", str(width),
        "--height", str(height),
        "--steps", str(steps),
        "--output", str(output_path),
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if negative_prompt:
        cmd += ["--negative-prompt", negative_prompt]

    if verbose:
        print(f"Z-Image Turbo ({model}): {width}x{height}, {steps} steps...", file=sys.stderr)

    start_time = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Bildgenerierung nach 10 Minuten wegen Zeitlimit kontrolliert abgebrochen.",
        }
    elapsed_ms = int((time.time() - start_time) * 1000)

    if proc.returncode != 0:
        return {
            "success": False,
            "error": (proc.stderr or proc.stdout).strip()[-2000:],
        }

    if not output_path.exists():
        return {
            "success": False,
            "error": f"mlxgen reported success but {output_path} was not created",
        }

    return {
        "success": True,
        "output": str(output_path),
        "model": model,
        "width": width,
        "height": height,
        "steps": steps,
        "seed": seed,
        "inference_time_ms": elapsed_ms,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate images locally with Z-Image Turbo via MLX-Gen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/z_image.py --prompt "A puffin on a cliff" --output puffin.png
  python tools/z_image.py --prompt "Product shot" --width 1024 --height 1024 --steps 6
  python tools/z_image.py --prompt "..." --seed 42 --output out.png
        """,
    )
    parser.add_argument("--prompt", "-p", type=str, help="Text prompt")
    parser.add_argument("--output", "-o", type=str, help="Output image file (.png)")
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"MLX-Gen model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--width", type=int, default=DEFAULT_WIDTH,
        help=f"Image width (default: {DEFAULT_WIDTH})",
    )
    parser.add_argument(
        "--height", type=int, default=DEFAULT_HEIGHT,
        help=f"Image height (default: {DEFAULT_HEIGHT})",
    )
    parser.add_argument(
        "--steps", type=int, default=DEFAULT_STEPS,
        help=f"Diffusion steps (default: {DEFAULT_STEPS}, recommended for Z-Image Turbo)",
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument("--negative-prompt", type=str, help="Negative prompt")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if not args.prompt:
        print("Error: --prompt required", file=sys.stderr)
        sys.exit(1)
    if not args.output:
        print("Error: --output required", file=sys.stderr)
        sys.exit(1)

    result = generate_image(
        prompt=args.prompt,
        output_path=args.output,
        model=args.model,
        width=args.width,
        height=args.height,
        steps=args.steps,
        seed=args.seed,
        negative_prompt=args.negative_prompt,
        verbose=not args.json,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            print(f"Saved: {args.output} ({result['inference_time_ms']}ms)", file=sys.stderr)
        else:
            print(f"Error: {result.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
