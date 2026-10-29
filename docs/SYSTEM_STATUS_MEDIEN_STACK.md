# HANNIBAL AI OS — Status & Audit: Medien- & Video-Stack

**Stand:** 28. Oktober 2026
**Auditor / Schreiber:** Antigravity CLI (`agy`)
**Status:** Vollständig einsatzbereit (100 % betriebsbereit)

---

## 1. Übersicht & Architektur

Das HANNIBAL AI OS verfolgt für Video- und Audioproduktion eine strikte **Lokal-First- & Zero-Bloat-Strategie**:
1. **Stufe 1 (Lokal, 0 € Grenzkosten):** Generierung mit LTX-2.5 MLX auf Apple Silicon (M4 Pro / 24 GB) + hardwarebeschleunigtes VideoToolbox Lanczos-3 CAS-Schärfen.
2. **Stufe 2 (Cloud Fallback, Pay-per-Use):** Higgsfield CLI-Aggregator (`seedance_2_5`, `minimax_h3`, `wan3_0`, `kling3_0`, `veo3`, `topaz`). Kein monatliches Abo, rein bedarfsgesteuertes Guthaben mit vorgeschaltetem Kosten-Gate.

---

## 2. Komponenten-Audit (Live verifiziert)

| Komponente | Pfad / Tool | Status | Funktion |
| :--- | :--- | :--- | :--- |
| **Lokale Video-Engine** | `tools/ltx25_mlx_adapter.py` | ✅ Aktiv | LTX-2.5 MLX (Distilled Q8, 24 fps, M4 Pro Sweet Spot) |
| **Cloud Video-Aggregator** | `/usr/local/bin/higgsfield` | ✅ Aktiv | Higgsfield CLI (Kontostatus zum Prüfzeitpunkt) |
| **Cloud Video-Wrapper** | `tools/higgsfield_video.py` | ✅ Aktiv | Kosten-Gate, Balancencheck, automatischer Download |
| **Hardware-Finishing** | `/opt/homebrew/bin/ffmpeg` (v9.0.2) | ✅ Aktiv | Apple VideoToolbox (Lanczos-3 CAS, H.264/HEVC Hardware) |
| **Transkription & Audio** | `~/.local/bin/whisper` | ✅ Aktiv | Lokales Whisper (0 € Transkription & SRT-Erzeugung) |
| **TTS & Stimmen** | Gemini 3.8 Flash TTS | ✅ Aktiv | Broadcast Voiceover (`promote`, `narration`, `friendly`) |
| **Audio-Mastering** | `tools/audio_mix.py` | ✅ Aktiv | Sidechain-Ducking & Lautheitsnormierung auf **-14.0 LUFS** |
| **Programmatisches Video** | `@remotion/cli` (v4.0.526) | ✅ Aktiv | Dynamische Word-by-Word Social Captions & Overlays |
| **Desktop-Post-Production** | `/Applications/DaVinci Resolve.app` | ✅ Aktiv | Finales Finishing- & Fairlight-Mastering-Gate |
| **Social Video Editor** | `/Applications/CapCut.app` | ✅ Aktiv | Schnitt, B-Roll, Punch-in Zooms (via CapCut-Skill) |

---

## 3. Zentrale Master-Pipeline

Die Steuerung erfolgt konsolidiert über:
```bash
python3 tools/master_pipeline.py \
    --prompt "Szenenbeschreibung" \
    --provider local \
    --voice-text "Sprechertext" \
    --music assets/audio/beat.mp3 \
    --target-lufs -14.0 \
    --output out/master.mp4
```

### Eingehaltene Regie- & Qualitätsgesetze:
* **Lamborghini-Regel:** Kein räumliches Teleportieren, kein Springen. Kamera bewegt sich, Motiv & Licht bleiben konsistent.
* **End-Frame = Start-Frame Gesetz:** `--continue-from` verriegelt das exakte Endframe des vorherigen Clips pixelgenau als Startframe.
* **Kosten-Schutz:** Cloud-Aufrufe verlangen zwingend `--confirm` nach vorheriger Preisanzeige.
