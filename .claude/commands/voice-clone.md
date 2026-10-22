---
description: Lokales Qwen3-TTS Voice Cloning mit ausdrücklicher Einwilligung
---

# Lokales Voice Cloning

Das kostenlose Modell braucht rund 2,5 GB Plattenplatz und wird nur auf
ausdrücklichen Wunsch eingerichtet:

```bash
uv run --extra local-voice tools/local_voice.py --setup
```

Frage nach einer lokalen Referenzaufnahme und deren exaktem Transkript. Kläre,
dass die Stimme der anfragenden Person gehört oder eine ausdrückliche
Einwilligung und die nötigen Nutzungsrechte vorliegen. Ohne diese Bestätigung
keine Aufnahme verarbeiten. Dateien bleiben lokal.

```bash
uv run --extra local-voice tools/local_voice.py \\
  --text "Hallo, dies ist ein kurzer Stimmtest." \\
  --ref-audio "REFERENCE.wav" \\
  --ref-text "EXACT REFERENCE TRANSCRIPT" \\
  --language German \\
  --output "voice-test.wav" \\
  --consent-confirmed
```

Vorhandene Ausgabedateien werden nicht überschrieben. Es gibt keinen
Cloud-Fallback.
