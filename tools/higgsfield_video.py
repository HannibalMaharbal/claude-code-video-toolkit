#!/usr/bin/env python3
"""
AI video generation via Higgsfield (cloud, paid) — wraps the installed `higgsfield` CLI.

Cost-gated: always shows the credit cost and current account balance before
spending anything. Generation only runs when --confirm is passed explicitly.
Without --confirm, this only estimates cost and exits (no job is created).

Usage:
    # Show cost only (no --confirm, no charge, no job created)
    python tools/higgsfield_video.py --prompt "cinematic product shot" --output clip.mp4

    # Actually generate (only after reviewing the cost)
    python tools/higgsfield_video.py --prompt "cinematic product shot" --output clip.mp4 --confirm

    # Image-to-video
    python tools/higgsfield_video.py --prompt "camera pans right" --image photo.jpg \\
        --output clip.mp4 --confirm

    # Different model (default: seedance_2_0_mini, cost-efficient)
    python tools/higgsfield_video.py --model kling3_0 --prompt "..." --output clip.mp4

    # List available video models
    python tools/higgsfield_video.py --list-models
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from file_transfer import download_from_url

DEFAULT_MODEL = "seedance_2_0_mini"


def _get_higgsfield_bin() -> str:
    hf_bin = shutil.which("higgsfield")
    if not hf_bin:
        print(
            "Error: higgsfield CLI not found on PATH.\n"
            "\n"
            "Install/login: https://docs.higgsfield.ai "
            "(CLI already installed for this account per setup).\n"
            "Check login with: higgsfield auth token",
            file=sys.stderr,
        )
        sys.exit(1)
    return hf_bin


def _run_json(cmd: list[str]) -> dict | list:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return json.loads(proc.stdout)


def list_models() -> list[dict]:
    hf_bin = _get_higgsfield_bin()
    return _run_json([hf_bin, "model", "list", "--video", "--json"])


def get_balance() -> dict:
    """Parse `higgsfield account status` (plain text: 'email — plan, N credits')."""
    hf_bin = _get_higgsfield_bin()
    proc = subprocess.run([hf_bin, "account", "status"], capture_output=True, text=True)
    text = (proc.stdout or "").strip()
    credits = None
    if "credits" in text:
        try:
            credits = float(text.rsplit(",", 1)[-1].replace("credits", "").strip())
        except ValueError:
            pass
    return {"raw": text, "credits": credits}


def estimate_cost(
    model: str, prompt: str, image: str | None = None, extra_params: dict | None = None,
) -> dict:
    hf_bin = _get_higgsfield_bin()
    cmd = [hf_bin, "generate", "cost", model, "--prompt", prompt, "--json"]
    if image:
        cmd += ["--image", image]
    for k, v in (extra_params or {}).items():
        cmd += [f"--{k}", str(v)]
    return _run_json(cmd)


def create_video(
    model: str,
    prompt: str,
    output_path: str,
    image: str | None = None,
    extra_params: dict | None = None,
    wait_timeout: str = "20m",
) -> dict:
    hf_bin = _get_higgsfield_bin()
    cmd = [
        hf_bin, "generate", "create", model,
        "--prompt", prompt,
        "--wait", "--wait-timeout", wait_timeout,
        "--json",
    ]
    if image:
        cmd += ["--image", image]
    for k, v in (extra_params or {}).items():
        cmd += [f"--{k}", str(v)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"success": False, "error": (proc.stderr or proc.stdout).strip()}

    try:
        jobs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Could not parse higgsfield output: {proc.stdout[:500]}",
        }

    job = jobs[0] if isinstance(jobs, list) else jobs
    result_url = job.get("result_url") or job.get("min_result_url")

    if job.get("status") != "completed" or not result_url:
        return {
            "success": False,
            "error": f"Job did not complete: {json.dumps(job)[:1000]}",
            "job": job,
        }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = download_from_url(result_url, str(output_path), verbose=True)
    if not ok:
        return {"success": False, "error": f"Download failed: {result_url}", "job": job}

    return {
        "success": True,
        "output": str(output_path),
        "job_id": job.get("id"),
        "model": model,
        "result_url": result_url,
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI video generation via Higgsfield CLI (cloud, paid, cost-gated)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/higgsfield_video.py --prompt "cinematic product shot" --output clip.mp4
  python tools/higgsfield_video.py --prompt "..." --output clip.mp4 --confirm
  python tools/higgsfield_video.py --prompt "camera pans right" --image photo.jpg \\
      --output clip.mp4 --confirm
  python tools/higgsfield_video.py --list-models
        """,
    )
    parser.add_argument("--prompt", "-p", type=str, help="Text prompt")
    parser.add_argument("--output", "-o", type=str, help="Output video file (.mp4)")
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help=f"Higgsfield video job_type (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--image", type=str,
        help="Reference image for image-to-video (local path or upload id)",
    )
    parser.add_argument("--duration", type=int, help="Clip duration in seconds (model-dependent)")
    parser.add_argument("--resolution", type=str, help="Resolution, e.g. 720p (model-dependent)")
    parser.add_argument(
        "--aspect-ratio", type=str, help="Aspect ratio, e.g. 16:9 (model-dependent)",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually spend credits and create the job. Without this flag, only cost is shown.",
    )
    parser.add_argument(
        "--list-models", action="store_true", help="List available Higgsfield video models",
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.list_models:
        models = list_models()
        if args.json:
            print(json.dumps(models, indent=2))
        else:
            print("\nHiggsfield video models:\n")
            for m in models:
                print(f"  {m['job_type']:<24} {m['display_name']}")
            print()
        return

    if not args.prompt:
        print("Error: --prompt required", file=sys.stderr)
        sys.exit(1)
    if not args.output:
        print("Error: --output required", file=sys.stderr)
        sys.exit(1)

    extra_params = {}
    if args.duration is not None:
        extra_params["duration"] = args.duration
    if args.resolution:
        extra_params["resolution"] = args.resolution
    if args.aspect_ratio:
        extra_params["aspect-ratio"] = args.aspect_ratio

    try:
        cost = estimate_cost(args.model, args.prompt, image=args.image, extra_params=extra_params)
        balance = get_balance()
    except RuntimeError as e:
        print(f"Error estimating cost: {e}", file=sys.stderr)
        sys.exit(1)

    credits = cost.get("credits")

    if not args.confirm:
        result = {
            "confirmed": False,
            "model": args.model,
            "estimated_credits": credits,
            "account_balance": balance,
            "note": "No job created. Re-run with --confirm to spend credits and generate.",
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Higgsfield cost estimate — model: {args.model}")
            print(f"  Estimated cost: {credits} credits")
            print(f"  Account balance: {balance['raw']}")
            insufficient = (
                balance.get("credits") is not None
                and credits is not None
                and balance["credits"] < credits
            )
            if insufficient:
                print("  WARNING: balance may be insufficient for this generation.")
            print("\nNo job created (no charge). Re-run with --confirm to generate.")
        return

    if not args.json:
        print(
            f"Confirmed — spending ~{credits} credits on {args.model}. "
            "Generating (this can take a few minutes)...",
            file=sys.stderr,
        )

    result = create_video(
        model=args.model,
        prompt=args.prompt,
        output_path=args.output,
        image=args.image,
        extra_params=extra_params,
    )
    result["estimated_credits"] = credits

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("success"):
            print(f"Saved: {result['output']}", file=sys.stderr)
        else:
            print(f"Error: {result.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
