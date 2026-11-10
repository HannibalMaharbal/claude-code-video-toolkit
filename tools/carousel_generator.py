#!/usr/bin/env python3
"""B2B LinkedIn & Instagram Multi-Page PDF & Image Carousel Generator.

Converts structured JSON content into a multi-slide 4:5 (1080x1350)
document carousel with Licbarska Dark-Luxury branding:
1. High-res PNG slides for Instagram multi-image carousel.
2. Multi-page PDF for LinkedIn document posts (which LinkedIn renders as interactive sliders).
3. 100% local rendering via Pillow (0 € cost).

Usage:
    uv run tools/carousel_generator.py --input templates/b2b-reel-remotion/sample-data.json
    uv run tools/carousel_generator.py --input templates/b2b-reel-remotion/sample-data.json --output ~/Hannibal/03_Export/Licbarska_Carousel.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

EXPORT_DIR = Path(os.path.expanduser("~/Hannibal/03_Export"))

WIDTH = 1080
HEIGHT = 1350  # 4:5 aspect ratio (optimal for LinkedIn & Instagram)

# Brand Color Palette
BG_COLOR = "#07090E"
CARD_BG = "#0F172A"
BORDER_GOLD = "#D4AF37"
TEXT_WHITE = "#FFFFFF"
TEXT_MUTED = "#94A3B8"
ACCENT_GOLD = "#D4AF37"
ACCENT_RED = "#F87171"
PILL_BG = "rgba(212, 175, 55, 0.15)"


def create_base_slide(slide_num: int, total_slides: int, brand_name: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Ambient top glow
    for r in range(300, 0, -20):
        alpha = int((300 - r) * 0.08)
        color = (212, 175, 55, alpha)
        draw.ellipse([540 - r, -100 - r, 540 + r, -100 + r], fill=color)

    # Subtle grid lines
    for x in range(0, WIDTH, 90):
        draw.line([(x, 0), (x, HEIGHT)], fill="#0D1322", width=1)
    for y in range(0, HEIGHT, 90):
        draw.line([(0, y), (WIDTH, y)], fill="#0D1322", width=1)

    # Header Bar
    draw.text((60, 50), brand_name.upper(), fill=ACCENT_GOLD)
    draw.text((WIDTH - 160, 50), f"{slide_num:02d} / {total_slides:02d}", fill=TEXT_MUTED)
    draw.line([(60, 90), (WIDTH - 60, 90)], fill="#1E293B", width=2)

    # Footer Swipe Indicator
    if slide_num < total_slides:
        draw.text((WIDTH - 200, HEIGHT - 70), "Swipe ➔", fill=ACCENT_GOLD)
    else:
        draw.text((WIDTH - 240, HEIGHT - 70), "Bookmark 🔖", fill=ACCENT_GOLD)

    draw.text((60, HEIGHT - 70), "LICBARSKA CONSULT", fill=TEXT_MUTED)
    draw.line([(60, HEIGHT - 100), (WIDTH - 60, HEIGHT - 100)], fill="#1E293B", width=2)

    return img, draw


def render_cover_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    img, draw = create_base_slide(1, total_slides, data.get("brandName", "LICBARSKA"))

    # Badge Pill
    draw.rounded_rectangle([60, 240, 360, 300], radius=30, fill="#1E293B", outline=BORDER_GOLD, width=1)
    draw.text((90, 260), data.get("badgeText", "B2B ANALYSE"), fill=ACCENT_GOLD)

    # Main Headline (Wrap into multiple lines)
    headline = data.get("hookHeadline", "3 KARDINALFEHLER").upper()
    words = headline.split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        if len(" ".join(curr)) > 22:
            lines.append(" ".join(curr[:-1]))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    y = 350
    for line in lines:
        draw.text((60, y), line, fill=TEXT_WHITE)
        y += 75

    # Subline
    subline = data.get("hookSubline", "")
    draw.text((60, y + 40), subline[:140], fill=TEXT_MUTED)

    # Bottom Highlight Card
    draw.rounded_rectangle([60, y + 160, WIDTH - 60, y + 360], radius=24, fill=CARD_BG, outline="#334155", width=1)
    draw.text((100, y + 195), "KEY TAKEAWAY", fill=ACCENT_GOLD)
    draw.text((100, y + 245), "In diesem Leitfaden: Konkrete Hebel für Eigentümer.", fill=TEXT_WHITE)
    draw.text((100, y + 295), "Erprobt in 140+ DACH-Transaktionen.", fill=TEXT_MUTED)

    return img


def render_stat_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    img, draw = create_base_slide(2, total_slides, data.get("brandName", "LICBARSKA"))
    stat = data.get("statHighlight", {})

    draw.text((60, 200), "STATUS QUO AM MARKT", fill=ACCENT_GOLD)

    # Big Card
    draw.rounded_rectangle([60, 280, WIDTH - 60, 850], radius=28, fill=CARD_BG, outline=BORDER_GOLD, width=2)

    # Huge Stat
    val = stat.get("value", "-22%")
    draw.text((120, 360), val, fill=ACCENT_RED)

    lbl = stat.get("label", "Wertverlust durch Fehlvermarktung")
    draw.text((120, 520), lbl, fill=TEXT_WHITE)

    sub = stat.get("subtitle", "Basierend auf DACH-Transaktionsdaten")
    draw.text((120, 600), sub, fill=TEXT_MUTED)

    draw.line([(120, 680), (WIDTH - 120, 680)], fill="#334155", width=1)
    draw.text((120, 720), "Fazit: Wer ohne Vorbereitung anbietet, verliert Millionen.", fill="#F3E5AB")

    return img


def render_point_slide(idx: int, point: dict[str, Any], total_slides: int, brand_name: str) -> Image.Image:
    img, draw = create_base_slide(idx, total_slides, brand_name)

    draw.text((60, 200), f"SCHRITT {point.get('index', idx - 2)} VON 3", fill=ACCENT_GOLD)

    draw.rounded_rectangle([60, 280, WIDTH - 60, 850], radius=28, fill=CARD_BG, outline="#334155", width=2)

    # Number Badge
    draw.rounded_rectangle([100, 340, 200, 440], radius=20, fill="#1E293B", outline=BORDER_GOLD, width=2)
    draw.text((135, 365), str(point.get("index", 1)), fill=ACCENT_GOLD)

    title = point.get("title", "")
    draw.text((100, 500), title, fill=TEXT_WHITE)

    detail = point.get("detail", "")
    # Word wrap
    words = detail.split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        if len(" ".join(curr)) > 35:
            lines.append(" ".join(curr[:-1]))
            curr = [w]
    if curr:
        lines.append(" ".join(curr))

    y = 600
    for l in lines:
        draw.text((100, y), l, fill=TEXT_MUTED)
        y += 45

    return img


def render_cta_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    img, draw = create_base_slide(total_slides, total_slides, data.get("brandName", "LICBARSKA"))
    cta = data.get("cta", {})

    draw.rounded_rectangle([60, 260, WIDTH - 60, 950], radius=32, fill=CARD_BG, outline=BORDER_GOLD, width=2)

    draw.text((100, 340), "NÄCHSTER SCHRITT", fill=ACCENT_GOLD)
    draw.text((100, 420), cta.get("headline", "OBJEKT PRÜFEN LASSEN"), fill=TEXT_WHITE)

    subline = cta.get("subline", "Kostenfreie Potenzial-Analyse für Eigentümer.")
    draw.text((100, 520), subline, fill=TEXT_MUTED)

    # CTA Button Box
    draw.rounded_rectangle([100, 660, WIDTH - 100, 780], radius=60, fill="#D4AF37")
    draw.text((220, 700), cta.get("badge", "Off-Market Dealflow").upper(), fill="#07090E")

    if cta.get("url"):
        draw.text((380, 840), cta["url"], fill=ACCENT_GOLD)

    return img


def generate_carousel(
    input_json: Path,
    output_pdf: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    data = json.loads(input_json.read_text(encoding="utf-8"))
    key_points = data.get("keyPoints", [])
    total_slides = 3 + len(key_points)  # Cover + Stat + Points + CTA

    slides: list[Image.Image] = []

    # Slide 1: Cover
    slides.append(render_cover_slide(data, total_slides))

    # Slide 2: Stat Card
    slides.append(render_stat_slide(data, total_slides))

    # Slides 3..N: Key Points
    for i, pt in enumerate(key_points):
        slides.append(render_point_slide(3 + i, pt, total_slides, data.get("brandName", "LICBARSKA")))

    # Final Slide: CTA
    slides.append(render_cta_slide(data, total_slides))

    target_dir = output_dir or EXPORT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Export PNGs
    png_paths: list[str] = []
    base_name = input_json.stem
    for idx, slide in enumerate(slides):
        p = target_dir / f"{base_name}_slide_{idx+1:02d}.png"
        slide.save(p, "PNG")
        png_paths.append(str(p))

    # Export Multi-page PDF for LinkedIn
    pdf_out = output_pdf or (target_dir / f"{base_name}_carousel.pdf")
    if slides:
        slides[0].save(
            pdf_out,
            "PDF",
            resolution=150.0,
            save_all=True,
            append_images=slides[1:],
        )

    return {
        "status": "success",
        "total_slides": len(slides),
        "pdf_path": str(pdf_out),
        "png_slides": png_paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LinkedIn & Instagram PDF Carousel Generator")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input content JSON file.")
    parser.add_argument("--output", "-o", type=Path, help="Output PDF file path.")
    parser.add_argument("--dir", "-d", type=Path, help="Directory for PNG slides and PDF.")
    args = parser.parse_args()

    try:
        res = generate_carousel(args.input, output_pdf=args.output, output_dir=args.dir)
        print("=" * 65)
        print(" B2B LINKEDIN & INSTAGRAM CAROUSEL GENERATOR")
        print("=" * 65)
        print(f"Erzeugte Slides: {res['total_slides']}")
        print(f"LinkedIn PDF:    {res['pdf_path']}")
        print(f"Instagram PNGs:  {len(res['png_slides'])} Folien")
        print("=" * 65)
        return 0
    except Exception as err:
        print(f"Carousel Generator: ERROR — {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
