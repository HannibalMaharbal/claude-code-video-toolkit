from __future__ import annotations

import urllib.request
from pathlib import Path

from tools import azure_tts


def test_supported_arabic_locales_have_both_voice_genders() -> None:
    assert set(azure_tts.AZURE_VOICES) == {
        "ar-TN", "ar-DZ", "ar-MA", "ar-LB", "ar-SY", "ar-EG", "ar-msa"
    }
    assert all(set(voices) == {"female", "male"} for voices in azure_tts.AZURE_VOICES.values())


def test_build_ssml_escapes_text_and_marks_msa_fallback() -> None:
    ssml = azure_tts.build_ssml("مرحبا & <صديق>", "ar-msa", "ar-SA-ZariyahNeural")
    assert b'xml:lang="ar-SA"' in ssml
    assert b"&amp;" in ssml
    assert b"&lt;\xd8\xb5\xd8\xaf\xd9\x8a\xd9\x82&gt;" in ssml


def test_build_ssml_rejects_voice_from_a_different_locale() -> None:
    try:
        azure_tts.build_ssml("مرحبا", "ar-TN", "ar-SA-ZariyahNeural")
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("mismatched voice should be rejected")


def test_generate_audio_posts_ssml_and_writes_mp3_without_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        headers = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b"fake-mp3"

    class FakeOpener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("Ocp-apim-subscription-key")
            captured["body"] = request.data
            captured["timeout"] = timeout
            return FakeResponse()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FakeOpener())
    output = tmp_path / "voice.mp3"
    result = azure_tts.generate_audio(
        "مرحبا", output, "ar-TN", api_key="test-secret", region="westeurope"
    )

    assert result["success"] is True
    assert result["locale"] == "ar-TN"
    assert output.read_bytes() == b"fake-mp3"
    assert captured["url"] == (
        "https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1"
    )
    assert captured["key"] == "test-secret"
    assert b"ar-TN-ReemNeural" in captured["body"]

    second = azure_tts.generate_audio(
        "another", output, "ar-TN", api_key="test-secret", region="westeurope"
    )
    assert second["success"] is False
    assert "Refusing to overwrite" in second["error"]


def test_generate_audio_requires_credentials_without_network_or_output(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    output = tmp_path / "voice.mp3"

    result = azure_tts.generate_audio("مرحبا", output, "ar-TN")

    assert result == {"success": False, "error": "AZURE_SPEECH_KEY is not configured"}
    assert not output.exists()


def test_voiceover_parser_exposes_explicit_azure_locale_and_confirmation(monkeypatch) -> None:
    from tools import voiceover

    monkeypatch.setattr("sys.argv", [
        "voiceover.py", "--provider", "azure", "--azure-locale", "ar-EG",
        "--confirm-cloud", "--script", "script.txt", "--output", "voice.mp3",
    ])
    args = voiceover.parse_args()
    assert args.provider == "azure"
    assert args.azure_locale == "ar-EG"
    assert args.confirm_cloud is True
