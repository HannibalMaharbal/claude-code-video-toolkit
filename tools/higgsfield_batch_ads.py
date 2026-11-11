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
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import higgsfield_video

EXPORT_ROOT = Path(os.path.expanduser("~/Hannibal/00_INBOX/Zu_Bearbeiten/Videos/higgsfield"))
CAMPAIGN_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

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
    estimated_credits: float | None
    output_filename: str
    status: str = "pending"
    job_id: str | None = None
    local_path: str | None = None
    error: str | None = None


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

        est_credits: float | None = None
        if hasattr(higgsfield_video, "estimate_cost"):
            try:
                cost_res = higgsfield_video.estimate_cost(chosen_model, prompt=composed_prompt)
                if isinstance(cost_res, dict):
                    c = cost_res.get("credits")
                    if isinstance(c, (int, float)) and math.isfinite(c) and c >= 0:
                        est_credits = float(c)
            except Exception:
                est_credits = None

        items.append(
            AdItem(
                index=i + 1,
                hook=angle["hook"],
                model=chosen_model,
                prompt=composed_prompt,
                estimated_credits=est_credits,
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
    if (
        not isinstance(max_credits, (int, float))
        or isinstance(max_credits, bool)
        or not math.isfinite(max_credits)
        or max_credits <= 0
    ):
        raise ValueError(
            f"Ungültiges Limit --max-credits: {max_credits!r}. Muss eine endliche Zahl > 0 sein."
        )

    if not isinstance(campaign, str) or not CAMPAIGN_NAME_RE.fullmatch(campaign):
        raise ValueError(
            f"Ungültiger Kampagnenname: {campaign!r}. Erlaubt sind nur [A-Za-z0-9_-] mit 1–64 Zeichen."
        )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_root = EXPORT_ROOT.resolve()
    campaign_dir = (EXPORT_ROOT / f"{campaign}_{timestamp}").resolve()
    if campaign_dir == target_root or target_root not in campaign_dir.parents:
        raise ValueError(
            f"Zielpfad {campaign_dir} bricht aus dem Export-Verzeichnis {target_root} aus."
        )
    plan = generate_ad_plan(product, num_ads, models)

    unknown_costs = any(
        item.estimated_credits is None
        or not isinstance(item.estimated_credits, (int, float))
        or isinstance(item.estimated_credits, bool)
        or not math.isfinite(item.estimated_credits)
        or item.estimated_credits < 0
        for item in plan
    )
    total_estimated = sum(
        item.estimated_credits
        for item in plan
        if isinstance(item.estimated_credits, (int, float))
        and not isinstance(item.estimated_credits, bool)
        and math.isfinite(item.estimated_credits)
        and item.estimated_credits >= 0
    )
    if not math.isfinite(total_estimated) or total_estimated < 0:
        unknown_costs = True

    # Fail-closed check: if prices cannot be determined, confirm is blocked
    if confirm and unknown_costs:
        raise RuntimeError(
            "Fail-closed: Mindestens ein Modellpreis ist unbekannt oder konnte nicht ermittelt werden. "
            "Ohne verifizierten Preis ist --confirm gesperrt."
        )

    # Cost gating check
    if not unknown_costs and total_estimated > max_credits:
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
        "total_estimated_credits": total_estimated if not unknown_costs else None,
        "max_credits_authorized": max_credits,
        "confirm_flag_set": confirm,
        "target_directory": str(campaign_dir),
        "items": [asdict(item) for item in plan],
        "failed_count": 0,
    }

    if not confirm:
        print("=" * 70)
        print(" [DRY-RUN / KOSTENSCHÄTZUNG] Kein Job gestartet, 0 € berechnet.")
        print("=" * 70)
        print(f"Kampagne:              {campaign}")
        print(f"Produkt:                {product}")
        print(f"Geplante Ads:           {num_ads}")
        print(f"Eingesetzte Modelle:    {', '.join(models)}")
        cost_str = f"{total_estimated}" if not unknown_costs else "unbekannt"
        print(f"Geschätzte Credits:     {cost_str} (Limit: {max_credits})")
        print(f"Zielverzeichnis:        {campaign_dir}")
        print("-" * 70)
        for it in plan:
            print(f"  #{it.index:02d} [{it.model}] {it.hook}:")
            print(f"       Prompt: {it.prompt[:75]}...")
        print("-" * 70)
        print("Um die Ads tatsächlich zu generieren, führe den Befehl mit '--confirm' aus.")
        return result_summary

    # Production run
    def _valid_number(val: Any) -> bool:
        return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and val >= 0

    try:
        balance_info = higgsfield_video.get_balance()
        balance_credits = balance_info.get("credits") if isinstance(balance_info, dict) else None
    except Exception as exc:
        raise RuntimeError(f"Guthabenprüfung fehlgeschlagen ({exc}); kein Auftrag gestartet.") from exc

    if not _valid_number(balance_credits) or not _valid_number(total_estimated) or balance_credits < total_estimated:
        raise RuntimeError(
            f"Kosten oder Guthaben unbekannt oder unzureichend: Benötigt {total_estimated} Credits, "
            f"verfügbares Guthaben: {balance_credits}; kein Auftrag gestartet."
        )

    campaign_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] Starte Kampagnen-Generierung in: {campaign_dir}")

    spent_credits = 0.0
    for idx, it in enumerate(plan):
        # Unmittelbar vor JEDEM create_video() erneut estimate_cost() aufrufen
        new_price: float | None = None
        try:
            latest_cost_info = higgsfield_video.estimate_cost(it.model, prompt=it.prompt)
            if isinstance(latest_cost_info, dict):
                c = latest_cost_info.get("credits")
                if isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) and c >= 0:
                    new_price = float(c)
        except Exception:
            new_price = None

        if new_price is None or (spent_credits + new_price > max_credits):
            abort_msg = (
                f"Budget überschritten oder Preis nicht finit: verbraucht={spent_credits}, "
                f"neuer_preis={new_price}, limit={max_credits}"
            )
            print(f"[!] {abort_msg}. Breche diesen und alle weiteren Aufträge ab.", file=sys.stderr)
            for rem in plan[idx:]:
                rem.status = "abgebrochen: Budget"
                rem.error = abort_msg
            break

        it.estimated_credits = new_price
        spent_credits += new_price

        out_file = campaign_dir / it.output_filename
        print(f"[*] Generiere Ad #{it.index} ({it.hook}) mit {it.model}...")
        try:
            # Delegate to existing higgsfield_video wrapper: create_video
            job_res = higgsfield_video.create_video(
                model=it.model,
                prompt=it.prompt,
                output_path=str(out_file),
            )
            if isinstance(job_res, dict) and job_res.get("success", False):
                it.status = "ok"
                it.job_id = str(job_res.get("job_id") if job_res.get("job_id") else "ok")
                it.local_path = str(out_file)
                it.error = None
            else:
                err_msg = job_res.get("error", "Unbekannter Fehler") if isinstance(job_res, dict) else str(job_res)
                it.status = "fehler"
                it.error = err_msg
                if isinstance(job_res, dict) and job_res.get("job") and isinstance(job_res["job"], dict):
                    it.job_id = str(job_res["job"].get("id"))
                elif isinstance(job_res, dict) and job_res.get("job_id"):
                    it.job_id = str(job_res.get("job_id"))
                print(f"[!] Fehler bei Ad #{it.index}: {err_msg}", file=sys.stderr)
        except Exception as exc:
            it.status = "fehler"
            it.error = str(exc)
            print(f"[!] Fehler bei Ad #{it.index}: {exc}", file=sys.stderr)

    # Persist updated manifest and report
    failed_count = sum(1 for it in plan if it.status != "ok")
    result_summary["failed_count"] = failed_count
    result_summary["items"] = [asdict(item) for item in plan]
    if any(it.status == "abgebrochen: Budget" for it in plan):
        result_summary["status"] = "abgebrochen: Budget"
    manifest_path = campaign_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    report_path = campaign_dir / "summary.md"
    report_lines = [
        f"# Higgsfield Ad Campaign: {campaign}",
        f"- **Produkt:** {product}",
        f"- **Datum:** {timestamp}",
        f"- **Generierte Ads:** {num_ads}",
        f"- **Fehlgeschlagene Ads:** {failed_count}",
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
    if failed_count > 0:
        print(
            f"[TEILWEISE FEHLGESCHLAGEN] {failed_count} von {num_ads} Ads fehlgeschlagen. "
            f"Manifest gespeichert unter: {manifest_path}"
        )
    else:
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
        summary = run_batch(
            product=args.product,
            campaign=args.campaign,
            num_ads=args.num_ads,
            models=args.models,
            max_credits=args.max_credits,
            confirm=args.confirm,
        )
        if summary.get("failed_count", 0) > 0:
            return 2
        return 0
    except Exception as err:
        print(f"Batch Ad Generator: ERROR — {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
