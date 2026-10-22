from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tools import gemini_tts


def test_modes_contain_all_five_sota_production_presets() -> None:
    expected_modes = {"friendly", "narration", "promote", "podcast", "whisper"}
    assert set(gemini_tts.MODES.keys()) == expected_modes


def test_mode_sets_style_correctly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    captured_body = {}

    def fake_urlopen(req, timeout=60):
        nonlocal captured_body
        captured_body = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "audio", "data": "ZmFrZS1hdWRpby1kYXRh"}]
                }
            ]
        }).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out_file = tmp_path / "out.wav"
        result = gemini_tts.generate_audio(
            text="Hallo Welt [laugh]",
            output_path=str(out_file),
            mode="friendly",
            verbose=False,
        )

        assert result["success"] is True
        assert captured_body["model"] == "gemini-3.8-flash-lite-tts"
        content = captured_body["input"][0]["content"][0]
        assert content["text"] == "Hallo Welt [laugh]"
        assert "warm, friendly" in content["annotations"][0]["style"]


def test_custom_style_combines_with_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    captured_body = {}

    def fake_urlopen(req, timeout=60):
        nonlocal captured_body
        captured_body = json.loads(req.data.decode("utf-8"))
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({
            "steps": [
                {
                    "type": "model_output",
                    "content": [{"type": "audio", "data": "ZmFrZS1hdWRpby1kYXRh"}]
                }
            ]
        }).encode("utf-8")
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out_file = tmp_path / "out.wav"
        result = gemini_tts.generate_audio(
            text="Test",
            output_path=str(out_file),
            mode="narration",
            style="slightly mysterious",
            verbose=False,
        )

        assert result["success"] is True
        style_annot = captured_body["input"][0]["content"][0]["annotations"][0]["style"]
        assert "documentary storytelling" in style_annot
        assert "slightly mysterious" in style_annot
