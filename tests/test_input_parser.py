from pathlib import Path

import pytest

from tools import input_parser


def test_empty_input_is_rejected_without_external_call() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        input_parser.parse("   ")


def test_explicit_script_preserves_unicode(tmp_path: Path) -> None:
    script = tmp_path / "überblick.md"
    script.write_text("Grüße aus Köln — zuverlässig.", encoding="utf-8")

    parsed = input_parser.parse("", script_file=str(script), language="de")

    assert parsed.title == "überblick"
    assert parsed.script == "Grüße aus Köln — zuverlässig."
    assert parsed.type is input_parser.InputType.SCRIPT


def test_topic_title_is_deterministic_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_parser, "_topic_to_script", lambda *_args, **_kwargs: "script")
    topic = "Äußerst langer Titel! " * 20

    first = input_parser.parse(topic)
    second = input_parser.parse(topic)

    assert first.title == second.title
    assert len(first.title) <= 60


def test_url_classification_can_be_tested_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(input_parser, "_url_to_script", lambda *_args, **_kwargs: "script")

    parsed = input_parser.parse("https://www.example.test/path")

    assert parsed.type is input_parser.InputType.URL
    assert parsed.title == "example.test"
