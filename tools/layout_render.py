#!/usr/bin/env python3
"""Local layout specs rendered as HTML via a network-blocked Playwright page.

Spec JSON -> HTML -> Chromium screenshot/PDF. Chromium is only ever given
``file://``/``data:`` content; every other request is aborted. Rendering
logic (HTML generation, dimensions, spec editing) is Playwright-free and
unit-testable on its own; only ``render()`` touches the browser.
"""

from __future__ import annotations

import argparse
import base64
import html as html_escape
import json
import mimetypes
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate

MM_SIZES: dict[str, tuple[float, float]] = {"A4": (210.0, 297.0), "A5": (148.0, 210.0)}
DEFAULT_DPI = 96
LOCAL_FONT_DIRS = (
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path.home() / "Library" / "Fonts",
)


class LayoutError(RuntimeError):
    """A layout spec could not be validated, rendered, or edited."""


def load_spec(path: Path) -> dict[str, Any]:
    """Read and schema-validate a layout spec. Fail-closed on any violation."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LayoutError(f"Spec ist nicht lesbar: {error}") from error
    errors = validate("layout", data)
    if errors:
        raise LayoutError(f"Spec verletzt das Schema: {errors[0]}")
    return data


def dimensions(spec: dict[str, Any]) -> tuple[int, int]:
    """Pixel dimensions for the canvas, honoring dpi for A4/A5 paper presets."""
    canvas = spec["canvas"]
    preset = canvas["preset"]
    if preset in MM_SIZES:
        dpi = canvas.get("dpi", DEFAULT_DPI)
        width_mm, height_mm = MM_SIZES[preset]
        return round(width_mm / 25.4 * dpi), round(height_mm / 25.4 * dpi)
    return int(canvas["width"]), int(canvas["height"])


def _font_face(layer: dict[str, Any]) -> tuple[str, str] | None:
    """Return (css @font-face rule, family name) for a text layer's font_file."""
    font_file = layer.get("font_file")
    if not font_file:
        return None
    font_path = Path(font_file).expanduser()
    if not font_path.is_file():
        raise LayoutError(f"font_file nicht gefunden: {font_file}")
    mime, _ = mimetypes.guess_type(font_path.name)
    mime = mime or "font/ttf"
    data_uri = f"data:{mime};base64,{base64.b64encode(font_path.read_bytes()).decode('ascii')}"
    family = f"layout-font-{layer['id']}"
    rule = f"@font-face{{font-family:'{family}';src:url({data_uri});}}"
    return rule, family


def _image_src(layer: dict[str, Any], spec_path: Path | None) -> str:
    """Resolve an image layer to a local file:// or data: URL Chromium may load."""
    asset_id = layer.get("asset_id")
    if asset_id:
        from tools.asset_record import ASSET_ROOT, load_asset_record

        record, _ = load_asset_record(asset_id)
        image_path = (ASSET_ROOT / str(record["path"])).resolve()
    else:
        raw_path = layer.get("path")
        if not raw_path:
            raise LayoutError(f"Bild-Layer {layer['id']} braucht asset_id oder path.")
        image_path = Path(raw_path).expanduser()
        if not image_path.is_absolute():
            base = spec_path.parent if spec_path else Path.cwd()
            image_path = (base / image_path).resolve()
    if not image_path.is_file():
        raise LayoutError(f"Bild nicht gefunden: {image_path}")
    return image_path.as_uri()


def html(spec: dict[str, Any], spec_path: Path | None = None) -> str:
    """Render a layout spec to self-contained HTML (no external requests needed)."""
    width, height = dimensions(spec)
    font_rules: list[str] = []
    body: list[str] = []
    for layer in spec["layers"]:
        style = (
            f"position:absolute;left:{layer.get('x', 0)}px;top:{layer.get('y', 0)}px;"
            f"width:{layer.get('width', width)}px;height:{layer.get('height', height)}px;"
            f"opacity:{layer.get('opacity', 1)};transform:rotate({layer.get('rotation', 0)}deg);"
        )
        if layer["type"] == "shape":
            body.append(f'<div style="{style}background:{layer.get("color", "#fff")}"></div>')
        elif layer["type"] == "image":
            src = _image_src(layer, spec_path)
            fit = layer.get("fit", "cover")
            body.append(f'<img src="{src}" style="{style}object-fit:{fit}">')
        else:
            face = _font_face(layer)
            font_family = layer.get("font_family", "Arial")
            if face is not None:
                rule, font_family = face
                font_rules.append(rule)
            text_style = (
                f"{style}color:{layer.get('color', '#000')};"
                f"font-family:'{font_family}';font-size:{layer.get('size_pt', 12)}pt;"
                f"font-weight:{layer.get('weight', 'normal')};"
                f"text-align:{layer.get('align', 'left')};"
                f"line-height:{layer.get('line_height', 1.2)};"
                "white-space:pre-wrap;word-wrap:break-word;overflow-wrap:break-word;"
            )
            content = html_escape.escape(layer.get("content", ""))
            body.append(f'<div style="{text_style}">{content}</div>')
    style_block = f"<style>{''.join(font_rules)}</style>" if font_rules else ""
    return (
        f'<html><head>{style_block}</head><body style="margin:0;width:{width}px;'
        f'height:{height}px;position:relative;overflow:hidden">{"".join(body)}</body></html>'
    )


def is_local_request(url: str) -> bool:
    """Only ``file://`` and ``data:`` requests may reach Chromium's page."""
    return url.startswith(("file:", "data:"))


def render(spec_path: Path, png: Path, pdf: Path | None = None) -> None:
    """Render one spec to PNG (and optionally PDF) using a network-locked Chromium page."""
    spec = load_spec(spec_path)
    markup = html(spec, spec_path)
    width, height = dimensions(spec)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise LayoutError(
            "Playwright fehlt; keine Installation wird automatisch gestartet."
        ) from error
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route(
                "**/*",
                lambda route: route.continue_()
                if is_local_request(route.request.url)
                else route.abort(),
            )
            page.set_content(markup)
            png.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(png))
            if pdf is not None:
                pdf.parent.mkdir(parents=True, exist_ok=True)
                page.pdf(
                    path=str(pdf),
                    width=f"{width}px",
                    height=f"{height}px",
                    print_background=True,
                )
        finally:
            browser.close()


def _image_parent_ids(spec: dict[str, Any], spec_path: Path) -> list[str]:
    """Register/verify every image layer's source asset and return its asset_id."""
    from tools import asset_record

    parent_ids: list[str] = []
    for layer in spec["layers"]:
        if layer["type"] != "image":
            continue
        asset_id = layer.get("asset_id")
        if asset_id:
            asset_record.load_asset_record(asset_id)
            resolved_id = str(asset_id)
        else:
            raw_path = Path(layer["path"]).expanduser()
            if not raw_path.is_absolute():
                raw_path = (spec_path.parent / raw_path).resolve()
            resolved_id = str(asset_record.register_asset(raw_path)["asset_id"])
        if resolved_id not in parent_ids:
            parent_ids.append(resolved_id)
    return parent_ids


def register_outputs(
    spec_path: Path, png: Path, pdf: Path | None = None
) -> list[dict[str, Any]]:
    """Register the spec (EDITABLE_SOURCE) and rendered outputs (MASTER) with inherited rights."""
    from tools import asset_record

    spec = load_spec(spec_path)
    spec_record = asset_record.register_asset(spec_path, role="EDITABLE_SOURCE")
    parents: list[str] = [str(spec_record["asset_id"]), *_image_parent_ids(spec, spec_path)]
    records = [
        asset_record.register_derived(
            png, parents=parents, role="MASTER", tool="layout_render", operation="render_png"
        )
    ]
    if pdf is not None:
        records.append(
            asset_record.register_derived(
                pdf, parents=parents, role="MASTER", tool="layout_render", operation="render_pdf"
            )
        )
    return records


def set_value(path: Path, layer_id: str, assignment: str) -> None:
    """Set one layer's field in-place, keeping a timestamped backup of the prior spec."""
    if "=" not in assignment:
        raise LayoutError("Zuweisung muss key=wert sein.")
    key, raw_value = assignment.split("=", 1)
    spec = load_spec(path)
    layer = next((entry for entry in spec["layers"] if entry["id"] == layer_id), None)
    if layer is None:
        raise LayoutError(f"Layer nicht gefunden: {layer_id}")
    backup = path.with_name(path.name + ".bak." + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(path, backup)
    try:
        value: Any = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    layer[key] = value
    errors = validate("layout", spec)
    if errors:
        raise LayoutError(f"Änderung verletzt das Schema: {errors[0]}")
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_fonts() -> list[str]:
    """List locally installed font files. Never fetches or downloads anything."""
    fonts: list[str] = []
    for directory in LOCAL_FONT_DIRS:
        if not directory.is_dir():
            continue
        for font_path in directory.rglob("*"):
            if font_path.suffix.lower() in {".ttf", ".otf", ".ttc"}:
                fonts.append(str(font_path))
    return sorted(fonts)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render or edit local layout specs.")
    commands = parser.add_subparsers(dest="cmd", required=True)

    render_parser = commands.add_parser("render", help="Render a spec to PNG (and optional PDF).")
    render_parser.add_argument("spec", type=Path)
    render_parser.add_argument("--png", type=Path, required=True)
    render_parser.add_argument("--pdf", type=Path)
    render_parser.add_argument(
        "--no-register", action="store_true", help="Skip asset registration of spec/outputs."
    )

    set_parser = commands.add_parser("set", help="Set one layer field, backing up the old spec.")
    set_parser.add_argument("spec", type=Path)
    set_parser.add_argument("layer_id")
    set_parser.add_argument("assignment")

    commands.add_parser("list-fonts", help="List locally installed font files.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.cmd == "render":
            render(args.spec, args.png, args.pdf)
            if not args.no_register:
                records = register_outputs(args.spec, args.png, args.pdf)
                print(json.dumps(records, ensure_ascii=False))
        elif args.cmd == "set":
            set_value(args.spec, args.layer_id, args.assignment)
        else:
            for font_path in list_fonts():
                print(font_path)
    except LayoutError as error:
        print(f"Layout: ERROR — {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
