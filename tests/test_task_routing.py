from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_TYPES = {
    "image_edit",
    "image_generate",
    "layout",
    "video_cut",
    "audio_process",
    "tts",
    "stt",
    "subtitle",
    "translate",
    "qc_visual",
    "semantic_analysis",
    "code",
}
REQUIRED_ROUTE_FIELDS = {
    "primary",
    "secondary",
    "fallback",
    "locality",
    "cost_class",
    "requires_approval",
}


def _load_routing() -> dict[str, object]:
    return json.loads((ROOT / "contracts" / "task-routing.json").read_text(encoding="utf-8"))


def test_routing_validates_against_schema() -> None:
    from contracts.validate_contracts import validate

    assert validate("routing", _load_routing()) == []


def test_routing_covers_every_task_type() -> None:
    routing = _load_routing()
    assert set(routing["routes"]) == TASK_TYPES


def test_every_route_has_required_fields_and_valid_enums() -> None:
    routing = _load_routing()
    for task_type, route in routing["routes"].items():
        assert set(route) == REQUIRED_ROUTE_FIELDS, task_type
        assert route["locality"] in {"local", "cloud", "mixed"}, task_type
        assert route["cost_class"] in {"FREE", "PAID", "LIMITED"}, task_type
        assert isinstance(route["requires_approval"], bool), task_type
        assert isinstance(route["primary"], str) and route["primary"], task_type


def test_cloud_routes_require_approval() -> None:
    routing = _load_routing()
    for task_type, route in routing["routes"].items():
        if route["locality"] == "cloud":
            assert route["requires_approval"] is True, task_type


def test_local_free_routes_do_not_require_approval() -> None:
    routing = _load_routing()
    for task_type, route in routing["routes"].items():
        if route["locality"] == "local" and route["cost_class"] == "FREE":
            assert route["requires_approval"] is False, task_type


def test_schema_rejects_missing_task_type() -> None:
    from contracts.validate_contracts import validate

    routing = _load_routing()
    del routing["routes"]["code"]
    assert validate("routing", routing) != []


def test_schema_rejects_cloud_route_without_approval() -> None:
    from contracts.validate_contracts import validate

    routing = _load_routing()
    routing["routes"]["image_generate"]["requires_approval"] = False
    assert validate("routing", routing) != []
