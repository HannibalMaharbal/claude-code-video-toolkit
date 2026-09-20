from __future__ import annotations

import json

from tools import ai_router_check


def test_check_returns_all_expected_backend_keys() -> None:
    result = ai_router_check.check()
    assert set(result) == {
        "ollama",
        "whisper",
        "kokoro",
        "ffmpeg",
        "playwright",
        "remotion",
        "cloud_blocked",
    }
    assert all(isinstance(value, bool) for value in result.values())


def test_local_tools_confirmed_installed_are_reported_ready() -> None:
    result = ai_router_check.check()
    assert result["ffmpeg"] is True
    assert result["ollama"] is True
    assert result["whisper"] is True
    assert result["kokoro"] is True
    assert result["playwright"] is True
    assert result["remotion"] is True


def test_cloud_backend_is_reported_blocked_in_internal_only_mode() -> None:
    assert ai_router_check.check()["cloud_blocked"] is True


def test_check_ffmpeg_returns_false_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(ai_router_check.shutil, "which", lambda _name: None)
    assert ai_router_check._check_ffmpeg() is False


def test_check_kokoro_returns_false_when_cache_incomplete(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(ai_router_check, "KOKORO_CACHE", tmp_path / "missing")
    assert ai_router_check._check_kokoro() is False


def test_main_prints_json_object(capsys) -> None:
    assert ai_router_check.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert "cloud_blocked" in payload
