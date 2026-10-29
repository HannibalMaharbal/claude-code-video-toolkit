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
import math
import os
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from file_transfer import download_from_url

DEFAULT_MODEL = "seedance_2_0_mini"
QUOTE_TIMEOUT_SECONDS = 120
JOB_TIMEOUT_SECONDS = 1500


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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=QUOTE_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return json.loads(proc.stdout)


def list_models() -> list[dict]:
    hf_bin = _get_higgsfield_bin()
    return _run_json([hf_bin, "model", "list", "--video", "--json"])


def get_balance() -> dict:
    """Parse `higgsfield account status` (plain text: 'email — plan, N credits')."""
    hf_bin = _get_higgsfield_bin()
    proc = subprocess.run([hf_bin, "account", "status"], capture_output=True, text=True, timeout=QUOTE_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError("Higgsfield-Kontostatus nicht verfügbar")
    text = (proc.stdout or "").strip()
    credits = None
    if "credits" in text:
        try:
            credits = float(text.rsplit(",", 1)[-1].replace("credits", "").strip())
        except ValueError:
            pass
    return {"raw": text, "credits": credits}


def estimate_cost(
    model: str, prompt: str | None = None, image: str | None = None, video: str | None = None, extra_params: dict | None = None,
) -> dict:
    hf_bin = _get_higgsfield_bin()
    cmd = [hf_bin, "generate", "cost", model, "--json"]
    if prompt:
        cmd += ["--prompt", prompt]
    if image:
        cmd += ["--image", image]
    if video:
        cmd += ["--video", video]
    for k, v in (extra_params or {}).items():
        cmd += [f"--{k}", str(v)]
    return _run_json(cmd)


def _download_job_result(result_url: str, output_path: str, job: dict) -> dict | None:
    target = Path(output_path)
    temp_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".higgsfield-", suffix=".part", delete=False) as temp:
            temp_path = Path(temp.name)
        if not download_from_url(result_url, str(temp_path), verbose=True):
            raise OSError("Download fehlgeschlagen")
        os.link(temp_path, target)
        return None
    except OSError as exc:
        return {"success": False, "error": f"Download fehlgeschlagen ({exc}); Job-ID {job.get('id', 'unbekannt')}. Anbieterstatus und Download prüfen, nicht neu generieren.", "job": job}
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                print(f"Temporäre Datei konnte nicht entfernt werden: {temp_path}", file=sys.stderr)


def upscale_video(
    video_path: str,
    output_path: str,
    resolution: str = "1080p",
    preset: str = "aigc",
    wait_timeout: str = "20m",
) -> dict:
    """Upscale video using ByteDance Video Upscale on Higgsfield."""
    hf_bin = _get_higgsfield_bin()
    cmd = [
        hf_bin, "generate", "create", "bytedance_video_upscale",
        "--video", video_path,
        "--resolution", resolution,
        "--preset", preset,
        "--wait", "--wait-timeout", wait_timeout,
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Zeitüberschreitung: Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen."}
    if proc.returncode != 0:
        return {"success": False, "error": (proc.stderr or proc.stdout).strip() + " Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen."}

    try:
        jobs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Could not parse higgsfield output: {proc.stdout[:500]}. Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen.",
        }

    if isinstance(jobs, list):
        jobs = jobs[0] if jobs else None
    if not isinstance(jobs, dict):
        return {"success": False, "error": "Ungültige Job-Antwort; Anbieterstatus vor einem erneuten Auftrag prüfen."}
    job = jobs
    result_url = job.get("result_url") or job.get("min_result_url")

    if job.get("status") != "completed" or not result_url:
        return {
            "success": False,
            "error": f"Upscale job did not complete: {json.dumps(job)[:1000]}",
            "job": job,
        }

    error = _download_job_result(result_url, output_path, job)
    if error:
        return error

    return {
        "success": True,
        "output": str(output_path),
        "job_id": job.get("id"),
        "model": "bytedance_video_upscale",
        "result_url": result_url,
    }


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

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Zeitüberschreitung: Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen."}
    if proc.returncode != 0:
        return {"success": False, "error": (proc.stderr or proc.stdout).strip() + " Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen."}

    try:
        jobs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": f"Could not parse higgsfield output: {proc.stdout[:500]}. Anbieterstatus und mögliche Abbuchung vor erneutem Auftrag prüfen.",
        }

    if isinstance(jobs, list):
        jobs = jobs[0] if jobs else None
    if not isinstance(jobs, dict):
        return {"success": False, "error": "Ungültige Job-Antwort; Anbieterstatus vor einem erneuten Auftrag prüfen."}
    job = jobs
    result_url = job.get("result_url") or job.get("min_result_url")

    if job.get("status") != "completed" or not result_url:
        return {
            "success": False,
            "error": f"Job did not complete: {json.dumps(job)[:1000]}",
            "job": job,
        }

    error = _download_job_result(result_url, output_path, job)
    if error:
        return error

    return {
        "success": True,
        "output": str(output_path),
        "job_id": job.get("id"),
        "model": model,
        "result_url": result_url,
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI video generation & smart upscaling via Higgsfield CLI (cloud, paid, cost-gated)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Cost estimate with Smart Upscale trick (480p + ByteDance Upscale)
  python tools/higgsfield_video.py --model seedance_2_5 --prompt "cinematic shot" --output clip.mp4 --smart-upscale

  # Smart Upscale is blocked until its complete cost can be verified.

  # Standalone ByteDance Upscaling of any video (local or cloud)
  python tools/higgsfield_video.py --model bytedance_video_upscale --video draft.mp4 --output crisp.mp4 --allow-upload --confirm --max-credits 10

  # Standard single-pass generation
  python tools/higgsfield_video.py --prompt "..." --output clip.mp4 --confirm --max-credits 10
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
    parser.add_argument(
        "--video", "-v", type=str,
        help="Input video file path (for bytedance_video_upscale or video-to-video)",
    )
    parser.add_argument("--duration", type=int, help="Clip duration in seconds (model-dependent)")
    parser.add_argument("--resolution", type=str, help="Target resolution, e.g. 1080p, 480p (model-dependent)")
    parser.add_argument(
        "--aspect-ratio", type=str, help="Aspect ratio, e.g. 16:9 (model-dependent)",
    )
    parser.add_argument(
        "--preset", type=str, default="aigc",
        help="Upscale preset (common, aigc, short_series, ugc, old_film). Default: aigc",
    )
    parser.add_argument(
        "--smart-upscale", action="store_true",
        help="Calvin Hollywood Trick: Render base at 480p, then upscale with ByteDance to 1080p (cost depends on provider pricing)",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually spend credits and create the job. Without this flag, only cost is shown.",
    )
    parser.add_argument(
        "--list-models", action="store_true", help="List available Higgsfield video models",
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    parser.add_argument("--smart-base-only", action="store_true", help="Create only the 480p base clip; the upscale remains a separately priced job")
    parser.add_argument("--allow-upload", action="store_true", help="Explicitly allow media upload to Higgsfield, including during cost estimation")
    parser.add_argument("--max-credits", type=float, help="Maximum authorized credit cost for this job")
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

    is_upscale_only = (args.model == "bytedance_video_upscale")

    if not is_upscale_only and not args.prompt:
        print("Error: --prompt required for generative models", file=sys.stderr)
        sys.exit(1)
    if is_upscale_only and not args.video:
        print("Error: --video required for bytedance_video_upscale", file=sys.stderr)
        sys.exit(1)
    if not args.output:
        print("Error: --output required", file=sys.stderr)
        sys.exit(1)

    if args.smart_base_only and (not args.smart_upscale or is_upscale_only):
        print("--smart-base-only benötigt --smart-upscale und ein Generierungsmodell.", file=sys.stderr)
        sys.exit(1)
    if args.confirm and Path(args.output).exists():
        print("Ausgabedatei existiert bereits; eine neue Ausgabedatei wählen.", file=sys.stderr)
        sys.exit(1)
    if (args.image or args.video) and not args.allow_upload:
        print("Medienübertragung auch bei Preisabfrage möglich; --allow-upload ist erforderlich.", file=sys.stderr)
        sys.exit(1)
    if any(media and Path(media).resolve() == Path(args.output).resolve() for media in (args.video, args.image)):
        print("Eingabe und Ausgabe müssen verschiedene Dateien sein.", file=sys.stderr)
        sys.exit(1)
    if args.confirm and args.smart_upscale and not args.smart_base_only:
        print("Kosten des Upscalings vor Generierung unbekannt; automatische Kette gesperrt.", file=sys.stderr)
        sys.exit(1)
    extra_params = {}
    if args.duration is not None:
        extra_params["duration"] = args.duration
    if args.aspect_ratio:
        extra_params["aspect-ratio"] = args.aspect_ratio

    # Handle resolution for smart-upscale vs standard
    target_upscale_res = args.resolution or "1080p"
    if args.smart_upscale:
        base_res = "480p"
        extra_params["resolution"] = base_res
    elif args.resolution:
        extra_params["resolution"] = args.resolution

    try:
        balance = get_balance()

        if is_upscale_only:
            print("Hinweis: Die Preisabfrage kann das Video zu Higgsfield hochladen.", file=sys.stderr)
            cost = estimate_cost("bytedance_video_upscale", video=args.video, extra_params={"resolution": target_upscale_res, "preset": args.preset})
            credits = cost.get("credits")
        elif args.smart_upscale:
            base_cost = estimate_cost(args.model, prompt=args.prompt, image=args.image, extra_params=extra_params)
            base_cr = base_cost.get("credits")
            # The provider needs the generated video to quote the second step.
            credits = base_cr if args.smart_base_only else None
        else:
            cost = estimate_cost(args.model, prompt=args.prompt, image=args.image, extra_params=extra_params)
            credits = cost.get("credits")
    except subprocess.TimeoutExpired:
        print("Kostenprüfung Zeitüberschreitung; kein Auftrag erstellt.", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, ValueError, OSError, AttributeError) as exc:
        print(f"Kostenprüfung fehlgeschlagen: {exc}; kein Auftrag erstellt.", file=sys.stderr)
        sys.exit(1)
    native_comparison = None

    def valid_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    if args.confirm and (not valid_number(credits) or not valid_number(balance.get("credits")) or not valid_number(args.max_credits) or credits > args.max_credits or balance["credits"] < credits):
        print("Kosten, Guthaben oder --max-credits unbekannt oder unzureichend; kein Auftrag erstellt.", file=sys.stderr)
        sys.exit(1)

    if not args.confirm:
        savings_pct = round((1 - credits / native_comparison) * 100) if (native_comparison and credits) else None
        result = {
            "confirmed": False,
            "model": args.model,
            "smart_upscale": args.smart_upscale,
            "smart_base_only": args.smart_base_only,
            "target_resolution": target_upscale_res if args.smart_upscale else args.resolution,
            "estimated_credits": None if args.smart_base_only else credits,
            "base_credits": base_cr if args.smart_upscale else None,
            "native_1080p_credits": native_comparison,
            "savings_percent": f"{savings_pct}%" if savings_pct else None,
            "account_balance": balance,
            "note": "No job created. Individual jobs require --confirm and --max-credits; smart upscale remains blocked.",
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== HIGGSFIELD KOSTENSCHÄTZUNG ===")
            print(f"  Modell:             {args.model}")
            if args.smart_upscale:
                print(f"  Modus:              Smart Upscale Trick (480p Basis + ByteDance Upscale auf {target_upscale_res})")
                print(f"  Basispreis: {base_cr if base_cr is not None else 'unbekannt'} Credits")
                print("  Upscale-Preis und Gesamtkosten: unbekannt")
                if native_comparison:
                    print(f"  Vergleich Nativ:    ~{native_comparison} Credits")
                    print(f"  Deine Ersparnis:    ~{savings_pct}% Rabatt!")
            else:
                print(f"  Gesamtkosten: {credits if credits is not None else 'unbekannt'} Credits")
            print(f"  Account-Guthaben:   {balance['raw']}")
            insufficient = (
                balance.get("credits") is not None
                and credits is not None
                and balance["credits"] < credits
            )
            if insufficient:
                print("  WARNUNG: Guthaben reicht möglicherweise nicht aus.")
            print("\nKein Job ausgeführt (0 Credits verbraucht). Für einen Einzelauftrag sind --confirm und --max-credits erforderlich.")
            print("==================================")
        return

    # Execute workflow
    if is_upscale_only:
        print(f"Confirmed — upscale video mit ByteDance ({target_upscale_res})...", file=sys.stderr)
        res = upscale_video(args.video, args.output, resolution=target_upscale_res, preset=args.preset)
        if not res.get("success"):
            print(f"Error: {res.get('error')}", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Saved: {res['output']}", file=sys.stderr)
        return

    # Standard direct generation
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
        if not result.get("success"):
            sys.exit(1)
    else:
        if result.get("success"):
            print(f"Saved: {result['output']}", file=sys.stderr)
            if args.smart_base_only:
                print("Basisclip erhalten. Upscaling separat mit --model bytedance_video_upscale --video <Basisclip> --output <Ziel> --allow-upload vorab prüfen; danach Preislimit und Freigabe setzen.", file=sys.stderr)
        else:
            print(f"Error: {result.get('error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
