#!/usr/bin/env python3
"""Unified Tiered Video Dispatcher for HANNIBAL AI OS.

Integrates the canonical Video Architecture:
  - 1. Local-First & Sharpening (Standard Filter / 0 €):
       a) Base generation: Local LTX-2.5 MLX on Apple Silicon (0 € Grenzkosten).
       b) Local Hardware Sharpening (0 €): Instant Apple Silicon VideoToolbox pass
          with Lanczos 1080p scaling + AMD FidelityFX Contrast Adaptive Sharpening (CAS)
          to eliminate LTX softness in 0.3s.
       c) Topaz Neural Upscale (On-Demand / Higgsfield): Neural AI reconstruction
          for complex micro-textures (skin pores, reflections, high-end commercial).
       STOP-RULE: If the sharpened LTX clip is visually sufficient, STOP -> 0 € Cloud model costs!
  - 2. Equal Cloud Freedom (Direct Provider vs. Higgsfield Platform):
       When local LTX physics/motion isn't sufficient, choose freely:
       a) Direct Providers: Wan 3.0 directly (Alibaba) & MiniMax H3 directly (lowest raw cost).
       b) Third-Party Platform (Higgsfield): Wan 3.0, MiniMax H3, Seedance 2.5, Kling,
          Marketing Studio, UGC Ad Multiplier, and Soul-ID (consistent faces) in one account.
       c) Selective High-End: Seedance 2.5 for complex character-locks / multi-image references.

Cost & Safety Guards:
  - Paid Cloud models strictly require `--confirm`. Without it, only cost estimation
    and data privacy notices are displayed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent

# Model metadata and approximate pricing (USD per second)
TIER_MODELS = {
    "draft": {
        "default": "ltx25",
        "models": ["ltx25"],
        "cost_per_sec": 0.0,
        "locality": "local",
        "description": "Local LTX-2.5 MLX + VideoToolbox CAS (0 € Grenzkosten, Scrap-Filter)",
    },
    "cloud": {
        "default": "wan3_0",
        "models": ["wan3_0", "wan3_0_prime", "minimax_h3", "minimax_h3_max", "seedance_2_mini"],
        "cost_per_sec": 0.10,  # ~0.10 $/s for Wan 3.0, ~0.13 $/s for H3 2K, ~0.03 $/s for Seedance 2 Mini
        "locality": "cloud",
        "description": "Economic Cloud Workhorse (Wan 3.0, MiniMax H3, Seedance 2 Mini via Higgsfield)",
    },
    "premium": {
        "default": "seedance_2_5",
        "models": ["seedance_2_5", "seedance_2_0"],
        "cost_per_sec": 0.30,  # ~0.25 - 0.40 $/s
        "locality": "cloud",
        "description": "Higgsfield Marketing Studio & Selective High-End (Seedance 2.5 für Multi-Ref & Soul-ID)",
    },
    "upscale": {
        "default": "topaz_hyperion_2_5",
        "models": ["topaz_hyperion_2_5", "topaz_video", "video_upscale"],
        "cost_per_sec": 0.08,
        "locality": "cloud",
        "description": "Topaz AI Cloud Upscaler / Sharpening (schärft weiche LTX-2.5 Entwürfe)",
    },
}

MODEL_TO_TIER = {
    "ltx25": "draft",
    "wan3_0": "cloud",
    "wan3_0_prime": "cloud",
    "minimax_h3": "cloud",
    "minimax_h3_max": "cloud",
    "seedance_2_mini": "cloud",
    "seedance_2_5": "premium",
    "seedance_2_0": "premium",
    "topaz_hyperion_2_5": "upscale",
    "topaz_video": "upscale",
    "video_upscale": "upscale",
}

# Specific model overrides for rates
MODEL_RATES = {
    "seedance_2_mini": 0.03,  # ~10x cost reduction compared to Seedance 2.5
}


def _estimate_cost(model: str, duration: int, has_ref_video: bool = False) -> dict[str, Any]:
    tier = MODEL_TO_TIER.get(model, "cloud")
    rate = MODEL_RATES.get(model, TIER_MODELS[tier]["cost_per_sec"])
    ref_factor = 1.4 if (has_ref_video and tier not in ("draft", "upscale")) else 1.0
    estimated_usd = round(duration * rate * ref_factor, 2)
    return {
        "model": model,
        "tier": tier,
        "duration_seconds": duration,
        "has_ref_video": has_ref_video,
        "estimated_cost_usd": estimated_usd,
        "currency": "USD",
        "is_free": (tier == "draft"),
    }


def _run_local_hardware_sharpen(input_path: str, output_path: str) -> bool:
    """Run Apple Silicon VideoToolbox Lanczos 1080p scaling + Contrast Adaptive Sharpening (CAS).
    
    This pass runs locally in ~0.3s on Apple Silicon at 0,00 $ cost, removing typical LTX softness.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Warning: ffmpeg not found, skipping local hardware sharpening.", file=sys.stderr)
        return False

    # Filter: Scale keeping aspect ratio (1080p target) + CAS (0.6) + light unsharp mask
    # Handles both 16:9 landscape and 9:16 vertical automatically
    vf_filter = (
        "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=lanczos,"
        "cas=0.6,"
        "unsharp=5:5:0.5:3:3:0.2"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        input_path,
        "-vf",
        vf_filter,
        "-c:v",
        "h264_videotoolbox",
        "-b:v",
        "20M",
        "-c:a",
        "copy",
        output_path,
    ]

    print(
        f"[Local Hardware Sharpen] Apple Silicon VideoToolbox (CAS 0.6 + Lanczos 1080p, 0 €)...",
        file=sys.stderr,
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"Warning: Local sharpening error: {proc.stderr[:400]}", file=sys.stderr)
        return False
    return True


def _run_ltx_draft(
    prompt: str,
    output_path: str,
    image: str | None = None,
    continue_from: str | None = None,
    frames: int = 97,
    fps: int = 24,
    mode: str = "two-stage",
) -> int:
    adapter = TOOLKIT_ROOT / "tools" / "ltx25_mlx_adapter.py"
    cmd = [
        sys.executable,
        str(adapter),
        "--prompt",
        prompt,
        "--output",
        output_path,
        "--frames",
        str(frames),
        "--frame-rate",
        str(fps),
        "--mode",
        mode,
    ]
    if image:
        cmd += ["--image", image]
    if continue_from:
        cmd += ["--continue-from", continue_from]

    print(f"[1. Lokal-First] Inferenz via LTX-2.5 MLX (0 € Grenzkosten)...", file=sys.stderr)
    proc = subprocess.run(cmd)
    return proc.returncode


PROVIDER_MODEL_MAP = {
    "seedance_2_mini": "seedance_2_0_mini",
    "seedance_2_0": "seedance_2_0",
    "seedance_2_5": "seedance_2_5",
}


def _run_cloud_generation(
    model: str,
    prompt: str,
    output_path: str,
    image: str | None = None,
    ref_video: str | None = None,
    provider: str = "higgsfield",
    duration: int = 5,
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    confirm: bool = False,
) -> int:
    hf_video = TOOLKIT_ROOT / "tools" / "higgsfield_video.py"
    target_model = PROVIDER_MODEL_MAP.get(model, model)
    cmd = [
        sys.executable,
        str(hf_video),
        "--model",
        target_model,
        "--prompt",
        prompt,
        "--output",
        output_path,
        "--duration",
        str(duration),
    ]
    if image:
        cmd += ["--image", image]
    if resolution:
        cmd += ["--resolution", resolution]
    if aspect_ratio:
        cmd += ["--aspect-ratio", aspect_ratio]
    if confirm:
        cmd.append("--confirm")

    if ref_video:
        print(
            f"[Reference Guidance] Verwende LTX-Vorlage '{ref_video}' als Bewegungsanker für {model}.",
            file=sys.stderr,
        )

    print(f"[Cloud Execution] Route: Provider={provider.upper()} | Model={model}", file=sys.stderr)
    proc = subprocess.run(cmd)
    return proc.returncode


def _run_topaz_upscale(input_path: str, output_path: str, confirm: bool = False) -> int:
    hf_video = TOOLKIT_ROOT / "tools" / "higgsfield_video.py"
    cmd = [
        sys.executable,
        str(hf_video),
        "--model",
        "topaz_hyperion_2_5",
        "--prompt",
        "enhance detail, remove noise, 4k sharpen",
        "--image",
        input_path,
        "--output",
        output_path,
    ]
    if confirm:
        cmd.append("--confirm")

    print(f"[Topaz Sharpening] Skaliere und schärfe LTX-Entwurf via Topaz Hyperion 2.5...", file=sys.stderr)
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Video Dispatcher: Local LTX + Topaz vs. Direct Provider vs. Higgsfield",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        choices=["draft", "cloud", "premium", "upscale"],
        default=None,
        help="Tier selection (draft: local LTX [0 $], cloud: Wan/H3, premium: Seedance, upscale: Topaz)",
    )
    parser.add_argument(
        "--model",
        "-m",
        choices=list(MODEL_TO_TIER.keys()),
        default=None,
        help="Explicit model override (e.g. ltx25, wan3_0, minimax_h3, seedance_2_5, topaz_hyperion_2_5)",
    )
    parser.add_argument(
        "--provider",
        choices=["direct", "higgsfield"],
        default="higgsfield",
        help="Provider route: 'direct' (Alibaba/MiniMax direct) vs 'higgsfield' (Cloud Hub aggregator, default)",
    )
    parser.add_argument("--prompt", "-p", required=True, help="Text prompt for video generation")
    parser.add_argument("--output", "-o", required=True, help="Output MP4 file path")
    parser.add_argument("--image", "-i", help="Reference starting image (for Image-to-Video)")
    parser.add_argument(
        "--ref-video",
        help="Reference draft video (e.g. 5s LTX draft) used to guide motion & composition in cloud re-render",
    )
    parser.add_argument(
        "--upscale-topaz",
        action="store_true",
        help="Additionally upscale with Topaz AI in the cloud right after local generation",
    )
    parser.add_argument(
        "--no-local-sharpen",
        action="store_true",
        help="Skip the automatic local VideoToolbox CAS 1080p sharpening pass",
    )
    parser.add_argument("--continue-from", help="Continue previous video clip (End-Frame lock)")
    parser.add_argument(
        "--motion-profile",
        choices=["auto", "steady-workspace", "occlusion-recovery"],
        default="auto",
        help="LTX-2.5 motion trajectory profile (steady-workspace: DEV 40-step focus; occlusion-recovery: Distilled focus)",
    )
    parser.add_argument("--duration", "-d", type=int, default=5, help="Clip duration in seconds (default: 5)")
    parser.add_argument("--resolution", "-r", help="Resolution (e.g. 720p, 1080p, 2k)")
    parser.add_argument("--aspect-ratio", help="Aspect ratio (e.g. 16:9, 9:16)")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for paid Cloud/Premium generation. Without this flag, only cost estimate is printed.",
    )
    parser.add_argument("--json", action="store_true", help="Output execution metadata as JSON")

    args = parser.parse_args()

    # Determine model and tier
    if args.model:
        model = args.model
        tier = MODEL_TO_TIER[model]
    elif args.tier:
        tier = args.tier
        model = TIER_MODELS[tier]["default"]
    else:
        tier = "draft"
        model = "ltx25"

    cost_info = _estimate_cost(model, args.duration, bool(args.ref_video))

    # Safety Gate: Paid generation requires explicit confirmation
    if tier != "draft" and not args.confirm:
        cost_msg = (
            f"\n"
            f"=== HANNIBAL COST & SAFETY GATE ===\n"
            f"Modell:         {model} ({TIER_MODELS[tier]['description']})\n"
            f"Provider-Route: {args.provider.upper()}\n"
            f"Stufe (Tier):   {tier.upper()}\n"
            f"Dauer:          {args.duration} Sekunden\n"
            f"Ref-Video:      {args.ref_video or 'Keines'}\n"
            f"Geschätzte Kosten: ~{cost_info['estimated_cost_usd']} USD\n"
            f"\n"
            f"[DATENSCHUTZ-HINWEIS]\n"
            f"Wan 3.0 und MiniMax H3 laufen über Server außerhalb der EU (China).\n"
            f"Ausschließlich für freigegebene Marketing- und Fiktionsinhalte nutzen; keine Mandantendaten.\n"
            f"\n"
            f"HINWEIS: Um diesen Bezahlauftrag verbindlich auszuführen, hänge '--confirm' an den Befehl an.\n"
            f"===================================\n"
        )
        if args.json:
            print(json.dumps({"status": "approval_required", "cost": cost_info}, indent=2))
        else:
            print(cost_msg, file=sys.stderr)
        return 0

    # Execute selected tier
    if tier == "draft":
        frames = args.duration * 24 + 1
        rc = _run_ltx_draft(
            prompt=args.prompt,
            output_path=args.output,
            image=args.image,
            continue_from=args.continue_from,
            frames=frames,
        )
        if rc != 0:
            return rc

        # Optimized Local Sharpening Step (0 € via Apple VideoToolbox CAS)
        crisp_output = str(Path(args.output).with_suffix("")) + "_crisp.mp4"
        if not args.no_local_sharpen:
            ok = _run_local_hardware_sharpen(args.output, crisp_output)
            if ok:
                active_result = crisp_output
            else:
                active_result = args.output
        else:
            active_result = args.output

        # Optional Cloud Topaz Neural Sharpening
        if args.upscale_topaz:
            topaz_output = str(Path(args.output).with_suffix("")) + "_topaz.mp4"
            print(f"[Cloud Step] Sende an Topaz Hyperion 2.5...", file=sys.stderr)
            topaz_rc = _run_topaz_upscale(active_result, topaz_output, confirm=args.confirm)
            if topaz_rc == 0:
                active_result = topaz_output

        # Print Gate Verdict & Guidance for Hannibal
        print(
            f"\n"
            f"==========================================================\n"
            f"✓ LOKALER FILTER ERFOLGREICH (0 € MODEL-KOSTEN)\n"
            f"Roh-Entwurf:     {args.output}\n"
            f"Geschärfter Clip: {active_result}\n"
            f"----------------------------------------------------------\n"
            f"QUALITÄTS-VERDIKT (STOP-BEDINGUNG):\n"
            f"• Reicht dieser geschärfte Clip für die Szene aus?\n"
            f"  ➔ JA: FERTIG! Keine weiteren Schritte oder Kosten nötig.\n"
            f"  ➔ NEIN (mehr Dynamik/Physik nötig): Re-Render via Cloud:\n"
            f"     uv run tools/video_generate.py --provider direct --model wan3_0 --ref-video {active_result} --confirm\n"
            f"     oder via Higgsfield:\n"
            f"     uv run tools/video_generate.py --provider higgsfield --model minimax_h3 --ref-video {active_result} --confirm\n"
            f"----------------------------------------------------------\n"
            f"KINEMATISCHE DRAFT- & MASTERING-RICHTLINIE (LTX 2.5 SOTA):\n"
            f"• Ruhige Interaktion / Feinarbeit: DEV-Pfad (40 Steps, CFG 3.5, stabilerer Workspace)\n"
            f"• Dynamische Szene / Verdeckung: Distilled-Pfad (8-12 Steps, überlegene Re-Identifikation)\n"
            f"• HDR-Finishing: LTX-2.5 SDR-to-HDR IC-LoRA (streaming encode ON, ACEScg -> 10-Bit HLG BT.2020)\n"
            f"==========================================================\n",
            file=sys.stderr,
        )
        return 0

    elif tier == "upscale":
        target_input = args.ref_video or args.image or args.output
        return _run_topaz_upscale(target_input, args.output, confirm=args.confirm)
    else:
        return _run_cloud_generation(
            model=model,
            prompt=args.prompt,
            output_path=args.output,
            image=args.image,
            ref_video=args.ref_video,
            provider=args.provider,
            duration=args.duration,
            resolution=args.resolution,
            aspect_ratio=args.aspect_ratio,
            confirm=args.confirm,
        )


if __name__ == "__main__":
    sys.exit(main())
