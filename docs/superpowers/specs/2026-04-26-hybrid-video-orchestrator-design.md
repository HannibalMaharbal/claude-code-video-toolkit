# Hybrid Video Orchestrator — Design Spec
**Datum:** 2026-04-26
**Status:** Approved
**Autor:** Hannibal

---

## Ziel

Ein einziger Befehl (`hermes video`) generiert vollautomatisch ein fertiges MP4 — aus Thema, Text oder URL. Unterstützt Coding-Tutorials (kostenlos) und Marketing-Videos (Premium optional).

---

## Architektur

```
Input (Thema | Text | URL)
    ↓
[1. Input Parser]
    - Typ erkennen: topic / script / url
    - Bei URL: playwright scrape → Text
    - Script generieren via Claude Code (komplex) oder Hermes/gemma4:e4b (einfach)
    ↓
[2. Scene Splitter]
    - Szenen klassifizieren: code | visual | voiceover | cta | title
    - Brand auswählen: sac | licbarska | default
    ↓
[3. Asset Generator — parallel]
    ├── Flux2 (Modal)       → Backgrounds, Thumbnails, Scene-Images
    ├── LTX2 (Modal)        → B-Roll Video-Clips
    ├── Qwen3-TTS (Modal)   → Voiceover MP3 [kostenlos]
    ├── ElevenLabs          → Voiceover MP3 [--premium, Marketing]
    ├── music_gen (Modal)   → Hintergrundmusik [kostenlos]
    └── ElevenLabs Music    → Hintergrundmusik [--premium, Marketing]
    ↓
[4. Renderer]
    ├── Code/Text-Szenen    → Remotion (React)
    └── Visual-Szenen       → ffmpeg compose
    ↓
[5. Composer]
    └── ffmpeg merge → output/[titel]-[datum].mp4
```

---

## CLI Interface

```bash
# Thema
hermes video "SAC Produktvideo Sommer 2026"
hermes video "React Hooks Tutorial für Anfänger"

# URL
hermes video "https://sac-online-world.de"
hermes video "https://licbarska-immobilien.de"

# Script-Datei
hermes video --script mein-script.md

# Brand + Qualität
hermes video "SAC Kampagne" --brand sac --premium
hermes video "Licbarska Intro" --brand licbarska --premium

# Optionen
hermes video "..." --duration 60     # Ziel-Länge in Sekunden
hermes video "..." --no-music        # Ohne Musik
hermes video "..." --no-voiceover    # Nur Text-Einblendungen
hermes video "..." --output ./out/   # Ausgabeordner
```

---

## Brand-Profile

### SAC Online World
- **Farben:** #0F1923 (bg), #4A90D9 (akzent), #FFFFFF (text)
- **Font:** Barlow Condensed
- **Stil:** Dark, technisch, B2B, präzise

### Licbarska (Consult + Immobilien)
- **Farben:** #0A1628 (navy), #C9A96E (gold), #F5F0E8 (cream)
- **Font:** Cormorant Garamond (headlines), Montserrat (body)
- **Stil:** Premium, seriös, vertrauenswürdig

---

## Tool-Konfiguration

### Kostenlos (Standard)
| Funktion | Tool | Endpoint |
|----------|------|---------|
| Bilder | Flux2 | `MODAL_FLUX2_ENDPOINT_URL` |
| B-Roll Video | LTX2 | `MODAL_LTX2_ENDPOINT_URL` |
| Voiceover | Qwen3-TTS | `MODAL_QWEN3_TTS_ENDPOINT_URL` |
| Musik | music_gen | `MODAL_MUSIC_GEN_ENDPOINT_URL` |
| Rendering | Remotion | lokal |
| Composition | ffmpeg | lokal |

### Premium (--premium Flag)
| Funktion | Tool | Kosten |
|----------|------|--------|
| Voiceover | ElevenLabs | ~$0.30/1k Zeichen |
| Musik | ElevenLabs Music | ~$0.50/min |

---

## Hermes Integration

### Hermes Skill: `video`
Hermes erkennt `hermes video [...]` und:
1. Ruft den Orchestrator-Script auf
2. Zeigt Fortschritt (Scene 1/5... Asset Generation... Rendering...)
3. Meldet fertiges MP4

### Modell-Routing in Hermes
- Script-Generierung (einfach) → `qwen3.5`
- Script-Generierung (komplex/multi-file) → delegiert an Claude Code
- Asset-Ops (lokal) → `gemma4:e4b`

---

## Implementierungsschritte (Übersicht)

### Phase 1 — Video-Toolkit (Woche 1)
1. `orchestrator.py` — Haupt-Pipeline-Script
2. `input_parser.py` — Thema/Text/URL erkennen
3. `scene_splitter.py` — Szenen klassifizieren
4. `brand_config.py` — SAC + Licbarska Profile
5. `composer.py` — ffmpeg merge wrapper

### Phase 2 — Hermes Integration (Woche 1-2)
1. Hermes Skill `video.md` schreiben
2. SOUL.md bereits optimiert ✅
3. config.yaml reasoning_effort bereits auf `high` ✅
4. CLI-Routing testen

### Phase 3 — Claude Code Hooks (Woche 2)
1. Post-Task Notification Hook
2. python3-Tools auto-approve Permission
3. Video-Toolkit Skills in Claude Code registrieren

### Phase 4 — Gesamtintegration + Tests (Woche 2-3)
1. End-to-End Test: Thema → MP4
2. End-to-End Test: URL → MP4
3. End-to-End Test: Script → MP4
4. Brand-Tests: SAC + Licbarska
5. Premium-Pfad testen

---

## Erfolgskriterien

- [ ] `hermes video "SAC Produktvideo"` → MP4 in < 5 Minuten
- [ ] `hermes video "https://sac-online-world.de"` → MP4 in < 10 Minuten
- [ ] Kostenlos-Pfad: $0 (nur Modal Free Tier)
- [ ] Premium-Pfad: < €5 pro Video
- [ ] Beide Brands korrekt dargestellt
- [ ] Coding-Tutorial-Pfad: Code-Szenen via Remotion
- [ ] Marketing-Pfad: LTX2 B-Roll + ElevenLabs

---

## Bereits erledigt ✅
- Hermes SOUL.md optimiert
- Hermes config.yaml `reasoning_effort: high`
- Modal Endpoints deployed (Flux2, LTX2, TTS, music_gen)
- Video-Toolkit installiert (`~/claude-code-video-toolkit/`)
- Brand-Farben dokumentiert
