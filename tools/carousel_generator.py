#!/usr/bin/env python3
"""B2B LinkedIn & Instagram Multi-Page PDF & Image Carousel Generator.

Converts structured JSON content into a multi-slide 4:5 (1080x1350)
document carousel with Licbarska Dark-Luxury branding:
1. High-res PNG slides for Instagram multi-image carousel.
2. Multi-page PDF for LinkedIn document posts (which LinkedIn renders as interactive sliders).
3. 100% local rendering via Pillow (0 € cost).

Usage:
    uv run tools/carousel_generator.py --input templates/b2b-reel-remotion/sample-data.json
    uv run tools/carousel_generator.py --input templates/b2b-reel-remotion/sample-data.json --output ~/Hannibal/00_INBOX/Zu_Bearbeiten/Dokumente/Licbarska_Carousel.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

EXPORT_DIR = Path(os.path.expanduser("~/Hannibal/00_INBOX/Zu_Bearbeiten/Dokumente"))

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

SYSTEM_FONT_CANDIDATES = (
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
)

FONT_SIZE_STAT = 96
FONT_SIZE_TITLE = 72
FONT_SIZE_SUBLINE = 40
FONT_SIZE_BODY = 36
FONT_SIZE_LABEL = 28


def get_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load system font with fallback order: HelveticaNeue -> Helvetica -> SFNS -> default."""
    for font_path in SYSTEM_FONT_CANDIDATES:
        p = Path(font_path)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size=size, index=1 if bold and p.suffix == ".ttc" else 0)
            except Exception:
                try:
                    return ImageFont.truetype(str(p), size=size)
                except Exception:
                    pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def wrap_text(text: str, max_width: int, font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> list[str]:
    """Wrap text into multiple lines so that each line fits within max_width.

    Placeholders in brackets (e.g. '[XX %]') are treated as indivisible units
    (via non-breaking spaces) if they fit within max_width, preventing them
    from being split awkwardly across lines.
    """
    def _protect_brackets(m: re.Match[str]) -> str:
        s = m.group(0)
        bbox = font.getbbox(s)
        if (bbox[2] - bbox[0]) <= max_width:
            return s.replace(" ", "\u00a0")
        return s

    processed_text = re.sub(r"\[[^\]\n]+\]", _protect_brackets, text)
    words = [w for w in re.split(r"[ \t\n\r\f\v]+", processed_text) if w]
    if not words:
        return []
    lines: list[str] = []
    current_line: list[str] = []

    for word in words:
        test_line = " ".join([*current_line, word])
        bbox = font.getbbox(test_line)
        line_w = bbox[2] - bbox[0]
        if line_w <= max_width or not current_line:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line).replace("\u00a0", " "))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line).replace("\u00a0", " "))
    return lines


def fit_title_font(
    text: str,
    max_width: int,
    start_size: int = FONT_SIZE_TITLE,
    min_size: int = 44,
    bold: bool = True,
) -> tuple[ImageFont.ImageFont | ImageFont.FreeTypeFont, int]:
    """Shrink title font size step-by-step until each word fits within max_width."""
    size = start_size
    font = get_font(size, bold=bold)
    words = text.split()
    while size > min_size:
        if all((font.getbbox(w)[2] - font.getbbox(w)[0]) <= max_width for w in words):
            break
        size -= 2
        font = get_font(size, bold=bold)
    return font, size


def get_footer_action_text(
    slide_num: int,
    total_slides: int,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont | None = None,
) -> str:
    """Return clean ASCII/Latin-1 action indicator for carousel footer without missing glyphs."""
    if slide_num < total_slides:
        return "Weiter »"
    return "Speichern"


def create_base_slide(slide_num: int, total_slides: int, brand_name: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)

    # Ambient top glow: drawn on separate RGBA layer with GaussianBlur and low opacity (max ~22%)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(400, 0, -20):
        alpha = int((400 - r) / 400 * 55)
        color = (212, 175, 55, alpha)
        glow_draw.ellipse([540 - r, -100 - r, 540 + r, -100 + r], fill=color)

    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    base_rgba = img.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, glow)
    img = base_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Subtle grid lines (drawn after ambient glow composite)
    for x in range(0, WIDTH, 90):
        draw.line([(x, 0), (x, HEIGHT)], fill="#0D1322", width=1)
    for y in range(0, HEIGHT, 90):
        draw.line([(0, y), (WIDTH, y)], fill="#0D1322", width=1)

    font_label = get_font(FONT_SIZE_LABEL)

    # Header Bar
    draw.text((60, 50), brand_name.upper(), fill=ACCENT_GOLD, font=font_label)
    draw.text((WIDTH - 180, 50), f"{slide_num:02d} / {total_slides:02d}", fill=TEXT_MUTED, font=font_label)
    draw.line([(60, 90), (WIDTH - 60, 90)], fill="#1E293B", width=2)

    # Footer Action Indicator (clean glyphs, no missing emojis)
    footer_action = get_footer_action_text(slide_num, total_slides, font_label)
    bbox_action = font_label.getbbox(footer_action)
    action_w = bbox_action[2] - bbox_action[0]
    draw.text((WIDTH - 60 - action_w, HEIGHT - 70), footer_action, fill=ACCENT_GOLD, font=font_label)

    draw.text((60, HEIGHT - 70), brand_name.upper(), fill=TEXT_MUTED, font=font_label)
    draw.line([(60, HEIGHT - 100), (WIDTH - 60, HEIGHT - 100)], fill="#1E293B", width=2)

    return img, draw


def render_cover_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    brand = data.get("brandName", "LICBARSKA")
    img, draw = create_base_slide(1, total_slides, brand)

    font_label = get_font(FONT_SIZE_LABEL)
    font_subline = get_font(FONT_SIZE_SUBLINE)
    font_body = get_font(FONT_SIZE_BODY)

    # Badge Pill
    badge = data.get("badgeText")
    y_start = 240
    if badge:
        bbox = font_label.getbbox(badge)
        badge_w = bbox[2] - bbox[0] + 60
        draw.rounded_rectangle([60, y_start, 60 + badge_w, y_start + 60], radius=30, fill="#1E293B", outline=BORDER_GOLD, width=1)
        draw.text((90, y_start + 15), badge, fill=ACCENT_GOLD, font=font_label)
        y = y_start + 100
    else:
        y = y_start

    # Main Headline (Wrap into multiple lines with step-by-step font shrinking if word exceeds max_width)
    headline = data.get("hookHeadline", "").upper()
    if headline:
        font_title, title_size = fit_title_font(headline, max_width=WIDTH - 120)
        lines = wrap_text(headline, max_width=WIDTH - 120, font=font_title)
        for line in lines:
            draw.text((60, y), line, fill=TEXT_WHITE, font=font_title)
            y += int(title_size * 1.25)

    # Subline (wrapped instead of sliced)
    subline = data.get("hookSubline")
    if subline:
        y += 15
        lines = wrap_text(subline, max_width=WIDTH - 120, font=font_subline)
        for line in lines:
            draw.text((60, y), line, fill=TEXT_MUTED, font=font_subline)
            y += int(FONT_SIZE_SUBLINE * 1.3)

    # Optional Highlight Card: only render if keyTakeaway is provided in input data
    takeaway = data.get("keyTakeaway") or data.get("takeaway")
    if takeaway:
        card_y = max(y + 40, 720)
        lines = wrap_text(takeaway, max_width=WIDTH - 200, font=font_body)
        card_h = 90 + len(lines) * int(FONT_SIZE_BODY * 1.3)
        draw.rounded_rectangle([60, card_y, WIDTH - 60, card_y + card_h], radius=24, fill=CARD_BG, outline="#334155", width=1)
        draw.text((100, card_y + 25), "KEY TAKEAWAY", fill=ACCENT_GOLD, font=font_label)
        ty = card_y + 65
        for t_line in lines:
            draw.text((100, ty), t_line, fill=TEXT_WHITE, font=font_body)
            ty += int(FONT_SIZE_BODY * 1.3)

    return img


def render_stat_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    brand = data.get("brandName", "LICBARSKA")
    img, draw = create_base_slide(2, total_slides, brand)
    stat = data.get("statHighlight", {})

    font_label = get_font(FONT_SIZE_LABEL)
    font_stat = get_font(FONT_SIZE_STAT, bold=True)
    font_subline = get_font(FONT_SIZE_SUBLINE, bold=True)
    font_body = get_font(FONT_SIZE_BODY)

    draw.text((60, 200), "STATUS QUO AM MARKT", fill=ACCENT_GOLD, font=font_label)

    # Big Card
    draw.rounded_rectangle([60, 270, WIDTH - 60, 880], radius=28, fill=CARD_BG, outline=BORDER_GOLD, width=2)

    cur_y = 330
    # Stat value
    val = stat.get("value")
    if val:
        draw.text((120, cur_y), val, fill=ACCENT_RED, font=font_stat)
        cur_y += int(FONT_SIZE_STAT * 1.25)

    # Label
    lbl = stat.get("label")
    if lbl:
        lbl_lines = wrap_text(lbl, max_width=WIDTH - 240, font=font_subline)
        for l_line in lbl_lines:
            draw.text((120, cur_y), l_line, fill=TEXT_WHITE, font=font_subline)
            cur_y += int(FONT_SIZE_SUBLINE * 1.3)

    # Subtitle: only if provided in input data (NO hardcoded default!)
    sub = stat.get("subtitle")
    if sub:
        cur_y += 15
        sub_lines = wrap_text(sub, max_width=WIDTH - 240, font=font_body)
        for s_line in sub_lines:
            draw.text((120, cur_y), s_line, fill=TEXT_MUTED, font=font_body)
            cur_y += int(FONT_SIZE_BODY * 1.3)

    # Optional Conclusion / Note: only if provided in input data (NO hardcoded default!)
    conclusion = stat.get("conclusion") or stat.get("note") or stat.get("fazit")
    if conclusion:
        draw.line([(120, cur_y + 20), (WIDTH - 120, cur_y + 20)], fill="#334155", width=1)
        cur_y += 40
        conc_lines = wrap_text(conclusion, max_width=WIDTH - 240, font=font_body)
        for c_line in conc_lines:
            draw.text((120, cur_y), c_line, fill="#F3E5AB", font=font_body)
            cur_y += int(FONT_SIZE_BODY * 1.3)

    return img


def render_point_slide(idx: int, point: dict[str, Any], total_slides: int, brand_name: str) -> Image.Image:
    img, draw = create_base_slide(idx, total_slides, brand_name)

    font_label = get_font(FONT_SIZE_LABEL)
    font_subline = get_font(FONT_SIZE_SUBLINE, bold=True)
    font_body = get_font(FONT_SIZE_BODY)

    step_idx = point.get("index", idx - 2)
    total_steps = max(1, total_slides - 3)
    draw.text((60, 200), f"SCHRITT {step_idx} VON {total_steps}", fill=ACCENT_GOLD, font=font_label)

    draw.rounded_rectangle([60, 270, WIDTH - 60, 880], radius=28, fill=CARD_BG, outline="#334155", width=2)

    # Number Badge
    draw.rounded_rectangle([100, 320, 190, 410], radius=20, fill="#1E293B", outline=BORDER_GOLD, width=2)
    badge_font = get_font(FONT_SIZE_SUBLINE, bold=True)
    draw.text((130, 340), str(step_idx), fill=ACCENT_GOLD, font=badge_font)

    title = point.get("title", "")
    cur_y = 440
    if title:
        title_lines = wrap_text(title, max_width=WIDTH - 240, font=font_subline)
        for t_line in title_lines:
            draw.text((100, cur_y), t_line, fill=TEXT_WHITE, font=font_subline)
            cur_y += int(FONT_SIZE_SUBLINE * 1.3)

    detail = point.get("detail", "")
    if detail:
        cur_y += 20
        detail_lines = wrap_text(detail, max_width=WIDTH - 240, font=font_body)
        for d_line in detail_lines:
            draw.text((100, cur_y), d_line, fill=TEXT_MUTED, font=font_body)
            cur_y += int(FONT_SIZE_BODY * 1.3)

    return img


def render_cta_slide(data: dict[str, Any], total_slides: int) -> Image.Image:
    brand = data.get("brandName", "LICBARSKA")
    img, draw = create_base_slide(total_slides, total_slides, brand)
    cta = data.get("cta", {})

    font_label = get_font(FONT_SIZE_LABEL)
    font_title = get_font(FONT_SIZE_SUBLINE + 8, bold=True)
    font_body = get_font(FONT_SIZE_BODY)

    draw.rounded_rectangle([60, 260, WIDTH - 60, 950], radius=32, fill=CARD_BG, outline=BORDER_GOLD, width=2)

    draw.text((100, 330), "NÄCHSTER SCHRITT", fill=ACCENT_GOLD, font=font_label)

    cur_y = 390
    headline = cta.get("headline", "")
    if headline:
        h_lines = wrap_text(headline, max_width=WIDTH - 200, font=font_title)
        for h_line in h_lines:
            draw.text((100, cur_y), h_line, fill=TEXT_WHITE, font=font_title)
            cur_y += int((FONT_SIZE_SUBLINE + 8) * 1.25)

    subline = cta.get("subline", "")
    if subline:
        cur_y += 15
        s_lines = wrap_text(subline, max_width=WIDTH - 200, font=font_body)
        for s_line in s_lines:
            draw.text((100, cur_y), s_line, fill=TEXT_MUTED, font=font_body)
            cur_y += int(FONT_SIZE_BODY * 1.3)

    # CTA Button Box
    badge = cta.get("badge")
    btn_y = max(cur_y + 40, 680)
    if badge:
        draw.rounded_rectangle([100, btn_y, WIDTH - 100, btn_y + 100], radius=50, fill="#D4AF37")
        btn_font = get_font(FONT_SIZE_LABEL + 4, bold=True)
        btn_text = badge.upper()
        btn_bbox = btn_font.getbbox(btn_text)
        btn_w = btn_bbox[2] - btn_bbox[0]
        btn_h = btn_bbox[3] - btn_bbox[1]
        draw.text(((WIDTH - btn_w) // 2, btn_y + (100 - btn_h) // 2 - btn_bbox[1]), btn_text, fill="#07090E", font=btn_font)
        btn_y += 100

    if cta.get("url"):
        url_font = get_font(FONT_SIZE_BODY, bold=True)
        url_text = cta["url"]
        url_bbox = url_font.getbbox(url_text)
        url_w = url_bbox[2] - url_bbox[0]
        draw.text(((WIDTH - url_w) // 2, btn_y + 30), url_text, fill=ACCENT_GOLD, font=url_font)

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

    base_name = input_json.stem
    pdf_out = output_pdf or (target_dir / f"{base_name}_carousel.pdf")
    pdf_out.parent.mkdir(parents=True, exist_ok=True)

    # Export PNGs
    png_paths: list[str] = []
    for idx, slide in enumerate(slides):
        p = target_dir / f"{base_name}_slide_{idx+1:02d}.png"
        slide.save(p, "PNG")
        png_paths.append(str(p))

    # Export Multi-page PDF for LinkedIn
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
