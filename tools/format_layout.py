#!/usr/bin/env python3
"""Resolve editable scene text into target-format-safe pixel layouts.

This module deliberately does not crop a rendered text master.  It validates the
same source scene independently for each profile before Remotion receives it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from contracts.validate_contracts import validate
from tools import platform_profiles


class FormatLayoutError(RuntimeError):
    """The scene layout cannot safely be rendered for a requested profile."""


def format_key(profile: dict[str, Any]) -> str:
    aspect = str(profile["aspect_ratio"])
    if aspect not in {"16:9", "9:16", "1:1"}:
        raise FormatLayoutError(f"Kein formatadaptives Layout für Seitenverhältnis {aspect}.")
    return aspect


def safe_area(profile: dict[str, Any]) -> dict[str, int]:
    """Use an explicit profile safe zone, otherwise a conservative 5% canvas inset."""
    resolution = profile["resolution"]
    width, height = int(resolution["width"]), int(resolution["height"])
    explicit = profile.get("safe_zone")
    if explicit:
        return {key: int(explicit[key]) for key in ("x", "y", "width", "height")}
    inset_x, inset_y = round(width * 0.05), round(height * 0.05)
    return {
        "x": inset_x,
        "y": inset_y,
        "width": width - 2 * inset_x,
        "height": height - 2 * inset_y,
    }


def load_scene(path: Path) -> dict[str, Any]:
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FormatLayoutError(f"Scene-Layout nicht lesbar: {error}") from error
    errors = validate("scene_layout", scene)
    if errors:
        raise FormatLayoutError(f"Scene-Layout verletzt Contract: {errors[0]}")
    return scene


def _pixel_layout(layout: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    required = ("x", "y", "width", "height", "font_size", "max_lines")
    missing = [key for key in required if key not in layout]
    if missing:
        raise FormatLayoutError(f"Layout benötigt {', '.join(missing)}.")
    return {
        "x": round(float(layout["x"]) * width),
        "y": round(float(layout["y"]) * height),
        "width": round(float(layout["width"]) * width),
        "height": round(float(layout["height"]) * height),
        "fontSize": max(1, round(float(layout["font_size"]) * min(width, height))),
        "maxLines": int(layout["max_lines"]),
        "align": str(layout.get("align", "center")),
        "visible": bool(layout.get("visible", True)),
    }


def _wrapped_line_count(text: str, available_width: int, font_size: int) -> int:
    # A deliberately conservative Latin/Cyrillic glyph estimate. The renderer also
    # applies overflow:hidden, but an estimate that exceeds maxLines is a hard fail.
    chars_per_line = max(1, math.floor(available_width / (font_size * 0.56)))
    count = 0
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            count += 1
            continue
        line_length = 0
        for word in words:
            proposed = len(word) if not line_length else line_length + 1 + len(word)
            if line_length and proposed > chars_per_line:
                count += 1
                line_length = len(word)
            else:
                line_length = proposed
        count += 1
    return count


def resolve_scene(scene: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profile = platform_profiles.get_profile(profile_name)
    key = format_key(profile)
    resolution = profile["resolution"]
    width, height = int(resolution["width"]), int(resolution["height"])
    area = safe_area(profile)
    elements: list[dict[str, Any]] = []
    issues: list[str] = []
    for source in scene["elements"]:
        source_layout = dict(source["layout"])
        source_layout.update((source.get("overrides") or {}).get(key, {}))
        layout = _pixel_layout(source_layout, width, height)
        element = {
            "id": source["id"],
            "content": source["content"],
            "priority": source.get("priority", 0),
            **layout,
        }
        if layout["visible"]:
            x, y, w, h = layout["x"], layout["y"], layout["width"], layout["height"]
            if x < 0 or y < 0 or x + w > width or y + h > height:
                issues.append(f"{source['id']}: außerhalb des Frames")
            if (
                x < area["x"]
                or y < area["y"]
                or x + w > area["x"] + area["width"]
                or y + h > area["y"] + area["height"]
            ):
                issues.append(f"{source['id']}: außerhalb der Safe Area")
            line_count = _wrapped_line_count(str(source["content"]), w, layout["fontSize"])
            if line_count > layout["maxLines"]:
                issues.append(
                    f"{source['id']}: Textüberlauf ({line_count}>{layout['maxLines']} Zeilen)"
                )
            if layout["height"] < math.ceil(
                layout["fontSize"] * 1.25 * min(line_count, layout["maxLines"])
            ):
                issues.append(f"{source['id']}: Texthöhe zu klein")
        elements.append(element)
    return {
        "profile": profile_name,
        "format": key,
        "width": width,
        "height": height,
        "safeArea": area,
        "elements": elements,
        "issues": issues,
    }


def resolve_scene_file(path: Path, profile_name: str) -> dict[str, Any]:
    return resolve_scene(load_scene(path), profile_name)
