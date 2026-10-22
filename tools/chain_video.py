#!/usr/bin/env python3
"""
Chain local LTX-2.5-MLX video clips with visual continuity.

Generates a sequence of video clips where each scene uses the last frame
of the previous scene as input, creating seamless visual flow.

Input modes:
  --scenes-dir DIR     Directory of numbered images (01.png, 02.png, ...)
                       First image seeds scene 1, each subsequent scene chains
                       from the previous clip's last frame.
  --first-clip FILE    Start chaining from an existing video clip.
                       Extracts last frame and generates the next scene.

Examples:
  # Chain 10 scenes from a directory of FLUX images
  uv run tools/chain_video.py \\
      --scenes-dir projects/myproject/public/images/scenes/ \\
      --output-dir projects/myproject/public/videos/chain/ \\
      --prompt "Cinematic transition, flowing camera movement" \\
      --progress json

  # Chain from scene 5 to 30 (resume interrupted run)
  uv run tools/chain_video.py \\
      --scenes-dir projects/myproject/public/images/scenes/ \\
      --output-dir projects/myproject/public/videos/chain/ \\
      --start 5 --end 30 \\
      --prompt "Celtic mythology, cinematic flow" \\
      --progress json

  # Chain with per-scene prompts from a JSON file
  uv run tools/chain_video.py \\
      --scenes-dir projects/myproject/public/images/scenes/ \\
      --output-dir projects/myproject/public/videos/chain/ \\
      --prompts-file scenes.json \\
      --progress json

  # Resume from an existing clip
  uv run tools/chain_video.py \\
      --first-clip output/chain-04.mp4 \\
      --output-dir output/ \\
      --start 5 --end 30 \\
      --prompt "Flowing transition" \\
      --progress json
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def progress(stage, msg, pct=None, elapsed=0.0):
    """Emit structured progress to stderr."""
    ts = time.strftime("%H:%M:%S")
    obj = {"ts": ts, "stage": stage, "msg": msg, "pct": pct, "elapsed": round(elapsed, 1)}
    print(json.dumps(obj), file=sys.stderr, flush=True)


def find_scene_images(scenes_dir, start, end):
    """Find numbered scene images in a directory."""
    images = {}
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for f in glob.glob(os.path.join(scenes_dir, ext)):
            basename = os.path.splitext(os.path.basename(f))[0]
            # Extract leading number from filename (01-title.png -> 1)
            num_str = ""
            for ch in basename:
                if ch.isdigit():
                    num_str += ch
                else:
                    break
            if num_str:
                num = int(num_str)
                if start <= num <= end:
                    images[num] = f
    return images


SCENE_TIMEOUT = 1860  # Adapter limit is 30 minutes; allow cleanup and result handling.


def generate_scene(input_image, previous_clip, prompt, output_path, extra_args):
    """Run the local LTX-2.5 adapter with exactly one visual start source."""
    cmd = [
        sys.executable,
        os.path.join(TOOLKIT_ROOT, "tools", "ltx25_mlx_adapter.py"),
        "--prompt", prompt,
        "--output", output_path,
    ]
    if previous_clip:
        cmd.extend(["--continue-from", previous_clip])
    elif input_image:
        cmd.extend(["--image", input_image])
    else:
        raise RuntimeError("scene has neither a previous clip nor an input image")
    cmd.extend(extra_args)

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=SCENE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ltx25_mlx_adapter.py timed out after {SCENE_TIMEOUT}s for {output_path}"
        )
    if result.returncode != 0:
        stderr_tail = result.stderr.decode(errors="replace")[-300:] if result.stderr else ""
        stdout_tail = result.stdout.decode(errors="replace")[-300:] if result.stdout else ""
        detail = stderr_tail or stdout_tail
        raise RuntimeError(f"ltx25_mlx_adapter.py failed for {output_path}: {detail}")
    if not os.path.exists(output_path):
        raise RuntimeError(f"ltx25_mlx_adapter.py produced no output: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Chain LTX-2 video clips with visual continuity")
    parser.add_argument("--scenes-dir", help="Directory of numbered scene images")
    parser.add_argument("--first-clip", help="Start chaining from this existing video clip")
    parser.add_argument("--output-dir", required=True, help="Output directory for chained clips")
    parser.add_argument(
        "--prompt",
        default="Cinematic continuation, flowing transition",
        help="Default prompt for all scenes",
    )
    parser.add_argument(
        "--prompts-file",
        help='JSON file with per-scene prompts: {"1": "prompt", ...}',
    )
    parser.add_argument("--start", type=int, default=1, help="First scene number (default: 1)")
    parser.add_argument("--end", type=int, default=30, help="Last scene number (default: 30)")
    parser.add_argument("--prefix", default="chain", help="Output filename prefix (default: chain)")
    parser.add_argument(
        "--progress",
        choices=["json", "human"],
        default="human",
        help="Progress output format",
    )

    args, extra = parser.parse_known_args()
    use_progress = args.progress == "json"
    t0 = time.time()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load per-scene prompts if provided
    scene_prompts = {}
    if args.prompts_file:
        try:
            with open(args.prompts_file) as f:
                raw = json.load(f)
            scene_prompts = {int(k): v for k, v in raw.items()}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"ERROR: Invalid prompts file {args.prompts_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Find scene images
    scene_images = {}
    if args.scenes_dir:
        scene_images = find_scene_images(args.scenes_dir, args.start, args.end)

    total = args.end - args.start + 1
    completed = 0
    prev_clip = args.first_clip

    for i in range(args.start, args.end + 1):
        curr = f"{i:02d}"
        output_path = os.path.join(args.output_dir, f"{args.prefix}-{curr}.mp4")
        prompt = scene_prompts.get(i, args.prompt)
        elapsed = time.time() - t0

        # Skip if already exists — prefer exact name, else glob for suffix
        # variants (chain-05-brigid.mp4)
        if os.path.exists(output_path):
            existing = [output_path]
        else:
            existing = glob.glob(os.path.join(args.output_dir, f"{args.prefix}-{curr}-*.mp4"))
        if existing:
            found = existing[0]
            pct = round(completed / total * 100)
            if use_progress:
                progress(
                    "item",
                    f"Scene {curr} already exists ({os.path.basename(found)}), skipping",
                    pct=pct,
                    elapsed=elapsed,
                )
            else:
                print(f"Scene {curr} already exists ({os.path.basename(found)}), skipping")
            completed += 1
            prev_clip = found
            continue

        if use_progress:
            progress(
                "item",
                f"Starting scene {curr}/{args.end} ({completed}/{total} done)",
                pct=round(completed / total * 100),
                elapsed=elapsed,
            )
        else:
            print(f"\n--- Scene {curr}/{args.end} ---")

        # Continue directly from the preceding clip. The local adapter owns
        # end-frame extraction, cleanup and fail-fast input validation.
        input_image = None
        if not prev_clip and i in scene_images:
            input_image = scene_images[i]

        if not prev_clip and not input_image:
            msg = f"Scene {curr}: no input image and no previous clip to chain from, skipping"
            if use_progress:
                progress("error", msg, elapsed=time.time() - t0)
            else:
                print(f"ERROR: {msg}")
            continue

        # Generate
        try:
            generate_scene(input_image, prev_clip, prompt, output_path, extra)
            prev_clip = output_path
            completed += 1
            elapsed = time.time() - t0
            if use_progress:
                progress(
                    "item",
                    f"Scene {curr} complete ({completed}/{total})",
                    pct=round(completed / total * 100),
                    elapsed=elapsed,
                )
            else:
                print(f"DING: Scene {curr} done ({completed}/{total})")
        except RuntimeError as e:
            elapsed = time.time() - t0
            if use_progress:
                progress("error", f"Scene {curr} failed: {e}", elapsed=elapsed)
            else:
                print(f"ERROR: Scene {curr} failed: {e}")
            # Don't chain from a failed scene — keep prev_clip as is
            continue

    elapsed = time.time() - t0
    if use_progress:
        progress(
            "complete",
            f"All done: {completed}/{total} scenes in {elapsed:.0f}s",
            pct=100,
            elapsed=elapsed,
        )
    else:
        print(f"\nALL DONE: {completed}/{total} scenes in {elapsed:.0f}s")


if __name__ == "__main__":
    main()
