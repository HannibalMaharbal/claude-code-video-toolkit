from __future__ import annotations

from pathlib import Path
import pytest
from PIL import Image, ImageDraw

from tools import thumbnail_ctr_audit


def test_analyze_thumbnail_computes_score_and_metrics(tmp_path: Path) -> None:
    img_path = tmp_path / "test_thumb.png"
    # Create high-contrast test image (black bg with white circle)
    img = Image.new("RGB", (1280, 720), "#000000")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 600, 400], fill="#FFFFFF")
    img.save(img_path)

    res = thumbnail_ctr_audit.analyze_thumbnail(img_path)

    assert "composite_score" in res
    assert res["composite_score"] > 50.0
    assert res["dimensions"] == "1280x720"
    assert "metrics" in res
    assert res["metrics"]["luminance_contrast_std"] > 40.0


def test_analyze_thumbnail_fails_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        thumbnail_ctr_audit.analyze_thumbnail(tmp_path / "non_existent.jpg")


def test_generate_diagnostic_sheet(tmp_path: Path) -> None:
    img_path = tmp_path / "source.png"
    out_sheet = tmp_path / "sheet.jpg"
    img = Image.new("RGB", (1280, 720), "#1E293B")
    img.save(img_path)

    res_path = thumbnail_ctr_audit.generate_diagnostic_sheet(img_path, out_sheet)

    assert res_path.is_file()
    assert res_path.stat().st_size > 0
