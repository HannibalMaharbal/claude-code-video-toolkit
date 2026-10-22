---
description: Lokales Dubbing mit Qwen3-TTS, MLX Whisper und Argos
---

# Lokales Dubbing

Verarbeitet Video, Transkript, Übersetzung und synthetische Sprache lokal.
Das Qwen3-TTS-Modell (ca. 2,5 GB) muss einmalig bewusst eingerichtet werden:

```bash
uv run --extra local-voice tools/local_voice.py --setup
```

Vor dem Start lokale Video- und Referenzpfade erfragen. Dubbing nutzt die
Referenzstimme und verlangt die ausdrückliche Bestätigung, dass der Nutzer die
Rechte und Einwilligung zur Verwendung dieser Stimme besitzt. Ohne Bestätigung
nicht ausführen. Das Ergebnis ersetzt die ursprüngliche Tonspur; Musik und
Raumklang werden nicht separat erhalten.

```bash
uv run --extra local-voice tools/redub.py \\
  --input "INPUT.mp4" \\
  --ref-audio "REFERENCE.wav" \\
  --ref-text "EXACT TRANSCRIPT OF THE REFERENCE" \\
  --source-language en \\
  --target-language de \\
  --output "OUTPUT.mp4" \\
  --consent-confirmed
```

Es gibt keinen Cloud-Fallback und keine Übertragung externer Dateien.
