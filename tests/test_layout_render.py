from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools import layout_render

ROOT = Path(__file__).resolve().parents[1]


def _spec(**canvas: object) -> dict[str, object]:
    return {
        "canvas": {"preset": "custom", "width": 200, "height": 100, **canvas},
        "layers": [
            {
                "id": "bg",
                "type": "shape",
                "color": "#112233",
                "x": 0,
                "y": 0,
                "width": 200,
                "height": 100,
            }
        ],
    }


# --- Pure logic: no browser involved -------------------------------------------------


def test_dimensions_custom_uses_pixel_size() -> None:
    assert layout_render.dimensions(_spec()) == (200, 100)


def test_dimensions_a4_default_dpi_matches_original_hardcoded_values() -> None:
    assert layout_render.dimensions({"canvas": {"preset": "A4"}, "layers": []}) == (794, 1123)


def test_dimensions_a5_default_dpi_matches_original_hardcoded_values() -> None:
    assert layout_render.dimensions({"canvas": {"preset": "A5"}, "layers": []}) == (559, 794)


def test_dimensions_a5_scales_with_dpi() -> None:
    width_150, height_150 = layout_render.dimensions(
        {"canvas": {"preset": "A5", "dpi": 150}, "layers": []}
    )
    width_96, _ = layout_render.dimensions({"canvas": {"preset": "A5"}, "layers": []})
    assert width_150 > width_96
    assert (width_150, height_150) == (874, 1240)


def test_load_spec_valid(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    assert layout_render.load_spec(spec_path)["canvas"]["width"] == 200


def test_load_spec_rejects_schema_violation(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"canvas": {"preset": "custom"}, "layers": []}), encoding="utf-8"
    )
    with pytest.raises(layout_render.LayoutError, match="Schema"):
        layout_render.load_spec(spec_path)


def test_load_spec_rejects_unreadable_json(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(layout_render.LayoutError, match="lesbar"):
        layout_render.load_spec(spec_path)


def test_html_renders_shape_and_escapes_text() -> None:
    spec = _spec()
    spec["layers"].append(
        {
            "id": "t",
            "type": "text",
            "content": "<script>",
            "x": 0,
            "y": 0,
            "width": 10,
            "height": 10,
        }
    )
    markup = layout_render.html(spec)
    assert "background:#112233" in markup
    assert "&lt;script&gt;" in markup
    assert "<script>" not in markup


def test_html_image_layer_resolves_relative_path(tmp_path: Path) -> None:
    image_path = tmp_path / "pic.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(image_path)
    spec_path = tmp_path / "spec.json"
    spec = {
        "canvas": {"preset": "custom", "width": 10, "height": 10},
        "layers": [{"id": "img", "type": "image", "path": "pic.png", "x": 0, "y": 0}],
    }
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    markup = layout_render.html(spec, spec_path)
    assert image_path.resolve().as_uri() in markup


def test_html_image_layer_missing_file_raises(tmp_path: Path) -> None:
    spec = {
        "canvas": {"preset": "custom", "width": 10, "height": 10},
        "layers": [{"id": "img", "type": "image", "path": "nope.png", "x": 0, "y": 0}],
    }
    with pytest.raises(layout_render.LayoutError, match="nicht gefunden"):
        layout_render.html(spec, tmp_path / "spec.json")


def test_html_text_layer_with_font_file_embeds_data_uri(tmp_path: Path) -> None:
    font_path = next(iter(layout_render.list_fonts()), None)
    if font_path is None:
        pytest.skip("Keine lokale .ttf/.otf/.ttc-Schriftdatei gefunden.")
    spec = _spec()
    spec["layers"].append(
        {
            "id": "t",
            "type": "text",
            "content": "Hi",
            "font_file": font_path,
            "x": 0,
            "y": 0,
            "width": 10,
            "height": 10,
        }
    )
    markup = layout_render.html(spec)
    assert "@font-face" in markup
    assert "layout-font-t" in markup
    assert "base64," in markup


def test_is_local_request() -> None:
    assert layout_render.is_local_request("file:///tmp/x.png") is True
    assert layout_render.is_local_request("data:image/png;base64,AA==") is True
    assert layout_render.is_local_request("https://example.invalid/x.png") is False
    assert layout_render.is_local_request("http://example.invalid/x.png") is False


def test_list_fonts_only_lists_local_font_files() -> None:
    fonts = layout_render.list_fonts()
    assert all(Path(font).suffix.lower() in {".ttf", ".otf", ".ttc"} for font in fonts)


def test_set_value_updates_layer_and_writes_backup(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")

    layout_render.set_value(spec_path, "bg", "color=#ff0000")

    updated = layout_render.load_spec(spec_path)
    assert updated["layers"][0]["color"] == "#ff0000"
    backups = list(tmp_path.glob("spec.json.bak.*"))
    assert len(backups) == 1
    original = json.loads(backups[0].read_text(encoding="utf-8"))
    assert original["layers"][0]["color"] == "#112233"


def test_set_value_parses_json_numeric_values(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")

    layout_render.set_value(spec_path, "bg", "height=250")

    assert layout_render.load_spec(spec_path)["layers"][0]["height"] == 250


def test_set_value_rejects_unknown_layer(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    with pytest.raises(layout_render.LayoutError, match="Layer nicht gefunden"):
        layout_render.set_value(spec_path, "missing", "color=#000000")


def test_set_value_refuses_schema_violating_change(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    with pytest.raises(layout_render.LayoutError, match="Schema"):
        layout_render.set_value(spec_path, "bg", "type=unknown-type")


# --- Asset registration: mocked ASSET_ROOT, no browser -------------------------------


def test_register_outputs_inherits_rights_from_spec_and_image(tmp_path: Path, monkeypatch) -> None:
    from tools import asset_record

    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "asset-store")

    image_path = tmp_path / "pic.png"
    Image.new("RGB", (10, 10), (4, 5, 6)).save(image_path)
    spec_path = tmp_path / "spec.json"
    spec = {
        "canvas": {"preset": "custom", "width": 10, "height": 10},
        "layers": [{"id": "img", "type": "image", "path": "pic.png", "x": 0, "y": 0}],
    }
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    png_path = tmp_path / "out.png"
    Image.new("RGB", (10, 10), (7, 8, 9)).save(png_path)

    records = layout_render.register_outputs(spec_path, png_path)

    assert len(records) == 1
    output_record = records[0]
    assert output_record["role"] == "MASTER"
    assert len(output_record["parent_ids"]) == 2
    spec_records = list((tmp_path / "asset-store" / "editable_source").rglob("*.asset.json"))
    assert len(spec_records) == 1


def test_register_outputs_registers_pdf_too(tmp_path: Path, monkeypatch) -> None:
    from tools import asset_record

    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "asset-store")

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    png_path = tmp_path / "out.png"
    Image.new("RGB", (10, 10), (7, 8, 9)).save(png_path)
    pdf_path = tmp_path / "out.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fake pdf content for asset registration test\n")

    records = layout_render.register_outputs(spec_path, png_path, pdf_path)

    assert len(records) == 2
    assert {record["derivation"]["operation"] for record in records} == {
        "render_png",
        "render_pdf",
    }


# --- Browser-backed: real Playwright/Chromium, network-blocked -----------------------


@pytest.mark.integration
def test_render_produces_png_and_pdf_for_flyer_a5(tmp_path: Path) -> None:
    spec_path = ROOT / "templates" / "layout" / "flyer-a5.json"
    png_path, pdf_path = tmp_path / "flyer.png", tmp_path / "flyer.pdf"

    layout_render.render(spec_path, png_path, pdf_path)

    assert png_path.is_file() and png_path.stat().st_size > 0
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
    with Image.open(png_path) as image:
        assert image.size == (559, 794)


@pytest.mark.integration
def test_render_produces_png_for_flyer_a4(tmp_path: Path) -> None:
    spec_path = ROOT / "templates" / "layout" / "flyer-a4.json"
    png_path = tmp_path / "flyer.png"

    layout_render.render(spec_path, png_path)

    with Image.open(png_path) as image:
        assert image.size == (794, 1123)


@pytest.mark.integration
def test_chromium_page_blocks_every_non_local_request(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    failed_urls: list[str] = []
    finished_urls: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if layout_render.is_local_request(route.request.url)
                    else route.abort()
                ),
            )
            page.on("requestfailed", lambda request: failed_urls.append(request.url))
            page.on("requestfinished", lambda request: finished_urls.append(request.url))
            page.set_content(
                '<html><body><img src="https://example.invalid/pixel.png">'
                '<script src="http://example.invalid/evil.js"></script></body></html>'
            )
            page.wait_for_timeout(500)
        finally:
            browser.close()

    assert any("example.invalid" in url for url in failed_urls)
    assert not any("example.invalid" in url for url in finished_urls)
