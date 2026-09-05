import pytest

from tools.scene_splitter import MAX_SCENE_DURATION, SceneType, split, total_duration


def test_empty_script_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        split(" \n ")


def test_structured_script_extracts_code_and_aliases() -> None:
    script = """## Szene 1: Titel | Einführung
Willkommen beim Test.

## Szene 2: terminal | Beispiel
Hier folgt Code.
```python
print("Grüße")
```
"""

    scenes = split(script, brand="licbarska")

    assert [scene.type for scene in scenes] == [SceneType.TITLE, SceneType.CODE]
    assert scenes[1].has_code is True
    assert scenes[1].code_block == 'print("Grüße")'
    assert total_duration(scenes) > 0


def test_very_long_scene_is_bounded_and_deterministic() -> None:
    script = "## Szene 1: voiceover | Lang\n" + "Wort. " * 1000

    first = split(script)
    second = split(script)

    assert first == second
    assert first[0].duration_s == MAX_SCENE_DURATION


def test_unknown_scene_type_falls_back_to_voiceover() -> None:
    scenes = split("## Szene 1: unbekannt | Test\nEin kurzer Satz.")
    assert scenes[0].type is SceneType.VOICEOVER
