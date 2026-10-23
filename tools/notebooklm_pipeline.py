#!/usr/bin/env python3
"""
HANNIBAL AI OS — NotebookLM to Video Pipeline Bridge
Connects Google NotebookLM (nlm CLI) with Hannibal's Video Production Engine.

Enforces:
1. Grounding & Zero-Hallucination (via NotebookLM sources)
2. Anti-Jump & Lamborghini Rule (Continuous scene, subject & asset lock, constant lighting)
3. Cinema & Regie Standard (Motivated camera, 35mm Bokeh, no stiff slide-cuts)
4. End-Frame = Start-Frame Rule (Continuous scene transitions)

Usage:
    uv run tools/notebooklm_pipeline.py query licbarska "Was sind die Kernvorteile der Deal-Arbitrage?"
    uv run tools/notebooklm_pipeline.py storyboard licbarska "Private Deal Arbitrage fuer Kapitalanleger" --shots 4
    uv run tools/notebooklm_pipeline.py studio licbarska report --focus "Leitfaden fuer Eigentuemer"
    uv run tools/notebooklm_pipeline.py studio licbarska quiz --focus "Wissenscheck Immobilienbewertung"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

NLM_BIN = os.path.expanduser("~/.local/bin/nlm")
if not os.path.exists(NLM_BIN):
    NLM_BIN = "nlm"

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "notebooklm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_nlm(cmd_args: list[str]) -> tuple[int, str]:
    """Execute nlm command safely."""
    full_cmd = [NLM_BIN] + cmd_args
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        output = proc.stdout if proc.stdout else proc.stderr
        return proc.returncode, output.strip()
    except Exception as e:
        return 1, str(e)


def handle_query(notebook: str, query: str):
    """Query notebook sources with zero hallucination."""
    print(f"🔍 Abfrage an NotebookLM [{notebook}]: '{query}'...")
    code, output = run_nlm(["notebook", "query", notebook, query])
    if code != 0:
        print(f"❌ Fehler bei nlm query: {output}")
        sys.exit(code)
    print("\n" + "=" * 60)
    print("ANTWORT (Quellen-gesichert):")
    print("=" * 60)
    print(output)
    print("=" * 60)
    return output


def handle_storyboard(notebook: str, topic: str, shot_count: int = 4):
    """
    Generate an actionable, cinema-grade storyboard from NotebookLM sources.
    Follows Hannibal Cinema Standards & Anti-Jump Rule.
    """
    print(f"🎬 Erstelle Storyboard für [{notebook}] zum Thema '{topic}' ({shot_count} Szenen)...")
    
    prompt = (
        f"Erstelle ein präzises Skript zum Thema '{topic}'. "
        f"Gliedere es in genau {shot_count} aufeinanderfolgende Kernaussagen (Sprechertext). "
        "Formuliere faktenbasiert, autoritär und überzeugend nach deinen Quellen. "
        "Gib für jeden Punkt 1-2 prägnante Sätze Voiceover-Text an."
    )
    
    code, raw_script = run_nlm(["notebook", "query", notebook, prompt])
    if code != 0:
        print(f"❌ Fehler beim Abrufen des Skripts: {raw_script}")
        sys.exit(code)

    # Clean JSON answer if nlm returned a JSON structure
    clean_text = raw_script
    try:
        parsed = json.loads(raw_script)
        if isinstance(parsed, dict) and "answer" in parsed:
            clean_text = parsed["answer"]
    except Exception:
        pass

    print("✓ Skript aus NotebookLM bezogen. Generiere cineastische Kamera- und Szenen-Spezifikation...")

    # Canonical camera motions according to HANNIBAL Cinema Standard
    camera_moves = [
        "Slow cinematic Dolly Push-In (35mm f/1.8 lens, shallow depth of field, subtle warm lighting)",
        "Gentle Tracking Pan right with subtle parallax (steadycam, 35mm bokeh, locked subject focus)",
        "Over-the-shoulder close-up to medium arc motion (clean architectural lighting, photorealistic textures)",
        "Slow cinematic Pull-back revealing full environment (atmospheric depth, steady crane movement)",
    ]

    shots = []
    # Split text into lines or paragraphs
    lines = [l.strip() for l in clean_text.split("\n") if l.strip() and not l.startswith("#") and not l.startswith("*")]
    chunks = [lines[i:i + max(1, len(lines) // shot_count)] for i in range(0, len(lines), max(1, len(lines) // shot_count))]

    for i in range(shot_count):
        cam = camera_moves[i % len(camera_moves)]
        vo_chunk = " ".join(chunks[i]) if i < len(chunks) else f"Kernaussage {i+1} zu {topic}."
        
        shot_entry = {
            "shot_id": i + 1,
            "duration_seconds": 5.0,
            "camera_motion": cam,
            "voiceover_text": vo_chunk,
            "continuity_rule": "End-Frame of Shot " + str(i) + " is Start-Frame of Shot " + str(i+1) if i > 0 else "Initial Keyframe Master Setup",
            "prompt_ltx_wan": (
                f"Cinematic photorealistic shot, 8k resolution, professional architectural and business aesthetic. "
                f"{cam}. "
                f"Subject and environment remain physically locked without sudden jumps. "
                f"Subtle organic motion, atmospheric light particles, elegant natural color grading."
            ),
        }
        shots.append(shot_entry)

    storyboard_data = {
        "project": f"NotebookLM_{notebook}_{re.sub(r'[^a-zA-Z0-9]', '_', topic)[:30]}",
        "notebook": notebook,
        "topic": topic,
        "standard": "HANNIBAL AI OS Cinema & Anti-Jump Standard",
        "shots_count": shot_count,
        "shots": shots,
    }

    out_file = OUTPUT_DIR / f"storyboard_{storyboard_data['project']}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(storyboard_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Storyboard erfolgreich generiert:")
    print(f"📄 Datei: {out_file}")
    print("\nÜbersicht der Szenen:")
    for shot in shots:
        print(f"  [Szene {shot['shot_id']}] {shot['camera_motion']}")
        print(f"    VO: {shot['voiceover_text'][:80]}...")
        print(f"    Kontinuität: {shot['continuity_rule']}")
    
    return str(out_file)


def handle_studio(notebook: str, artifact_type: str, focus: str | None = None):
    """Create studio artifacts (report, quiz, flashcards, mindmap, audio)."""
    valid_types = ["report", "quiz", "flashcards", "mindmap", "audio"]
    if artifact_type not in valid_types:
        print(f"❌ Ungültiger Studio-Typ '{artifact_type}'. Erlaubt: {', '.join(valid_types)}")
        sys.exit(1)

    print(f"🎨 Starte Studio-Generierung [{artifact_type}] für Notebook [{notebook}]...")
    cmd = [artifact_type, "create", notebook, "--confirm"]
    if focus:
        cmd.extend(["--focus", focus])
    
    code, output = run_nlm(cmd)
    if code != 0:
        print(f"❌ Fehler bei Studio-Generierung: {output}")
        sys.exit(code)
    
    print("\n" + "=" * 60)
    print(f"STUDIO-ARTEFAKT [{artifact_type.upper()}] ERFOLGREICH GESTARTET / ERZEUGT:")
    print("=" * 60)
    print(output)
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="NotebookLM to Video Pipeline Bridge (Hannibal AI OS)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Query command
    q_parser = subparsers.add_parser("query", help="Gefilterte Quellen-Abfrage")
    q_parser.add_argument("notebook", help="Notebook Name oder Alias (z. B. licbarska, zinzino, video)")
    q_parser.add_argument("query", help="Die Frage an die Quellen")

    # Storyboard command
    sb_parser = subparsers.add_parser("storyboard", help="Erzeugt ein cineastisches Storyboard aus Notebook-Fakten")
    sb_parser.add_argument("notebook", help="Notebook Name oder Alias")
    sb_parser.add_argument("topic", help="Das Kernthema für das Video")
    sb_parser.add_argument("--shots", type=int, default=4, help="Anzahl der Szenen (Default: 4)")

    # Studio command
    st_parser = subparsers.add_parser("studio", help="Erzeugt Studio-Artefakte (quiz, report, flashcards, mindmap, audio)")
    st_parser.add_argument("notebook", help="Notebook Name oder Alias")
    st_parser.add_argument("type", choices=["report", "quiz", "flashcards", "mindmap", "audio"], help="Artefakt-Typ")
    st_parser.add_argument("--focus", default=None, help="Optionaler Fokus-Prompt")

    args = parser.parse_args()

    if args.command == "query":
        handle_query(args.notebook, args.query)
    elif args.command == "storyboard":
        handle_storyboard(args.notebook, args.topic, args.shots)
    elif args.command == "studio":
        handle_studio(args.notebook, args.type, args.focus)


if __name__ == "__main__":
    main()
