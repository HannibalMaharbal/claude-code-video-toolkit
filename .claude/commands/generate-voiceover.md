---
description: Voiceover mit lokalen Stimmen oder ausdrücklich bestätigtem Azure Arabic TTS
---

# Lokales Voiceover

Standard ist Kokoro (lokal, ohne API-Key). Piper ist ebenfalls lokal. Qwen3-TTS
Voice Cloning benötigt das optionale Extra und ein vollständig eingerichtetes
lokales Modell:

```bash
uv run tools/voiceover.py --script SCRIPT.md --output voiceover.wav
uv run tools/voiceover.py --provider piper --script SCRIPT.md --output voiceover.wav
uv run --extra local-voice tools/local_voice.py --setup
```

Generiere Szenen einzeln, wenn der Schnitt pro Szene gesteuert wird:

```bash
uv run tools/voiceover.py --scene-dir public/audio/scenes --provider kokoro --json
```

Für Klonen die lokale Referenzaufnahme und das exakte Transkript erfragen.
Vor der Verarbeitung muss der Nutzer Rechte und Einwilligung zur Verwendung
der Stimme bestätigen. Ohne Bestätigung abbrechen. Es gibt keinen automatischen
Cloud-Fallback. Vorhandene Dateien nicht überschreiben.

Für arabische Dialekte ist Azure Speech optional und wird nie automatisch
verwendet. Unterstützt werden Tunesisch (`ar-TN`), Algerisch (`ar-DZ`),
Marokkanisch (`ar-MA`), Libanesisch (`ar-LB`), Syrisch (`ar-SY`) und Ägyptisch
(`ar-EG`). Azure führt keine eigene MSA-Locale; `ar-msa` verwendet ausdrücklich
eine Saudi-Stimme als Annäherung. `AZURE_SPEECH_KEY` und `AZURE_SPEECH_REGION`
müssen gesetzt sein. Jeder Live-Aufruf braucht `--confirm-cloud`, weil der
Skripttext an Microsoft gesendet wird und Nutzung jenseits des kostenlosen
Kontingents Kosten verursachen kann.

```bash
uv run tools/voiceover.py --provider azure --azure-locale ar-TN \
  --azure-gender female --confirm-cloud --script SCRIPT.md --output voiceover.mp3
```
