#!/usr/bin/env python3
"""Batch ad generator & multi-model orchestrator via Higgsfield CLI.

Inspired by Luca Delfino's Claude + Higgsfield workflow:
Generates multiple ad angles, estimates costs, enforces a strict budget ceiling,
downloads results locally, and persists a reproducible manifest.json + summary.md.

Usage:
    # 1. Dry Run / Cost Estimate (0 € charged):
    uv run tools/higgsfield_batch_ads.py \\
        --product "Licbarska Consult: B2B Finanzierungs- & Transaktionsberatung" \\
        --campaign "licbarska_b2b_ad_sprint" \\
        --models seedance_2_0_mini \\
        --num-ads 3 \\
        --max-credits 15

    # 2. Production Run (Requires explicit --confirm):
    uv run tools/higgsfield_batch_ads.py \\
        --product "Licbarska Consult" \\
        --campaign "licbarska_b2b_ad_sprint" \\
        --confirm --max-credits 15
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import higgsfield_video

EXPORT_ROOT = Path(os.path.expanduser("~/Hannibal/03_Export/higgsfield"))

DEFAULT_ANGLES = [
    {
        "hook": "Problem-Awareness",
        "prompt_template": "Cinematic high-angle shot, modern glass office in Frankfurt, institutional investor reviewing declining portfolio returns, moody corporate lighting, 8k resolution.",
    },
    {
        "hook": "Data & Insight",
        "prompt_template": "Macro financial data visualization floating over architectural blueprint, gold glowing growth vectors, photorealistic luxury aesthetic, smooth camera push-in.",
    },
    {
        "hook": "Solution & Authority",
        "prompt_template": "Confident senior deal strategist shaking hands in sunlit penthouse boardroom, skyline backdrop, cinematic lens flare, professional B2B atmosphere.",
    },
    {
        "hook": "Urgency / Market Shift",
        "prompt_template": "Fast dynamic camera glide through modern financial district at twilight, illuminated skyscrapers, sleek typography floating, premium documentary feel.",
    },
    {
        "hook": "Trust & Execution",
        "prompt_template": "Close-up of fountain pen signing high-stakes transaction agreement, textured luxury paper, shallow depth of field, warm golden hour light.",
    },
]


@dataclass
class AdItem:
    index: int
    hook: str
    model: str
    prompt: str
    estimated_credits: float
    output_filename: str
    status: str = "pending"
    job_id: str | None = None
    local_path: str | None = None


def generate_ad_plan(
    product: str,
    num_ads: int,
    models: list[str],
) -> list[AdItem]:
    items: list[AdItem] = []
    for i in range(num_ads):
        angle = DEFAULT_ANGLES[i % len(DEFAULT_ANGLES)]
        chosen_model = models[i % len(models)]
        composed_prompt = f"{angle['prompt_template']} Context: {product}."
        items.append(
            AdItem(
                index=i + 1,
                hook=angle["hook"],
                model=chosen_model,
                prompt=composed_prompt,
                estimated_credits=3.0,  # Standard baseline estimate for seedance_2_0_mini
                output_filename=f"ad_{i+1:02d}_{chosen_model}_{angle['hook'].lower().replace('/', '_')}.mp4",
            )
        )
    return items


def run_batch(
    product: str,
    campaign: str,
    num_ads: int,
    models: list[str],
    max_credits: float,
    confirm: bool = False,
) -> dict[str, Any]:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    campaign_dir = EXPORT_ROOT / f"{campaign}_{timestamp}"
    plan = generate_ad_plan(product, num_ads, models)

    # Cost gating check
    total_estimated = sum(item.estimated_credits for item in plan)
    if total_estimated > max_credits:
        raise RuntimeError(
            f"Budget Gate Blocked: Geschätzte Kosten ({total_estimated} Credits) übersteigen "
            f"das autorisierte Limit (--max-credits {max_credits})."
        )

    result_summary: dict[str, Any] = {
        "campaign": campaign,
        "product": product,
        "timestamp": timestamp,
        "num_ads": num_ads,
        "models": models,
        "total_estimated_credits": total_estimated,
        "max_credits_authorized": max_credits,
        "confirm_flag_set": confirm,
        "target_directory": str(campaign_dir),
        "items": [asdict(item) for item in plan],
    }

    if not confirm:
        print("=" * 70)
        print(" [DRY-RUN / KOSTENSCHÄTZUNG] Kein Job gestartet, 0 € berechnet.")
        print("=" * 70)
        print(f"Kampagne:              {campaign}")
        print(f"Produkt:                {product}")
        print(f"Geplante Ads:           {num_ads}")
        print(f"Eingesetzte Modelle:    {', '.join(models)}")
        print(f"Geschätzte Credits:     {total_estimated} (Limit: {max_credits})")
        print(f"Zielverzeichnis:        {campaign_dir}")
        print("-" * 70)
        for it in plan:
            print(f"  #{it.index:02d} [{it.model}] {it.hook}:")
            print(f"       Prompt: {it.prompt[:75]}...")
        print("-" * 70)
        print("Um die Ads tatsächlich zu generieren, führe den Befehl mit '--confirm' aus.")
        return result_summary

    # Production run
    campaign_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] Starte Kampagnen-Generierung in: {campaign_dir}")

    for it in plan:
        out_file = campaign_dir / it.output_filename
        print(f"[*] Generiere Ad #{it.index} ({it.hook}) mit {it.model}...")
        try:
            # Delegate to existing higgsfield_video wrapper
            job_res = higgsfield_video.generate_video(
                model=it.model,
                prompt=it.prompt,
                output_path=str(out_file),
                confirm=True,
                max_credits=it.estimated_credits * 1.5,
            )
            it.status = "completed"
            it.job_id = str(job_res.get("job_id") if isinstance(job_res, dict) else "ok")
            it.local_path = str(out_file)
        except Exception as exc:
            it.status = f"failed: {exc}"
            print(f"[!] Fehler bei Ad #{it.index}: {exc}", file=sys.stderr)

    # Persist manifest and report
    manifest_path = campaign_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report_path = campaign_dir / "summary.md"
    report_lines = [
        f"# Higgsfield Ad Campaign: {campaign}",
        f"- **Produkt:** {product}",
        f"- **Datum:** {timestamp}",
        f"- **Generierte Ads:** {num_ads}",
        f"- **Kosten:** ~{total_estimated} Credits",
        "",
        "## Generierte Video-Assets",
        "",
    ]
    for it in plan:
        report_lines.append(f"### Ad #{it.index}: {it.hook} ({it.model})")
        report_lines.append(f"- **Status:** {it.status}")
        report_lines.append(f"- **Datei:** `{it.output_filename}`")
        report_lines.append(f"- **Prompt:** *{it.prompt}*")
        report_lines.append("")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"[SUCCESS] Kampagne abgeschlossen. Manifest gespeichert unter: {manifest_path}")
    return result_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Higgsfield Multi-Ad Batch Generator with Budget Guard")
    parser.add_argument("--product", required=True, help="Product or service brief.")
    parser.add_argument("--campaign", default="b2b_ad_sprint", help="Campaign identifier.")
    parser.add_argument("--num-ads", type=int, default=3, help="Number of ad variations to create.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["seedance_2_0_mini"],
        help="List of Higgsfield models to cycle across.",
    )
    parser.add_argument(
        "--max-credits",
        type=float,
        default=15.0,
        help="Maximum authorized credit cost across all ads.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually execute and bill generation. Without this flag, only estimates are printed.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        run_batch(
            product=args.product,
            campaign=args.campaign,
            num_ads=args.num_ads,
            models=args.models,
            max_credits=args.max_credits,
            confirm=args.confirm,
        )
        return 0
    except Exception as err:
        print(f"Batch Ad Generator: ERROR — {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
