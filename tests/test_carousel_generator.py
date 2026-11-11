from __future__ import annotations

import json
from pathlib import Path
import pytest
from tools import carousel_generator


def test_generate_carousel_creates_pdf_and_pngs(tmp_path: Path) -> None:
    data = {
        "brandName": "LICBARSKA",
        "badgeText": "B2B ANALYSE",
        "hookHeadline": "3 KARDINALFEHLER BEIM VERKAUF",
        "hookSubline": "Warum Eigentümer Rendite verschenken",
        "statHighlight": {
            "value": "-22%",
            "label": "Wertverlust",
            "subtitle": "DACH-Daten",
        },
        "keyPoints": [
            {"index": 1, "title": "Punkt Eins", "detail": "Erklärung Eins"},
            {"index": 2, "title": "Punkt Zwei", "detail": "Erklärung Zwei"},
        ],
        "cta": {
            "headline": "OBJEKT PRÜFEN",
            "subline": "Kostenfreie Analyse",
            "badge": "Off-Market",
            "url": "licbarska.de",
        },
    }
    input_file = tmp_path / "content.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    out_pdf = tmp_path / "test_carousel.pdf"
    res = carousel_generator.generate_carousel(input_file, output_pdf=out_pdf, output_dir=tmp_path)

    assert res["status"] == "success"
    # Total slides = Cover (1) + Stat (1) + KeyPoints (2) + CTA (1) = 5
    assert res["total_slides"] == 5
    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 0
    assert len(res["png_slides"]) == 5


def test_generate_carousel_creates_output_parent_directory_before_saving(tmp_path: Path) -> None:
    data = {
        "brandName": "LICBARSKA",
        "hookHeadline": "TEST",
        "keyPoints": [{"index": 1, "title": "P1", "detail": "D1"}],
    }
    input_file = tmp_path / "content.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    out_pdf = tmp_path / "neu" / "x.pdf"
    assert not out_pdf.parent.exists()

    res = carousel_generator.generate_carousel(input_file, output_pdf=out_pdf, output_dir=tmp_path)
    assert res["status"] == "success"
    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 0


def test_carousel_title_font_and_bounding_box_height_ge_50() -> None:
    font = carousel_generator.get_font(carousel_generator.FONT_SIZE_TITLE)
    bbox = font.getbbox("KARDINALFEHLER")
    height = bbox[3] - bbox[1]
    assert height >= 50, f"Titel-Fonthöhe {height}px ist kleiner als 50px"


def test_carousel_output_contains_only_input_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    drawn_texts: list[str] = []
    from PIL import ImageDraw
    original_text = ImageDraw.ImageDraw.text

    def tracking_text(self, xy, text, *args, **kwargs):
        if text:
            drawn_texts.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", tracking_text)

    clean_data = {
        "brandName": "TESTCORP",
        "badgeText": "PRAXISREPORT",
        "hookHeadline": "NEUE REGELN",
        "hookSubline": "Erfolgreiche Strategien",
        "statHighlight": {
            "value": "+45%",
            "label": "Wachstum",
        },
        "keyPoints": [
            {"index": 1, "title": "Erster Hebel", "detail": "Erster Hebel im Detail erklärt."}
        ],
        "cta": {
            "headline": "KONTAKT AUFNEHMEN",
            "subline": "Unverbindlich anfragen",
            "badge": "Jetzt starten",
            "url": "testcorp.example",
        },
    }
    input_file = tmp_path / "clean_content.json"
    input_file.write_text(json.dumps(clean_data), encoding="utf-8")

    carousel_generator.generate_carousel(input_file, output_dir=tmp_path)

    all_text = " ".join(drawn_texts)
    # Must NOT contain hardcoded claims or numbers not in input
    assert "140" not in all_text, "Hardcodierte Zahl '140' gefunden!"
    assert "DACH" not in all_text, "Hardcodiertes 'DACH' gefunden!"
    assert "Erprobt" not in all_text, "Hardcodiertes 'Erprobt' gefunden!"
    assert "Millionen" not in all_text, "Hardcodiertes 'Millionen' gefunden!"


def test_carousel_ambient_top_glow_is_soft_and_not_solid_gold() -> None:
    img, _ = carousel_generator.create_base_slide(1, 5, "LICBARSKA")
    r, g, b = img.getpixel((540, 100))[:3]
    assert r < 120, f"Pixel bei (540, 100) hat R={r} >= 120 (goldener Festkörper)"
    r2, g2, b2 = img.getpixel((535, 100))[:3]
    assert r2 < 120, f"Pixel bei (535, 100) hat R={r2} >= 120 (nahezu reines Gold)"


def test_carousel_long_word_headline_fits_max_width() -> None:
    data = {
        "brandName": "LICBARSKA",
        "hookHeadline": "3 KARDINALFEHLER BEIM MEHRFAMILIENHAUS-VERKAUF",
    }
    cover = carousel_generator.render_cover_slide(data, total_slides=5)
    assert cover is not None

    headline = data["hookHeadline"].upper()
    font, size = carousel_generator.fit_title_font(
        headline, max_width=carousel_generator.WIDTH - 120
    )
    lines = carousel_generator.wrap_text(
        headline, max_width=carousel_generator.WIDTH - 120, font=font
    )
    assert len(lines) >= 2
    for line in lines:
        bbox = font.getbbox(line)
        line_w = bbox[2] - bbox[0]
        assert line_w <= carousel_generator.WIDTH - 120, (
            f"Zeile {line!r} ist mit {line_w}px breiter als max_width ({carousel_generator.WIDTH - 120}px)"
        )


def test_carousel_footer_action_text_contains_only_valid_glyphs() -> None:
    font_label = carousel_generator.get_font(carousel_generator.FONT_SIZE_LABEL)
    footer_next = carousel_generator.get_footer_action_text(1, 5, font_label)
    assert footer_next == "Weiter »"
    assert all(ord(ch) <= 0xFF for ch in footer_next), "Zeichen > U+00FF in Fußzeilentext gefunden"

    footer_last = carousel_generator.get_footer_action_text(5, 5, font_label)
    assert footer_last == "Speichern"
    assert all(ord(ch) <= 0xFF for ch in footer_last), "Zeichen > U+00FF in Fußzeilentext gefunden"


def test_carousel_bracketed_placeholder_wrap_not_broken() -> None:
    font = carousel_generator.get_font(carousel_generator.FONT_SIZE_BODY)
    text = "Käufer preisen unklare ESG-Risiken mit bis zu [XX %] Abschlag ein."
    lines = carousel_generator.wrap_text(text, max_width=840, font=font)
    for line in lines:
        assert not line.endswith("[XX"), f"Platzhalter wurde gebrochen (Zeile endet auf [XX): {line!r}"
        assert not line.startswith("%]"), f"Platzhalter wurde gebrochen (Zeile startet mit %]): {line!r}"
    assert any("[XX %]" in line or "[XX\xa0%]" in line for line in lines)

