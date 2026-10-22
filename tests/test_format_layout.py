from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts.validate_contracts import validate
from tools import format_layout


def _scene() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "elements": [
            {
                "id": "headline",
                "type": "text",
                "content": "Die Zukunft der KI entsteht jetzt.",
                "priority": 1,
                "layout": {
                    "x": 0.15, "y": 0.2, "width": 0.7, "height": 0.18,
                    "font_size": 0.07, "max_lines": 2, "align": "center", "visible": True,
                },
                "overrides": {
                    "9:16": {"x": 0.1, "y": 0.32, "width": 0.8, "height": 0.14, "font_size": 0.05},
                    "1:1": {"x": 0.1, "y": 0.22, "width": 0.8, "height": 0.18, "font_size": 0.055},
                },
            }
        ],
    }


def test_scene_layout_contract_and_format_overrides(tmp_path: Path) -> None:
    scene = _scene()
    assert validate("scene_layout", scene) == []
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    vertical = format_layout.resolve_scene_file(path, "ad_9x16")
    square = format_layout.resolve_scene_file(path, "ad_1x1")
    assert vertical["elements"][0]["fontSize"] != square["elements"][0]["fontSize"]
    assert vertical["issues"] == []
    assert square["issues"] == []


def test_text_outside_safe_area_is_a_hard_issue(tmp_path: Path) -> None:
    scene = _scene()
    element = scene["elements"][0]
    assert isinstance(element, dict)
    element["overrides"] = {
        "9:16": {"x": 0, "y": 0, "width": 0.8, "height": 0.2, "font_size": 0.05}
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    result = format_layout.resolve_scene_file(path, "ad_9x16")
    assert any("Safe Area" in issue for issue in result["issues"])


def test_required_layout_fields_fail_closed() -> None:
    scene = _scene()
    element = scene["elements"][0]
    assert isinstance(element, dict)
    element["layout"] = {"x": 0.1}
    with pytest.raises(format_layout.FormatLayoutError, match="benötigt"):
        format_layout.resolve_scene(scene, "ad_1x1")
