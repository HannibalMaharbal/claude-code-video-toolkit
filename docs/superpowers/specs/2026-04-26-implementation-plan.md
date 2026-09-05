# Implementierungsplan — Hybrid Video Orchestrator
**Datum:** 2026-04-26
**Status:** In Bearbeitung
**Ref:** 2026-04-26-hybrid-video-orchestrator-design.md

---

## Was bereits existiert ✅

| Komponente | Pfad | Status |
|-----------|------|--------|
| Voiceover (Kokoro/ElevenLabs/Qwen3) | `tools/voiceover.py` | ✅ |
| Musik (ACE-Step/Modal) | `tools/music_gen.py` | ✅ |
| Bilder (Flux2) | `tools/flux2.py` | ✅ |
| B-Roll Video (LTX2) | `tools/ltx2.py` | ✅ |
| Audio+Video merge | `tools/addmusic.py` | ✅ |
| Remotion Rendering | Templates | ✅ |
| Brand-Struktur | `brands/default/` | ✅ (nur default) |
| `/video` Command | `.claude/commands/video.md` | ✅ |

---

## Was gebaut werden muss

### Phase 1 — Core Pipeline (heute)

**1.1 Brand-Profile** (30 min)
- `brands/sac/brand.json` + `brands/sac/voice.json`
- `brands/licbarska/brand.json` + `brands/licbarska/voice.json`

**1.2 `tools/input_parser.py`** (45 min)
- Input-Typ erkennen: `topic | script_file | url`
- Bei `url`: Playwright scrape → Text
- Bei `topic`: Claude API → Script generieren
- Bei `script_file`: Direkt lesen + validieren
- Output: `ParsedInput` dataclass

**1.3 `tools/scene_splitter.py`** (30 min)
- Script → Liste von `Scene` objects
- Scene-Typen: `title | voiceover | code | visual | cta`
- Brand-Kontext pro Szene
- Output: `List[Scene]` als JSON

**1.4 `tools/orchestrator.py`** (90 min)
- CLI: `python tools/orchestrator.py "topic" [--brand sac] [--premium] [--duration 60]`
- Pipeline: input_parser → scene_splitter → parallel assets → compose
- Parallele Asset-Generierung via `asyncio`
- ffmpeg final merge
- Output: `output/[titel]-[datum].mp4`

### Phase 2 — Hermes Integration (morgen)

**2.1 Hermes Skill `video.md`**
- Erkennt `hermes video [...]`
- Ruft `orchestrator.py` auf
- Zeigt Fortschritt
- Meldet fertiges MP4

**2.2 Routing-Test**
- Einfach: `hermes video "SAC kurz"` → lokal
- Komplex: `hermes video "https://sac-online-world.de"` → Claude Code

### Phase 3 — Claude Code Hooks (übermorgen)

**3.1 Post-Task Notification**
- Hook: wenn Render fertig → `osascript` Notification

**3.2 Permission allow-list**
- `python3 tools/orchestrator.py` auto-approve
- `ffmpeg` auto-approve

### Phase 4 — Tests (Ende Woche)

| Test | Input | Erwartung |
|------|-------|----------|
| Topic-Test | `"SAC Produktvideo"` | MP4 < 5 min |
| URL-Test | `"https://sac-online-world.de"` | MP4 < 10 min |
| Script-Test | `--script test.md` | MP4 < 5 min |
| Brand SAC | `--brand sac` | Dark #0F1923 theme |
| Brand Licbarska | `--brand licbarska` | Navy #0A1628 + Gold |
| Premium | `--premium` | ElevenLabs Voice |

---

## Dateibaum (nach Phase 1)

```
tools/
├── orchestrator.py      ← NEU: Haupt-CLI
├── input_parser.py      ← NEU: Input-Erkennung
├── scene_splitter.py    ← NEU: Script → Szenen
├── voiceover.py         ← existiert
├── music_gen.py         ← existiert
├── flux2.py             ← existiert
└── ...

brands/
├── sac/                 ← NEU
│   ├── brand.json
│   └── voice.json
├── licbarska/           ← NEU
│   ├── brand.json
│   └── voice.json
└── default/             ← existiert
```

---

## Jetzt starten: Phase 1.1 → 1.4
