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
