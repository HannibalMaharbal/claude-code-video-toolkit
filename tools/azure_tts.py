#!/usr/bin/env python3
"""Generate Arabic speech with Azure Speech's regional neural voices."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
import xml.sax.saxutils
from pathlib import Path
from urllib.request import HTTPRedirectHandler

AZURE_VOICES = {
    "ar-TN": {"female": "ar-TN-ReemNeural", "male": "ar-TN-HediNeural"},
    "ar-DZ": {"female": "ar-DZ-AminaNeural", "male": "ar-DZ-IsmaelNeural"},
    "ar-MA": {"female": "ar-MA-MounaNeural", "male": "ar-MA-JamalNeural"},
    "ar-LB": {"female": "ar-LB-LaylaNeural", "male": "ar-LB-RamiNeural"},
    "ar-SY": {"female": "ar-SY-AmanyNeural", "male": "ar-SY-LaithNeural"},
    "ar-EG": {"female": "ar-EG-SalmaNeural", "male": "ar-EG-ShakirNeural"},
    # Azure has no distinct MSA locale. This is a transparent regional-voice fallback.
    "ar-msa": {"female": "ar-SA-ZariyahNeural", "male": "ar-SA-HamedNeural"},
}

LOCALE_LABELS = {
    "ar-TN": "Tunisian Arabic",
    "ar-DZ": "Algerian Arabic",
    "ar-MA": "Moroccan Arabic",
    "ar-LB": "Lebanese Arabic",
    "ar-SY": "Syrian Arabic",
    "ar-EG": "Egyptian Arabic",
    "ar-msa": "Modern Standard Arabic (Saudi voice approximation)",
}

OUTPUT_FORMAT = "audio-24khz-160kbitrate-mono-mp3"
SPEECH_ENDPOINT = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


class _RejectRedirects(HTTPRedirectHandler):
    """Keep the subscription key bound to the configured Azure endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_ssml(text: str, locale: str, voice: str) -> bytes:
    """Build an escaped SSML request using a voice supported by the selected locale."""
    if locale not in AZURE_VOICES:
        raise ValueError(f"Unsupported Azure Arabic locale: {locale}")
    if voice not in AZURE_VOICES[locale].values():
        raise ValueError(f"Voice {voice!r} does not belong to locale {locale}")
    if not text.strip():
        raise ValueError("Speech text must not be empty")
    voice_locale = "ar-SA" if locale == "ar-msa" else locale
    escaped_text = xml.sax.saxutils.escape(text)
    ssml = (
        f'<speak version="1.0" xml:lang="{voice_locale}">'
        f'<voice xml:lang="{voice_locale}" name="{voice}">{escaped_text}</voice>'
        "</speak>"
    )
    return ssml.encode("utf-8")


def generate_audio(
    text: str,
    output_path: str | Path,
    locale: str,
    gender: str = "female",
    *,
    api_key: str | None = None,
    region: str | None = None,
    timeout: float = 60,
) -> dict:
    """Synthesize speech through Azure's real-time REST endpoint."""
    key = api_key or os.getenv("AZURE_SPEECH_KEY")
    azure_region = region or os.getenv("AZURE_SPEECH_REGION")
    if not key:
        return {"success": False, "error": "AZURE_SPEECH_KEY is not configured"}
    if not azure_region or not re.fullmatch(r"[a-z0-9]+", azure_region):
        return {"success": False, "error": "AZURE_SPEECH_REGION is missing or invalid"}
    if gender not in {"female", "male"}:
        return {"success": False, "error": "gender must be 'female' or 'male'"}
    path = Path(output_path)
    if path.suffix.lower() != ".mp3":
        return {"success": False, "error": "Azure Speech output must use the .mp3 extension"}
    if path.exists():
        return {"success": False, "error": f"Refusing to overwrite existing output: {path}"}

    try:
        ssml = build_ssml(text, locale, AZURE_VOICES[locale][gender])
    except (KeyError, ValueError) as exc:
        return {"success": False, "error": str(exc)}

    request = urllib.request.Request(
        SPEECH_ENDPOINT.format(region=azure_region),
        data=ssml,
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "video-toolkit",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_RejectRedirects)
        with opener.open(request, timeout=timeout) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        # Do not include response headers or request data; they may contain credentials.
        detail = exc.read(2048).decode("utf-8", errors="replace")
        return {"success": False, "error": f"Azure Speech HTTP {exc.code}: {detail}"}
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        return {"success": False, "error": f"Azure Speech request failed: {reason}"}

    if not audio:
        return {"success": False, "error": "Azure Speech returned an empty audio response"}
    if not response.headers.get("Content-Type", "").startswith("audio/"):
        return {"success": False, "error": "Azure Speech returned a non-audio response"}

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(audio)
    except FileExistsError:
        return {"success": False, "error": f"Refusing to overwrite existing output: {path}"}
    except OSError as exc:
        return {"success": False, "error": f"Could not write Azure Speech output: {exc}"}
    return {
        "success": True,
        "output": str(path),
        "script_chars": len(text),
        "locale": locale,
        "locale_label": LOCALE_LABELS[locale],
        "voice": AZURE_VOICES[locale][gender],
        "format": "mp3",
    }
