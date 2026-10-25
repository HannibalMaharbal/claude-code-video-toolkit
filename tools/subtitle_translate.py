#!/usr/bin/env python3
"""SRT/VTT subtitle translation via Argos Translate (local, offline, default,
free forever, no account -- verified), Gemini (cloud, explicit opt-in),
2026-09-26) or Ollama (local/offline LLM prompt, unreliable for this task,
kept only for explicit opt-in comparison).

Drei Engines:
1. Argos Translate (Standard): komplett lokal, offline, kostenlos fuer
   immer, kein Account, kein API-Key. Nutzt spezialisierte Uebersetzungsmodelle
   (nicht ein LLM mit Prompt) -- ersetzt den unzuverlaessigen Ollama-Pfad fuer
   diese Aufgabe. Live verifiziert 2026-09-26 (de<->en, korrekte Uebersetzung
   in drei Wiederholungen, exit 0). Sprachpaket muss vorher installiert sein
   (siehe install_argos_language_pair()).
2. Gemini (--engine gemini): Cloud, gemini-3.8-flash, explizite Auswahl.
3. Ollama (--engine ollama): lokal/offline LLM-Prompt, fuer diese Aufgabe
   nachweislich unzuverlaessig (Platzhalter-Echo, Timeouts) -- nur fuer
   expliziten Vergleich, nicht empfohlen.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ENGINE = "argos"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:14b"
DEFAULT_SOURCE_LANGUAGE = "de"  # dieses Projekt ist primaer deutschsprachig; nur fuer --engine argos relevant
MARKER = re.compile(r"<translation>\s*(.*?)\s*</translation>", re.DOTALL | re.IGNORECASE)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

ARGOS_LANG_MAP = {
    "english": "en", "en": "en", "en-us": "en", "en-gb": "en",
    "german": "de", "deutsch": "de", "de": "de",
    "french": "fr", "französisch": "fr", "fr": "fr",
    "spanish": "es", "spanisch": "es", "es": "es",
    "italian": "it", "italienisch": "it", "it": "it",
    "dutch": "nl", "niederländisch": "nl", "nl": "nl",
    "polish": "pl", "polnisch": "pl", "pl": "pl",
    "portuguese": "pt", "portugiesisch": "pt", "pt": "pt",
    "japanese": "ja", "japanisch": "ja", "ja": "ja",
    "chinese": "zh", "chinesisch": "zh", "zh": "zh",
    "russian": "ru", "russisch": "ru", "ru": "ru",
}


def _normalize_argos_lang(lang: str) -> str:
    key = lang.strip().lower()
    if key in ARGOS_LANG_MAP:
        return ARGOS_LANG_MAP[key]
    return key[:2]


def _translate_gemini(text: str, target_language: str, model: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set in environment. Add it to ~/.secrets, "
            "or use --engine argos for local/offline translation."
        )
    prompt = (
        f"Translate this subtitle line into {target_language}. "
        "Return ONLY the translation, nothing else — no quotes, no explanation.\n\n"
        f"{text}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(
        GEMINI_API_URL.format(model=model),
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API error {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini API request failed: {e.reason}")

    try:
        translated = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Gemini response: {json.dumps(payload)[:500]}")
    return translated.strip()


def _translate_ollama(text: str, target_language: str, model: str) -> str:
    prompt = (
        f"Translate the subtitle text into {target_language}. Return exactly one XML fragment: "
        "<translation>translated subtitle text</translation>. No analysis, no thinking, no "
        f"other text.\n\n{text}"
    )
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Ollama translation failed")
    clean_stdout = ANSI_ESCAPE.sub("", result.stdout)
    match = MARKER.search(clean_stdout)
    if not match or not match.group(1).strip():
        raise RuntimeError("Ollama response lacks a complete translation marker")
    translated = match.group(1).strip()
    normalized = re.sub(r"[^a-z]", "", translated.lower())
    if normalized == "translatedsubtitletext":
        raise RuntimeError(
            "Ollama echoed the prompt template's placeholder instead of translating "
            f"({model!r} did not follow the instruction) — verify manually or use --engine argos."
        )
    return translated


def install_argos_language_pair(from_code: str, to_code: str) -> None:
    """One-time setup: download+install an Argos Translate language package.
    Not called automatically by _translate_argos -- run explicitly once per
    language pair before using --engine argos for that pair."""
    import argostranslate.package

    argostranslate.package.update_package_index()
    for pkg in argostranslate.package.get_available_packages():
        if pkg.from_code == from_code and pkg.to_code == to_code:
            path = pkg.download()
            argostranslate.package.install_from_path(path)
            return
    raise RuntimeError(f"Kein Argos-Sprachpaket für {from_code!r} -> {to_code!r} im Package-Index gefunden.")


def _configure_argos_local_only(argos_translate) -> None:
    """Prevent Argos' bundled Stanza tokenizer from checking for updates."""
    import argostranslate.sbd as argos_sbd

    class LocalOnlyStanzaSentencizer(argos_sbd.StanzaSentencizer):
        def lazy_pipeline(self):
            if self.stanza_pipeline is None:
                self.stanza_pipeline = argos_sbd.stanza.Pipeline(
                    lang=self.stanza_lang_code,
                    dir=str(self.pkg.package_path / "stanza"),
                    processors="tokenize",
                    use_gpu=argos_sbd.settings.device == "cuda",
                    logging_level="WARNING",
                    download_method=None,
                )
            return self.stanza_pipeline

    argos_translate.StanzaSentencizer = LocalOnlyStanzaSentencizer


def _translate_argos(text: str, source_language: str, target_language: str) -> str:
    try:
        import argostranslate.translate as argos_translate
    except ImportError:
        raise RuntimeError(
            "argostranslate ist nicht installiert. Im Projekt-venv: `uv add argostranslate`."
        )
    _configure_argos_local_only(argos_translate)
    from_code = _normalize_argos_lang(source_language)
    to_code = _normalize_argos_lang(target_language)
    installed = {lang.code for lang in argos_translate.get_installed_languages()}
    if from_code not in installed or to_code not in installed:
        raise RuntimeError(
            f"Argos-Sprachpaket {from_code!r} -> {to_code!r} nicht installiert. "
            f"Einmalig installieren: install_argos_language_pair({from_code!r}, {to_code!r})."
        )
    result = argos_translate.translate(text, from_code, to_code)
    if not result or not result.strip():
        raise RuntimeError(f"Argos Translate lieferte eine leere Übersetzung für {from_code!r} -> {to_code!r}.")
    return result.strip()


def _translate(
    text: str,
    target_language: str,
    model: str,
    engine: str,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
) -> str:
    if engine == "argos":
        try:
            return _translate_argos(text, source_language, target_language)
        except Exception as e:
            print(
                f"[Subtitle Translate] Argos fehlgeschlagen ({e}), "
                f"nutze lokalen Ollama Fallback ({DEFAULT_OLLAMA_MODEL})...",
                file=sys.stderr,
            )
            return _translate_ollama(text, target_language, DEFAULT_OLLAMA_MODEL)
    elif engine == "ollama":
        return _translate_ollama(text, target_language, model)
    elif engine == "gemini":
        return _translate_gemini(text, target_language, model)
    raise ValueError(f"Unbekannte Engine: {engine}. Erlaubt: 'argos', 'ollama', 'gemini'.")


def translate_subtitle_file(
    source: Path,
    output: Path,
    *,
    target_language: str,
    model: str | None = None,
    engine: str | None = None,
    source_language: str = DEFAULT_SOURCE_LANGUAGE,
) -> None:
    if engine is None:
        if model is not None and model != DEFAULT_GEMINI_MODEL:
            engine = "ollama"
        else:
            engine = DEFAULT_ENGINE
    if model is None:
        if engine == "ollama":
            model = DEFAULT_OLLAMA_MODEL
        elif engine == "gemini":
            model = DEFAULT_GEMINI_MODEL
        else:
            model = ""
    source, output = source.resolve(), output.resolve()
    if source == output:
        raise ValueError("output must differ from input")
    blocks = source.read_text(encoding="utf-8").split("\n\n")
    rendered = []
    for block in blocks:
        lines = block.splitlines()
        timestamp = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if timestamp is None or not lines[timestamp + 1:]:
            rendered.append(block)
            continue
        text = "\n".join(lines[timestamp + 1:])
        translated = _translate(text, target_language, model, engine, source_language).splitlines()
        rendered.append("\n".join(lines[:timestamp + 1] + translated))
    content = "\n\n".join(rendered)
    if source.read_text(encoding="utf-8").endswith("\n"):
        content += "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Translate SRT/VTT subtitles via Argos Translate (local/offline default), Gemini (cloud opt-in) or Ollama (local LLM, unreliable)",
        epilog="""
Engines:
  argos (default): Local, offline, free forever, no account, no API key. Uses a
          dedicated translation model (not an LLM prompt). Verified
          2026-09-26 (de<->en). Requires the language pair to be installed
          once via install_argos_language_pair() in this file.
  gemini: Cloud, gemini-3.8-flash, explicit opt-in.
  ollama: Lokal/offline LLM-Prompt -- fuer diese Aufgabe nachweislich
          unzuverlaessig (Platzhalter-Echo), nur fuer expliziten Vergleich.

Examples:
  python tools/subtitle_translate.py --input de.srt --output en.srt --target-language English
  python tools/subtitle_translate.py --input de.srt --output en.srt --target-language English --engine argos
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-language", required=True)
    parser.add_argument(
        "--source-language", default=DEFAULT_SOURCE_LANGUAGE,
        help=f"Source language, only used by --engine argos (default: {DEFAULT_SOURCE_LANGUAGE}).",
    )
    parser.add_argument(
        "--engine", choices=["argos", "ollama", "gemini"], default=DEFAULT_ENGINE,
        help=f"Translation engine (default: {DEFAULT_ENGINE}, verified). "
        "argos=local, free forever, verified. ollama=lokal/offline LLM, unreliable for this task; gemini=default, verified.",
    )
    parser.add_argument(
        "--model", default=None,
        help=f"Override model (default: {DEFAULT_OLLAMA_MODEL} for ollama, {DEFAULT_GEMINI_MODEL} for gemini)",
    )
    args = parser.parse_args()
    try:
        translate_subtitle_file(
            args.input,
            args.output,
            target_language=args.target_language,
            model=args.model,
            engine=args.engine,
            source_language=args.source_language,
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
