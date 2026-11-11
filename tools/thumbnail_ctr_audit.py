#!/usr/bin/env python3
"""YouTube Thumbnail Mobile-CTR & Contrast Simulator.

Audits thumbnail viability on mobile devices (where 80%+ of YouTube clicks occur):
1. Mobile Feed Downscale Test (simulates 64px–128px smartphone view).
2. Grayscale Luminance Contrast Audit (tests dark/light separation).
3. Saliency & Edge Clarity Analysis (verifies text & subject pop).
4. Composite Diagnostic Sheet & 1-100 CTR Readability Score.

Usage:
    uv run tools/thumbnail_ctr_audit.py --image path/to/thumb.png
    uv run tools/thumbnail_ctr_audit.py --image path/to/thumb.png --output-dir ~/Hannibal/00_INBOX/Zu_Bearbeiten/Bilder/
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


def analyze_thumbnail(image_path: Path) -> dict[str, Any]:
    if not image_path.is_file():
        raise FileNotFoundError(f"Thumbnail nicht gefunden: {image_path}")

    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    aspect_ratio = round(width / max(1, height), 2)

    # Convert to grayscale for luminance analysis
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.float32)

    # 1. Luminance Contrast Metrics
    mean_lum = float(np.mean(arr))
    std_lum = float(np.std(arr))  # Standard deviation = contrast spread
    min_lum = float(np.min(arr))
    max_lum = float(np.max(arr))
    contrast_dynamic_range = max_lum - min_lum

    # Standard ideal std deviation for high-CTR thumbnails is >= 55.0
    contrast_score = min(100.0, max(0.0, (std_lum / 60.0) * 100.0))

    # 2. Edge & Saliency Analysis (Sobel-like gradient magnitude)
    gy, gx = np.gradient(arr)
    edge_magnitude = np.sqrt(gx**2 + gy**2)
    mean_edge = float(np.mean(edge_magnitude))
    # Strong clear text and silhouettes have higher edge energy
    clarity_score = min(100.0, max(0.0, (mean_edge / 18.0) * 100.0))

    # 3. Mobile Shrink Viability (downscale to 128px width, then compute loss)
    thumb_small = gray.resize((128, int(128 / (width / height))), Image.Resampling.LANCZOS)
    arr_small = np.array(thumb_small, dtype=np.float32)
    small_contrast = float(np.std(arr_small))
    mobile_retention_ratio = small_contrast / max(1.0, std_lum)
    mobile_score = min(100.0, max(0.0, mobile_retention_ratio * 100.0))

    # Composite Overall CTR Score
    composite_score = round(
        (contrast_score * 0.40) + (clarity_score * 0.35) + (mobile_score * 0.25), 1
    )

    # Recommendations
    recommendations: list[str] = []
    if std_lum < 45:
        recommendations.append(
            "Kontrast zu flach: Erhöhe die Helligkeit des Hauptmotivs oder dunkle den Hintergrund ab."
        )
    if mean_edge < 12:
        recommendations.append(
            "Schärfe & Textabgrenzung ungenügend: Verstärke Textkonturen (Drop-Shadow / Outline)."
        )
    if mobile_score < 75:
        recommendations.append(
            "Mobile-Verlust: Das Motiv verliert auf kleinen Handydisplays zu viele Details. Reduziere Kleinteiliges."
        )
    if aspect_ratio != 1.78 and aspect_ratio != 0.56:
        recommendations.append(
            f"Ungewöhnliches Seitenverhältnis ({aspect_ratio}): 16:9 (1.78) für YouTube oder 9:16 (0.56) für Shorts empfohlen."
        )

    if not recommendations:
        recommendations.append("Hervorragende Mobile-Präsenz: Kontrast und Schärfe sind im Top-Performer-Bereich.")

    verdict = "EXCELLENT" if composite_score >= 80 else ("GOOD" if composite_score >= 65 else "NEEDS_IMPROVEMENT")

    return {
        "image": str(image_path.resolve()),
        "dimensions": f"{width}x{height}",
        "aspect_ratio": aspect_ratio,
        "composite_score": composite_score,
        "verdict": verdict,
        "metrics": {
            "luminance_mean": round(mean_lum, 1),
            "luminance_contrast_std": round(std_lum, 1),
            "dynamic_range": round(contrast_dynamic_range, 1),
            "edge_clarity": round(mean_edge, 1),
            "mobile_retention_score": round(mobile_score, 1),
        },
        "recommendations": recommendations,
    }


def generate_diagnostic_sheet(image_path: Path, output_path: Path) -> Path:
    """Generates a 3-panel visual audit sheet for quick creator review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(image_path).convert("RGB")
    width, height = img.size

    # Standardize to 1280x720 for audit sheet
    orig = img.resize((1280, 720), Image.Resampling.LANCZOS)
    gray = orig.convert("L").convert("RGB")

    # Mobile preview (simulated 160x90 smartphone feed card)
    mobile_thumb = orig.resize((160, 90), Image.Resampling.LANCZOS).resize(
        (320, 180), Image.Resampling.NEAREST
    )

    sheet = Image.new("RGB", (1280, 1080), "#0A0D14")
    draw = ImageDraw.Draw(sheet)

    # Header
    draw.rectangle([0, 0, 1280, 80], fill="#111827")
    draw.text((40, 26), "YOUTUBE THUMBNAIL MOBILE-CTR AUDIT", fill="#D4AF37")

    # Panel 1: Original Thumbnail
    sheet.paste(orig.resize((580, 326)), (40, 120))
    draw.text((40, 460), "1. ORIGINAL (DESKTOP ANSICHT)", fill="#CBD5E1")

    # Panel 2: Grayscale Contrast Map
    sheet.paste(gray.resize((580, 326)), (660, 120))
    draw.text((660, 460), "2. KONTRAST-TRENNUNG (GRAUSTUFEN)", fill="#CBD5E1")

    # Panel 3: Mobile Feed Simulation Card
    sheet.paste(mobile_thumb, (40, 520))
    draw.text((40, 720), "3. SMARTPHONE FEED SIMULATION (64px EFFECTIVE)", fill="#CBD5E1")

    # Panel 4: Metrics Card
    audit = analyze_thumbnail(image_path)
    score = audit["composite_score"]
    score_color = "#34D399" if score >= 80 else ("#FBBF24" if score >= 65 else "#F87171")

    draw.rectangle([660, 520, 1240, 750], fill="#1E293B", outline="#D4AF37", width=1)
    draw.text((690, 540), f"CTR READABILITY SCORE: {score}/100", fill=score_color)
    draw.text((690, 580), f"Verdict: {audit['verdict']}", fill="#FFFFFF")
    draw.text((690, 620), f"Luminance Std: {audit['metrics']['luminance_contrast_std']}", fill="#94A3B8")
    draw.text((690, 650), f"Edge Saliency: {audit['metrics']['edge_clarity']}", fill="#94A3B8")
    draw.text((690, 680), f"Empfehlung: {audit['recommendations'][0][:55]}...", fill="#F3E5AB")

    sheet.save(output_path, quality=95)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube Thumbnail Mobile-CTR Simulator")
    parser.add_argument("--image", "-i", type=Path, required=True, help="Input thumbnail file.")
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("~/Hannibal/00_INBOX/Zu_Bearbeiten/Bilder").expanduser())
    parser.add_argument("--sheet", action="store_true", default=True, help="Generate visual diagnostic sheet.")
    parser.add_argument("--json", action="store_true", help="Print json output only.")
    args = parser.parse_args()

    try:
        report = analyze_thumbnail(args.image)
        if args.sheet:
            sheet_out = args.output_dir / f"audit_{args.image.stem}.jpg"
            generate_diagnostic_sheet(args.image, sheet_out)
            report["diagnostic_sheet"] = str(sheet_out)

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("=" * 60)
            print(" YOUTUBE THUMBNAIL MOBILE-CTR AUDIT")
            print("=" * 60)
            print(f"Datei:         {report['image']}")
            print(f"Dimensionen:   {report['dimensions']} ({report['aspect_ratio']})")
            print(f"CTR-Score:     {report['composite_score']} / 100 ({report['verdict']})")
            print("-" * 60)
            print("Metriken:")
            for k, v in report["metrics"].items():
                print(f"  - {k}: {v}")
            print("-" * 60)
            print("Empfehlungen:")
            for r in report["recommendations"]:
                print(f"  * {r}")
            if "diagnostic_sheet" in report:
                print(f"\n[+] Diagnostic Sheet gerendert: {report['diagnostic_sheet']}")
        return 0
    except Exception as err:
        print(f"Thumbnail CTR Audit: ERROR — {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
