#!/usr/bin/env python3
"""
Voice-to-Action Pipeline (Ramble-to-Structured-Output Engine).

Transforms unstructured audio memos, voice recordings, or rambles into:
1. Structured dev/agent tickets (--mode task)
2. High-impact social media posts (--mode post)
3. Polished executive memos (--mode memo)

Uses local mlx-whisper (0 € cost, Apple Silicon optimized).

Usage:
    python tools/voice_to_action.py --input memo.m4a --mode task
    python tools/voice_to_action.py --input thought.mp3 --mode post
    python tools/voice_to_action.py --input audio.wav --mode memo --output ticket.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
VENV_PYTHON = TOOLS_DIR.parent / ".venv" / "bin" / "python"
TRANSCRIBE_SCRIPT = TOOLS_DIR / "transcribe.py"


def transcribe_audio(audio_path: Path, language: str = "de") -> str:
    """Run local transcribe.py to get raw text."""
    python_bin = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    cmd = [
        str(python_bin),
        str(TRANSCRIBE_SCRIPT),
        "--input", str(audio_path),
        "--language", language,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def format_as_task(raw_text: str) -> str:
    """Format rambling transcription into a structured Hannibal ticket."""
    return f"""# TICKET: Voice Action Item

- **Erstellt aus Sprachmemo:** {raw_text[:80]}...
- **Rolle:** Primary Executor (Antigravity / Codex)
- **Effort:** Medium

## Ziel
Präzise Ausführung der im Audiomemo beschriebenen Kernanforderung.

## Transkribierter Originaltext
> "{raw_text}"

## Extrahierte Aufgaben & Akzeptanzkriterien
- [ ] Kernaussage analysieren und Kernbefund isolieren.
- [ ] Relevante Dateien im Projekt identifizieren und prüfen.
- [ ] Konkrete Änderungen umsetzen.
- [ ] Verifikation durchführen und Status dokumentieren.
"""


def format_as_post(raw_text: str) -> str:
    """Format transcription into a LinkedIn / Social Media post draft."""
    return f"""# SOCIAL POST ENTWURF (aus Sprachmemo)

### Hook-Optionen:
1. Warum die meisten [Thema] komplett falsch angehen (und was wirklich funktioniert):
2. Ich habe mir eine Sprachnotiz gemacht – und genau das ist der größte Hebel:

---

### Post-Body:
{raw_text}

---

### Call-to-Action (CTA):
Wie handhabt ihr das aktuell in eurer Praxis? Schreibt eure Erfahrungen in die Kommentare.

#KI #Automation #BusinessGrowth #Produktivität
"""


def format_as_memo(raw_text: str) -> str:
    """Format transcription into an executive memo."""
    return f"""# EXECUTIVE MEMO

- **Datum:** Automatisch generiert
- **Status:** Entwurf / Review

## Zusammenfassung
{raw_text}

## Nächste Schritte
1. Freigabe der Kernpunkte durch die Leitung.
2. Delegation an zuständigen Agenten / Spezialisten.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform raw voice rambles into actionable tickets, posts, or memos.")
    parser.add_argument("--input", "-i", required=True, type=Path, help="Audio file (.m4a, .mp3, .wav)")
    parser.add_argument("--mode", "-m", choices=["task", "post", "memo"], default="task", help="Output format")
    parser.add_argument("--language", "-l", default="de", help="Audio language (default: de)")
    parser.add_argument("--output", "-o", type=Path, help="Optional output markdown file")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Error: Input file {args.input} does not exist.")

    print(f"Transcribing {args.input.name} via local Whisper...", file=sys.stderr)
    transcript = transcribe_audio(args.input, args.language)

    if not transcript:
        sys.exit("Error: No speech detected in audio.")

    if args.mode == "task":
        formatted = format_as_task(transcript)
    elif args.mode == "post":
        formatted = format_as_post(transcript)
    else:
        formatted = format_as_memo(transcript)

    if args.output:
        args.output.write_text(formatted, encoding="utf-8")
        print(f"Result written to {args.output}")
    else:
        print(formatted)


if __name__ == "__main__":
    main()
