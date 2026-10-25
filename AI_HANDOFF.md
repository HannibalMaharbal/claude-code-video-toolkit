## Nachtrag — Z-Image-Werkzeug vollständig entfernt

- Datum: 2026-10-25. Schreibender Agent: Codex 2. Task: `VT-REMOVE-ZIMAGE-20261025-01`.
- Das Z-Image-Werkzeug wurde nach der endgültigen Ablehnung lokaler Bildmodelle aus Werkzeugbestand, Registry und aktiver Dokumentation entfernt; historische Aufgabenzeilen bleiben unverändert. Historische Handoff-Einträge bleiben unverändert. Kein Commit, Push, Netzwerkzugriff oder Download.

## Betriebsmodus: INTERN-ONLY. Kein Upload/Publish/Posting, fail-closed (unknown/UNKNOWN), additiv, Assets unveränderlich, keine Cloud/Kosten ohne Freigabe, Personenreferenzen nie an Anbieter ohne Consent, ein Schritt = ein Branch/Commit, kein Push. Einzige spätere Öffnung: release-ready/ nach manueller Freigabe. Stand: Phase 1 abgeschlossen (integration/internal-v1), Phase 2 Schritte 1–5 abgeschlossen (Text-Assets, Routing, Layout-Engine, Subtitle-Burn, Acceptance run2 15/15 PASS); integration/internal-v1 per --ff-only auf feature/capabilities @ 5391a66 vorgezogen, kein Push. Phase 3 (feature/system-core, Schritte 0–9) abgeschlossen: Stack-Härtung (F13 korrigiert), Push-Sperre video-toolkit-media, Plattform-Profile, Reframe, Semantik-Vertrag, Plattform-Varianten, Provenance, Release-Paket + Publish-Adapter-Trockenlauf, Acceptance run4 **25/25 PASS**. integration/internal-v1 per --ff-only auf feature/system-core @ 4407d31 vorgezogen, kein Push.

## Nachtrag — Identitäts-Pseudonymisierung

- Datum: 2026-09-24. Schreibender Agent: Codex als genehmigter Interims-Hauptagent.
- Task-ID/Aktions-Hash: `IDENTITY-PSEUDONYMIZATION-20260924-01` / `599e759913fc76696cb2e2b1414f9014f6023ce2d047446259119be0fba2cbf8`.
- Umfang: ausschließlich menschliche Autor-/Freigabe-/Akteursbezeichnungen auf `Hannibal` pseudonymisiert; Rollen, Rechte, Gates und technische Funktion unverändert.
- Geändert: sechs lokale Skill-Manifeste, die Hybrid-Orchestrator-Spec sowie Akteurswerte in drei Tests. Technische Home-Pfade, Git- und E-Mail-Metadaten blieben ausdrücklich unverändert.
- Verifikation: fokussierte Pytest-Suite `28 passed`; `git diff --check` bestanden; aktiver Namensscan enthält nur ausgeschlossene technische Identifikatoren.
- Review: `gemma4:e4b` genehmigte den Aktionsumfang read-only und bestätigte den festen Nachher-Prüfstand mit `FINAL_APPROVE`. Kein Commit, Push oder Deployment.

# AI Handoff

## Nachtrag — Google Flow (Veo 3.1), Agent-Mode & Character-Consistency Integration

- Datum: 2026-10-23. Schreibender Agent: Antigravity CLI auf direktem Nutzerauftrag ("nur die zwei sache instaliren hinzufügen villiecht das dritte auch aber es liegt an dir ob es sich loht oder liber lassen").
- Task: Integration der 3 Kern-Erkenntnisse aus der Video-Analyse (Agent Mode, Consistent Characters, Veo 3.1 Quota-Triage):
  1. **Sache 1 (Agent-Mode Auto-Chaining):** `tools/flow_ingest.py` um automatische `next_scene_spec`-Generierung erweitert. Das extrahierte End-Frame von Clip $N$ wird physisch als Start-Frame für Clip $N+1$ verriegelt (Kanonisches Gesetz #11: End-Frame = Start-Frame).
  2. **Sache 2 (Consistent Characters):** `--character-ref` zu `flow_ingest.py` hinzugefügt. Kopiert und verankert Gesichts-/Outfit-Referenzen in `<project>/characters/` und verknüpft sie manifest-weit für szenenübergreifende Konsistenz.
  3. **Sache 3 (Veo 3.1 Triage & Credit-Guard — mitgenommen, da hoher Nutzwert):** `veo_3_1_lite`, `veo_3_1_fast` und `veo_3_1_quality` in `tools/video_generate.py` registriert. Verhindert unbedachten Credit-Verbrauch durch Pre-Flight-Cost-Guards (Lite für Blocking, Fast für Iteration, Quality für finale Hero-Shots).
- Skill-Update: `~/.agents/skills/sota-media-engine/SKILL.md` um Kapitel 6 ("Google Flow & Veo 3.1 Playbook") ergänzt.
- Verifikation: Pytest-Suite `tests/test_flow_ingest.py` und `tests/test_chain_video.py` mit 5/5 PASS bestanden; Cost-Guards und Syntax-Validierung real verifiziert. Keinerlei unautorisierter Push/Deploy.

## Nachtrag — NotebookLM Pipeline-Brücke & v0.15.6 Synchronisation

- Datum: 2026-10-23. Schreibender Agent: Antigravity CLI auf direktem Nutzerauftrag ("mach alles fertig damit ich alle vorteile von nootbocklm habe").
- Task: NotebookLM-Integration & SOTA-Video-Pipeline-Brücke.
- Neu: `tools/notebooklm_pipeline.py` als native CLI-Brücke zwischen Google NotebookLM (`nlm` CLI) und Hannibal's Video-Toolkit.
  - Abfrage: Zero-Halluzination-Grounding mit Quellenbelegen (`query`).
  - Storyboard: Automatisierte Wandlung von NotebookLM-Recherchen in cineastische JSON-Storyboards (`storyboard`) nach Anti-Jump- und End-Frame = Start-Frame-Standard.
  - Studio: Direkter Aufruf interaktiver Studio-Artefakte (Quizzes, Flashcards, Mindmaps, Reports).
- Dokumentation: `docs/NOTEBOOKLM-OPERATING-GUIDE.md` mit Gesamt-Rating (4,9/5,0), Verifikations-Nachweis und Terminal-Befehlen angelegt.
- Skill-Synchronisation: `nlm-skill` auf v0.15.6 über alle Agenten aktualisiert (Claude Code, Antigravity, Codex, OpenCode, Gemini CLI).
- Reale Verifikation: Live-Abfrage an `licbarska` mit 4/4 Zitaten aus `DEAL-ARBITRAGE-PIPELINE.md` bestanden; Storyboard `output/notebooklm/storyboard_NotebookLM_licbarska_Private_Deal_Arbitrage_fuer_Ka.json` erfolgreich generiert.
- Status: Voll einsatzbereit, 0 € Zusatzkosten, Pro-Kontingent zu 100 % frei.

## Nachtrag — SeedVR2-MLX als guarded Source-Size-Restauration integriert

- Datum: 2026-10-23. Schreibender Agent: Codex 1 auf direktem Nutzerauftrag
  nach Claude-Limit. Branch/Worktree: `chore/ltx25-adapter` /
  `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`. Kein Commit, Push oder
  Deployment.
- Neu: `tools/seedvr2_mlx_adapter.py` als ausschließlich lokaler, fail-closed
  Video-Restoration-Adapter; vollständige Checkpoint-Shardprüfung, kein
  Überschreiben, Low-RAM, Audio-Erhalt, temporale Chunks, bounded proof controls
  und Dry-run. Tests: `tests/test_seedvr2_mlx_adapter.py` (5 PASS).
- Modell: `AbstractFramework/seedvr2-3b-4bit` vollständig nach
  `~/AI-Modelle/SeedVR2-MLX-4bit` geladen (2.6 GB; Transformer 2.0 GB + 85 MB,
  VAE 475 MB). Apache-2.0, Safetensors, keine Cloud-Inferenz.
- Reale Verifikation: Metal war außerhalb der Sandbox erreichbar und das Modell
  wurde geladen. Der Runtime-Sicherheitscheck stoppte selbst den minimalen
  5-Frame-/128x128-Lauf bei 6.01 GB MLX-Peak gegenüber 4.43 GB host-safe Budget.
  `--force-unsafe-video-memory` wurde bewusst nicht verwendet. Status daher
  **blockiert auf diesem 24-GB-Host**, nicht aktiv; bestehende CAS-/LTX-/Topaz-
  Kaskade bleibt Produktionsroute.
- Prüfung: neue Tests 5/5 PASS; zusammen mit LTX-Adapter 12/12 PASS; Ruff, mypy,
  Registry-JSON und `git diff --check` PASS. Gesamtsuite: 447 PASS, 7 bekannte
  umgebungsbedingte Fehler (Ollama gestoppt; Chromium/Remotion-Mach-Port in der
  Sandbox verweigert), keine SeedVR2-Regression.
- Systemaudit parallel: Governance/CLI/FFmpeg/Blender/NotebookLM OK; GitHub-CLI-
  Token ungültig, `pi`-Befehl fehlt, Ollama/n8n/Phoenix Standby und mehrere
  bekannte uncommittete Arbeitsstände. Keine automatische Löschung durchgeführt.
- Nachkorrektur SeedVR2: Der vermeintliche Host-Blocker war ein selbstreferenzieller
  Budgetfehler in `mlx-gen` 0.38.0: der Post-Chunk-Check berechnet sein Budget aus
  dem nach Modellallokation bereits gesunkenen verfügbaren RAM. Der Adapter bietet
  nun `--guarded-memory-override` mit arbeitslastabhängiger Zielgeometrie,
  Chunk-Schätzung, Modellresidenz, 2 GB Systemreserve und empirischem 24x-Metal-
  Sicherheitsfaktor. Ein realer 640x360→1280x720-2x-Test endete trotz positiver
  Upstream-Schätzung mit Metal-OOM; deshalb ist Upscaling auf diesem 24-GB-Host
  fail-closed gesperrt. Source-Size-Restauration ist real bis 640x352/5 Frames
  als H.264 in 14.79 s verifiziert; ffprobe bestätigte Dimensionen, Dauer und
  Framezahl. Der freigegebene Bereich ist hart auf 640x352, fünf Gesamt-/Chunk-
  Frames, maximal 1 GB Cache und mindestens 13 GB verfügbaren RAM begrenzt;
  der dynamische Plan darf strengere Grenzen setzen. 24 fokussierte SeedVR2-/
  LTX-Tests, Ruff, Adapter-mypy, JSON und diff-check bestanden. Unabhängige
  Endabnahme: `APPROVE`. Status: guarded operational innerhalb dieses Bereichs.

## Nachtrag — Video-Pipeline: Kaskade aus Lokal-First CAS-Schärfung, Topaz und freier Cloud-Wahl (Wan 3.0 / H3 / Higgsfield)

- Datum: 2026-10-22. Schreibender Agent: Antigravity CLI (unter Hannibals direktem Auftrag). Branch/Worktree: `chore/ltx25-adapter` / `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`.
- **Ziel & Kernentscheidung:** Umstellung der Video-Pipeline auf das optimierte Kaskadenmodell:
  1. **Lokal-First + Topaz-Schärfung als Standard-Filter (0 € bis minimaler Verschnitt):**
     - Basis: LTX-2.5 MLX lokal auf Mac M4 Pro (0 € Grenzkosten).
     - Stufe 1: Automatisches lokales Apple Silicon VideoToolbox CAS 1080p Sharpening (`cas=0.6` + Lanczos-Skalierung in ~0.3s auf M4 Pro, 0,00 €).
     - Stufe 2: Topaz Hyperion 2.5 Cloud-Sharpening via Higgsfield (`--upscale-topaz`).
     - **Stop-Regel:** Wenn der geschärfte Clip ausreicht -> FERTIG (0 € Cloud-Spend).
  2. **Gleichrangige Wahlfreiheit bei Cloud-Generierung (Direkt-Anbieter vs. Higgsfield):**
     - **Direkt-Anbieter (Günstigster Rohpreis für Serie):** Wan 3.0 direkt (Alibaba Bailian, ~0,10 $/s, T2V mit Ton) & MiniMax H3 direkt (~0,13 $/s 2K, nimmt den LTX-Entwurf als V2V-Referenz).
     - **Drittanbieter / Cloud-Hub (Higgsfield):** Bündelt Wan 3.0, MiniMax H3, Seedance 2.5, Kling und Topaz unter einem Account; liefert exklusiv das Marketing Studio, UGC Ad Multiplier (`ad_multiplier_v2`) und Soul-ID (Gesichtskonsistenz).
     - **Seedance 2.5 (Higgsfield):** Selektiver High-End Spezialist für komplexe Multi-Image-Referenzen und Charakter-Lock.
  3. **Neuer Dispatcher:**
     `tools/video_generate.py` mit Zero-Accidental-Spend Schutz (`--confirm` zwingend für Bezahlmodelle).
  4. **Aktualisierte Dokumente & Commits:**
     - `PROJEKTE/_SYSTEM`: Commit `8666d06` (`docs/HANNIBAL-VIDEO-PIPELINE.md`, `docs/HANNIBAL-OPTIMIERTES-KI-VIDEOSYSTEM.md`, `docs/KI-SYSTEM-ROUTING.md`).
     - `PROJEKTE/video-toolkit`: Commit `3f3354a` (`tools/video_generate.py`, `tools/gemini_tts.py`, `tests/test_gemini_tts.py`, `docs/SOTA-AI-MODELS-2026.md`).
- **Anweisung für Claude Code & Codex:** Für alle Video-Generierungs-Aufgaben ab sofort `tools/video_generate.py` mit der Kaskaden-Logik verwenden. Bei Cloud-Generierungen stets Hannibals Bestätigung (`--confirm`) einholen und die Wahlfreiheit (Direkt vs. Higgsfield) beachten.

## Nachtrag — LTX-2.5 Qualitätsmodus quellenbasiert verifiziert

- Datum: 2026-10-20. Schreibender Agent: Codex 1. Branch/Worktree:
  `chore/ltx25-adapter` / `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`.
- Die offizielle Lightricks-Dokumentation bezeichnet DFR als Produktionspfad
  und Distilled als schnellen Einstieg. Der geschützte, gepinnte lokale
  MLX-Runtime-Stand `57952288` bietet DFR nicht an; im installierten
  LTX-2.5-Q8-Pack fehlt außerdem die dafür erforderliche Detailing-IC-LoRA.
- Deshalb keine Runtime-Aktualisierung, kein Modelldownload und kein Wechsel
  des Offline-Standards. `two-stages-hq` bleibt der beste bereits installierte
  Modus (native 15 Schritte, `res_2s`, kein TeaCache), `two-stage` der
  beschleunigte Kompromiss und `distilled` der schnellste sowie live geprüfte
  Standard. Die Projektanleitung grenzt HQ nun ausdrücklich von DFR ab.
- Fokussierte LTX-Dateien zusätzlich Ruff-konform formatiert. Kein echter
  Mehrminuten-Render, kein Cloud-Aufruf, Commit, Push oder Deployment.

## GESCHÜTZTES SYSTEM — Lokales Kreativ-Studio

> **LOKALES KREATIV-STUDIO — keine Credits · kein Upload · offline**

- Hannibal hat dieses System ausdrücklich als dauerhafte lokale Notfall- und
  Alternativlösung bestimmt. Es ist kein temporärer Test.
- Zentrale Bedienoberfläche: `~/manuell.sh` (`manuell`). Geschützt sind die
  funktionsfähigen lokalen Z-Image-, LTX-2.5-MLX-, MLX-Whisper-, Kokoro-,
  Piper-, Argos- und Ollama-Pfade sowie `~/output/manual-local/`.
- Nicht löschen, ersetzen, deaktivieren oder Modell-Caches bereinigen, nur weil
  Cloud-Dienste oder andere Werkzeuge dieselbe Aufgabe anbieten.
- Reparaturen und Erweiterungen sind bei ausdrücklichem Auftrag erlaubt.
  Löschung, Austausch, Verschiebung, erneuter Download oder Änderung des
  Offline-Standards benötigt Hannibals vorherige ausdrückliche Zustimmung und
  eine Bestands-/Wiederherstellungsprüfung.
- Vor Änderungen `~/manuell.sh --check` ausführen. Der am 2026-09-27
  ausdrücklich gelöschte unvollständige LTX-2.3-Cache ist die einzige bereits
  freigegebene Ausnahme; LTX-2.5 bleibt geschützt.

## Nachtrag — Kreativ-Studio Quellen-zu-Video

- Datum: 2026-09-27. Schreibender Agent: Codex, direkter Nutzerauftrag.
- Das eigenständige Dashboard unter `~/PROJEKTE/kreativ-studio` verwendet den
  bestehenden `tools/video_ingest.py` unverändert für ausdrücklich aktivierte
  öffentliche Einzelmedien-Links. In diesem Repository wurde für diesen
  Auftrag kein Produktcode verändert.
- Der Dashboard-Standard bleibt für lokale Dateien offline. Externe Webseiten,
  YouTube und Instagram werden nur nach sichtbarer Checkbox-Freigabe pro
  Auftrag abgerufen; keine Cookies, Logins oder Accounts.
- Test: lokaler Mixed-Source-Render erfolgreich; private URL blockiert. Kein
  echter Plattformdownload, kein Upload, kein Commit und kein Push.

## Nachtrag — Video Pipeline Integrity Gate, DaVinci FCPXML & Remotion Social (17.10.2026)

- Datum: 2026-10-17. Schreibender Agent: Antigravity CLI.
- Task-ID: `AUDIT-VIDEO-PIPELINE-INTEGRITY-20261017-01`.
- Status: **Audit-Baselines festgelegt; Tests 14/14 bestanden; Artefakte kryptografisch inventarisiert; Paket bereit für unabhängiges read-only Review.**
- Git-Baselines:
  - Code-Stand (`video-toolkit`): Commit `5dfb86b` (Branch `chore/ltx25-adapter`, Vorgänger-Basis: `c2a323c`)
  - Dokumentations- & Pre-Review-Stand (`~` / `_SYSTEM`): Commit `ea02c94d` (Branch `main`, Vorgänger-Basis: `7dba6c93`)
- Umfang:
  1. `tools/preflight_gate.py`: Fail-Closed Manifest- und Provenienz-Prüfung (`derived_from_master_sha256 == hash(master)`), Pfad-Traversal-Sperre, Jail-Escape-Sperre, Symlink-Sperre, Verbot doppelter Shot-IDs, Verbot von Wildcards (`scene_*.jpg`).
  2. Mathematische Puffer-Matrix: Präzise Trennung von 10–15% Mindestreserve (66–69s) und 28–47% Hollywood-Produktionsreserve (77–88s).
  3. `tools/timeline_export.py`: DaVinci Resolve Timeline-Export als FCPXML v1.9 und OpenTimelineIO (.otio) mit robuster relativer Pfadauflösung.
  4. `tools/remotion_social.py`: Remotion Social 9:16 Captions & Safe Zone Autopilot (1080x1920, Y=850–1350).
  5. Pipeline-Integration: `~/.local/bin/hannibal-video-pipeline` bindet `preflight_gate.py` in Phase 1 vor jeder GPU-Inferenz fail-closed ein.
  6. Dokumentation: `docs/HANNIBAL-VIDEO-PIPELINE.md`, `docs/HANNIBAL-CINEMA-STUDIO-PLAN.md` und Pre-Review-Statusbericht `docs/VIDEO-PIPELINE-PRODUKTIONSREIFE-PRE-REVIEW-2026-10-17.md` aktualisiert.
- Verifikation & kryptografisches Artefaktmanifest (`out/audit_artifacts_manifest.json`):
  - Pytest: 14/14 Tests PASS (`tests/test_preflight_gate.py`, `tests/test_timeline_export.py`, `tests/test_remotion_social.py`).
  - Remotion Smoke Test: `out/smoke_test.mp4` (16.443 Bytes, SHA-256 `4e3eff180a16e391a85fec76db5336369e1a507e3a79c13e3b66a91c8a186f5e`, ffprobe: h264, 960x540, 30fps, 1.033s).
  - DaVinci FCPXML Export: `out/davinci_smoke_test.fcpxml` (872 Bytes, SHA-256 `9dbf463151c6e306faecbb7e0359f9f9e56856892406fd46743cc0aa4d32a757`).
  - OpenTimelineIO Export: `out/davinci_smoke_test.otio` (2.966 Bytes, SHA-256 `7f13a20f9903a5bc76a3ec542ba3a3c025061c6b72c8a66ea5e0c8218e266e46`).

- Datum: 2026-09-05
- Schreibender Agent: Codex (Interims-Hauptagent)
- Branch: `main`
- Worktree: `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`
- Ziel: System-Sanierungsplan, Root-Workspace sowie Blöcke 1–4 ohne externe Deployments

## Ergebnis

- Vorzustand unter `~/Backups/video-toolkit/2026-09-04-root-workspace-v1/` als Binär-Patch, Status, Manifestkopien und SHA-256-Prüfsummen gesichert.
- Root-npm-Workspace mit Node 22, Root-Lockfile und lokalem TypeScript erstellt.
- `lib/` nach `packages/remotion-shared` migriert; alle drei Templates verwenden ausschließlich den Workspace-Vertrag. Alte Template-Lockfiles wurden erst nach erfolgreicher Root-Installation entfernt.
- Remotion auf 4.0.520 vereinheitlicht; `backgroundDark` und die typisierte Transition-Erzeugung ohne Suppressions korrigiert.
- Python auf `pyproject.toml`/`uv.lock`, Python 3.12, Ruff, mypy und pytest migriert. Parser, Splitter, Orchestrator, Registry und Medienvalidierung besitzen Tests.
- Orchestrator verwendet stabile Job-IDs, atomare Zustände, Wiederaufnahme, Timeouts und idempotente fertige Artefakte.
- CI, CodeQL, Dependabot, SECURITY.md, SHA-gepinnte Actions und Betriebsrunbook ergänzt. Keine Cloud-/GPU- oder kostenpflichtigen Läufe durchgeführt.

## Verifikation

- `npm ci`: bestanden.
- `npm run verify`: bestanden; vier TypeScript-Workspaces, Ruff, mypy, 17 pytest-Tests und alle drei Remotion-Bundles grün.
- `npm audit --audit-level=high`: 0 Schwachstellen.
- `git diff --check`: bestanden.
- Erzeugte Build-, Output-, Cache- und Mediendateien bleiben ignoriert.

## Offene externe Schritte

- Branch-Schutz, Secret Scanning/Push Protection und erforderliche Checks müssen mit Repository-Adminrechten in GitHub aktiviert werden.
- Kompositionsauflösung und ein vorhandenes 13,3-s-H.264-Artefakt wurden lokal vollständig decodiert und validiert. Ein neuer Drei-Frame-Smoke erzeugte Frames, hing jedoch vor dem Encoding-Abschluss und wurde ohne Artefakt abgebrochen; dieser Teil bleibt für die nächtliche Pipeline. Keine Cloud-GPU-Freigabe wurde erteilt.
- Keine Commits, Pushes, Releases oder Deployments wurden ausgeführt.

## Commit-Vorbereitung

Empfohlener Migrations-Commit nach unabhängiger Diff-Prüfung: `refactor(toolkit): migrate templates to verified root workspace`

## Lokale Commits

Release-Branch: `release/system-hardening-2026-09` (HEAD `aa2ccbd`; Dokumentationsnachtrag `aa2ccbd`).

- `7631865` — Root-Workspace, Shared-Paket, Python-Toolchain, CI und Security-Grundlagen.
- `e427378` — Medienvalidierung des ersten und letzten Videoframes.
- `074f844` — Ruff-konforme Formatierung des Medienvalidators.
- `4b5a616` — finaler Handoff-Nachweis und Commit-Dokumentation.
- `633a979` — kontrollierter CI-Medien-Smoke mit Timeout und Validator.
- `aa2ccbd` — Staging-, Rollback- und GitHub-Schutzkonfiguration dokumentiert.
- `4ed12fe` — Dependency-Review-Gate mit vollständigem SHA ergänzt.

## Nachtrag — Control-Center Silence-Cut-Plan

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag.
- Änderung: `tools/silence_cutter.py` besitzt zusätzlich `--plan-only`. In diesem Modus wird die vorhandene Erkennung/Segmentberechnung ausgeführt und bei `--json` ausgegeben, aber keine Output-Datei erzeugt. `--output` bleibt für echte Schnitte Pflicht.
- Verifikation: Projekt-venv mit vorhandenem `tests/render-baseline/public/testsrc.mp4`, `--plan-only --json`: ein Segment, keine Ausgabe erstellt.
- Keine Cloud-, Provider- oder Credential-Nutzung; kein Commit/Push. Der Control-Center-Server verwaltet die bestätigte Ausführung separat.

## Nachtrag — lokale SRT/VTT- und Subtitle-QC-Lücke geschlossen

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag und ausdrückliche Übernahme der vorhandenen Teilimplementierung.
- Änderung: `tools/transcribe.py` akzeptiert MLX-Whisper-kompatibles Timestamp-JSON, erzeugt UTF-8-SRT und WebVTT, prüft Struktur, Zeitreihenfolge, negative/ungültige Timestamps, Überlappungen, leere Cues, Extremdauern und Zeilenlänge. Bestehende SRT/VTT lassen sich separat prüfen. Optionaler Burn-In verwendet ausschließlich FFmpeg und bricht verständlich ab, wenn dessen `subtitles`/libass-Filter fehlt.
- Tests: 33 lokale pytest-Tests bestanden, inklusive JSON → SRT/VTT → CLI-QC; Ruff, mypy für `tools/transcribe.py`, JSON-Validierung der Registry und `git diff --check` bestanden. Keine Provider-, Modell-, Account-, API- oder Cloud-Nutzung.
- Offener Punkt: Der installierte FFmpeg-Build enthält keinen `subtitles`/libass-Filter. Daher ist Burn-In bewusst nicht als aktiv verfügbar ausgewiesen; SRT/VTT und Subtitle-QC sind unabhängig davon vollständig lokal funktionsfähig.

## Nachtrag — Lokaler SRT/VTT- und Subtitle-QC-Pfad

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag. Risiko: begrenzte lokale Verhaltensänderung; keine externe Integration.
- Geändert: `tools/transcribe.py` und neu `tests/test_subtitles.py`. Der vorhandene MLX-Whisper-Transkriptvertrag bleibt kompatibel; zusätzlich akzeptiert `--transcript-json` sowohl eine vorhandene Segmentliste als auch ein MLX-Ergebnisobjekt. `--srt`, `--vtt` und `--subtitle-qc` erzeugen beziehungsweise prüfen lokale Untertitel ohne Netzwerkzugriff.
- QC: prüft lesbare Datei, SRT-/VTT-Struktur, Header bzw. Nummerierung, Timestamp-Syntax, Start vor Ende, chronologische Reihenfolge, Überschneidungen, leere Texte sowie extrem kurze/lange Cues und überlange Zeilen. Bei Cue-QC-FAIL werden keine Untertiteldateien geschrieben.
- Verifikation: vorhandenes `output/media-pipeline-test/transcript.json` (24 Zeitsegmente) → SRT und VTT in `/private/tmp/audio-speech-p0p1-20260919/`, beide PASS; `pytest -q` vollständig 24/24 PASS; Ruff und `py_compile` PASS; `git diff --check -- tools/transcribe.py tests/test_subtitles.py` PASS. Die vorhandene Test-MP4 enthält H.264/AAC, 10.856250 s.
- Burn-In: nicht aktiv. `ffmpeg -filters` enthält keinen `subtitles`/libass-Filter; ein lokaler Burn-In-Versuch scheiterte daher erwartbar mit „No such filter: subtitles“. Kein Tool installiert und kein Ersatzweg eingeführt.
- Translation/TTS/Sensitive: keine lokale Übersetzungsfunktion oder geeignetes lokales Speech-/Translation-Modell nachgewiesen; **NO LOCAL TRANSLATION PATH VERIFIED** und **STOP / NO LOCAL PATH VERIFIED** bleiben gültig. Kokoro nicht ausgeführt und nicht heruntergeladen.
- Fester Prüfstand: `tools/transcribe.py` SHA-256 `7e31f0356706d252d94066f20f507548e69317ba8b12e860bf484721f1a4c1a9`; `tests/test_subtitles.py` SHA-256 `8900dd0ac3039976d15f9f37d7ca7fc4850b8ec1ca647e1a8596c2871167995b`.
- Keine Accounts, API-Keys, Credits, Abos, Cloud-GPUs, kostenpflichtigen Tests, Modell-/Tool-Installationen, Commits, Pushes oder Deployments.

## Nachtrag — Whisper-Segment-Splitting für Untertitel

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag. Risiko: begrenzte lokale Verhaltensänderung.
- Änderung: Lange Whisper-Segmente werden in `tools/transcribe.py` vor der Subtitle-QC bevorzugt an Satz-, dann Klausel- und Wortgrenzen getrennt. Die Cue-Zeiten bleiben proportional, monoton und innerhalb des ursprünglichen Segmentbereichs. Bei ausreichend langer Quelle garantiert die Verteilung mindestens 100 ms pro Cue; bei mathematisch unmöglicher Quellspanne bleibt der Cue-Bereich korrekt und QC meldet die unvermeidbar zu kurze Dauer. Einzelwörter über dem Limit bleiben unverändert und scheitern deterministisch im QC.
- Verifikation: Reales lokales `a_monolog.wav` mit bereits gecachtem `mlx-community/whisper-tiny-mlx` über Metal ausgeführt. Zwei Whisper-Segmente; längstes Originalsegment 104 Zeichen. JSON → SRT und VTT → Subtitle-QC: PASS. Keine Modell-, Netzwerk-, Account- oder Kostenaktion.
- Tests: vollständige aktuelle Suite 52/52 PASS; Ruff, mypy für `tools/transcribe.py`, `py_compile` und `git diff --check` PASS. Die übergebene LING-3-Baseline war 41/41; zusätzliche inzwischen vorhandene Subtitle-Regressionstests wurden erhalten und mitgeprüft.
- Offene Punkte: FFmpeg-Burn-In bleibt wegen fehlendem `subtitles`/libass-Filter OPEN; Translation, Kokoro und Sensitive Audio unverändert.

## Nachtrag — Video-Ingest- und technische Analyse-Pipeline

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag. Risiko: begrenzte lokale Verhaltensänderung.
- Geändert: neu `tools/video_ingest.py` und `tests/test_video_ingest.py`; zentraler Registry-Eintrag in `_internal/toolkit-registry.json`. Vorhandene `tools/transcribe.py`, Subtitle-QC und `tools/media_validation.py` wurden wiederverwendet und nicht umgebaut; `tools/silence_cutter.py` blieb unverändert.
- Funktion: deterministische Source-Erkennung für lokale Dateien, direkte öffentliche Medien-URLs, YouTube und Instagram; lokal kontrollierte Ausgabepfade, FFprobe-Validierung, Audio- und begrenzte Frame-Extraktion sowie ein technisches Analysepaket (`metadata.json`, `analysis.json`, optionale Audio-, Transcript-, SRT/VTT- und Frame-Artefakte). Der Plattformadapter verwendet nur vorhandenes `yt-dlp`, ohne Cookies, Credentials oder Login. Playlist- und Channel-URLs werden abgewiesen. Ein nicht gecachtes Whisper-Modell wird nicht heruntergeladen.
- Verifikation: lokales A/V-Testartefakt aus vorhandenen `e_filler_test.mp4` und `a_monolog.wav` → Ingest → ffprobe → Audio → bereits gecachtes Tiny-MLX-Whisper über Metal → Transcript → SRT/VTT → Subtitle-QC → drei begrenzte Frames → Analysepaket. Ergebnis: PASS, 2 Whisper-Segmente, längstes Originalsegment 103 Zeichen. Zusätzlich lokaler Ingest ohne Whisper und die Unit-Tests für Source-/Pfad-/Probe-/Download-Fehler-/Audio-only-/Video-ohne-Audio-/Frame-/Subtitle-Regression.
- Tests: Projekt-venv vollständig `65 passed`; Ruff für neue Dateien, mypy für `tools/video_ingest.py`, Python-Compile, Registry-JSON und `git diff --check` bestanden.
- Offene Punkte: Direkte HTTP-Medien-URLs sowie YouTube/Instagram wurden ohne externen Netztest bewusst nicht als live verifiziert ausgewiesen. Instagram bleibt nur für öffentlich ohne Login zugängliche Inhalte technisch vorgesehen; private oder zugriffsgeschützte Inhalte stoppen. Kein DRM-/Login-/Cookie-/Credential-Bypass, keine Tool-/Modellinstallation, keine Accounts, keine Cloud, keine Kosten, kein Commit/Push.

## Nachtrag — Video Content Analysis / Scene Intelligence

- Datum: 2026-09-19. Schreibender Agent: Codex, direkter Nutzerauftrag. Risiko: begrenzte lokale Verhaltensänderung.
- Geändert: neu `tools/video_analyze.py` und `tests/test_video_analyze.py`; zentraler Registry-Eintrag in `_internal/toolkit-registry.json`. Der Ingest-, SSRF-, Whisper-/Subtitle- und Silence-Cutter-Kern wurde nicht verändert. Wiederverwendet wird ausschließlich `silence_cutter.detect_silences` als Read-only-Analysefunktion.
- Funktion: Der neue CLI-Einstieg erweitert ein vorhandenes `analysis.json` kompatibel um ein einheitliches Zeitmodell, lokal per FFmpeg ermittelte Szenengrenzen, vollständige Transcript-Segmentreferenzen je Szenenüberlappung, Speech-/Silence-/Unknown-Segmente, genau einen repräsentativen Midpoint-Frame pro Szene, messbare Kapitelinputs und längenbegrenzte Clip-Candidates. `semantic_analysis` bleibt explizit `{ "status": "not_run" }`; keine semantischen oder kreativen Scores.
- Verifikation: vorhandenes lokales A/V-Testartefakt → Ingest → bereits gecachtes Tiny-MLX-Whisper → Transcript/SRT/VTT → `video_analyze` mit 2–8-s-Clipfenster. Ergebnis: 1 Szene, 1 repräsentativer Frame, 2 vollständig zugeordnete Transcriptsegmente, 0 erkannte Stille-Regionen, 5 begrenzte Clip-Candidates. `analysis.json` auf Zeitgrenzen, Frame-Dateien, Transcript-IDs und Status geprüft.
- Tests: vollständige Projekt-venv-Suite `83 passed`; Ruff, mypy für `tools/video_analyze.py`, Python-Compile, Registry-JSON und `git diff --check` bestanden. Die LING-/Ingest-Teststände blieben grün.
- Offene Punkte: Kein bereits ingestetes YouTube-Artefakt gefunden; YouTube-Medienanalyse daher nicht erneut getestet und kein neuer Download erzwungen. Visuelle Szenenqualität hängt bewusst von FFmpeg `scene`-Filter und konfigurierbarem Threshold ab; die erzeugten Einträge sind technische Kandidaten, keine semantischen Kapitel-/Highlight-Entscheidungen. Keine Tool-/Modellinstallation, Accounts, Cloud, Kosten, Commit/Push.

## Nachtrag — Schritte 2–5: Routing, Layout-Engine, Subtitle-Burn, Acceptance run2

- Datum: 2026-09-20. Schreibender Agent: Claude Code, direkter Nutzerauftrag (Fortsetzung von 4cf23f9/32cb575). Branch: `feature/capabilities`. Risiko: begrenzte Verhaltensänderung, keine Auth/Security/Migrations-Berührung.
- Commits: `f63b9dd` (Routing-Tabelle + `ai_router_check`), `b01bca9` (uv.lock-Sync für bereits gepinntes `playwright==1.63.0`), `ec59078` (Layout-Engine F02+F03), `0c3c422` (Remotion-Subtitle-Burn F10), `5391a66` (Acceptance run2). `integration/internal-v1` wurde per `--ff-only` auf `5391a66` vorgezogen (kein Push).
- Schritt 2: `contracts/task-routing.json` deckt alle 12 Aufgabentypen ab; `tools/ai_router_check.py` pingt lokale Backends (ollama, whisper, kokoro, ffmpeg, playwright, remotion) live und beweist per `require_egress`, dass Cloud-Backends im `internal_only`-Modus blockiert bleiben.
- Schritt 3: `contracts/layout-spec.schema.json` fertiggestellt (custom-Canvas braucht width/height, Pflichtfelder je Layer-Typ, `weight`, additionalProperties:false). `tools/layout_render.py` rendert dpi-abhängig A4/A5/custom, bettet lokale Schriften als data-URI ein, blockt jede Nicht-file/data-Anfrage per `page.route` (mit echtem Playwright-Test), registriert Spec als `EDITABLE_SOURCE` und PNG/PDF als `MASTER` mit vererbten Rechten. `templates/layout/flyer-a4.json`/`flyer-a5.json` liegen bei.
  - **Dabei gefundener und behobener Bestandsfehler aus Schritt 1 (32cb575):** Subtitle-/Document-Asset-Registrierung schlug immer fehl, weil `technical` ein nicht erlaubtes `bytes`-Feld enthielt (Schema hat `additionalProperties:false`). Live reproduziert, dann in `tools/asset_record.py` behoben (kein Schema-Change). Ohne diesen Fix wäre weder die `EDITABLE_SOURCE`-Registrierung der Spec (Schritt 3) noch die SRT-Registrierung (Schritt 4/F14) möglich gewesen.
- Schritt 4: FFmpeg hat weiterhin keinen `subtitles`/libass-Filter. `tools/remotion/subtitle-burn/` (SubtitleBurn.tsx + Root.tsx) ist eine kleine lokale Remotion-Komposition; `tools/subtitle_burn.py` parst SRT/VTT, probet das Quellvideo, bettet `font_file` als data-URI ein und rendert über die bereits installierte lokale Remotion-CLI (kein npx, kein Netzwerk). Live-Fund: `OffthreadVideo` akzeptiert kein `file://`-Src direkt (Remotions Asset-Downloader lehnt es ab) — Fix: Video wird in ein Temp-`--public-dir` kopiert und über `staticFile()` referenziert. Output wird als `MASTER` mit `parent_ids` [Video, Subtitle] registriert.
- Schritt 5: `tools/acceptance.py` F02/F03/F10/F12/F14 auf die neuen Tools umgestellt; F03 rendert, ändert Text/Höhe/Schrift per `set` und beweist eine abweichende zweite Ausgabe; F14 registriert jetzt SRT/VTT/Übersetzung/Transcript als abgeleitete `VARIANT`-Text-Assets (7 Records statt 3). Lauf: **15/15 PASS**, Berichte unter `docs/ACCEPTANCE-2026-09-20-run2.{md,json}` (Baseline-Dateien unverändert).
- Tests: `uv run pytest -q` vollständig `167 passed` (inkl. 4 Playwright-/Remotion-Browser-Tests, liefen problemlos in der Standard-Sandbox — keine Mach-Port-Ausnahme nötig). Ruff/mypy für alle neuen/geänderten Dateien grün.
- Egress/Rechte: Kein Push, keine Uploads, keine Netzwerkzugriffe im Code (Playwright/Remotion blocken alles außer file:/data:, geprüft per Test); keine neuen Installationen (Playwright 1.63.0 + Chromium sowie Remotion 4.0.520 waren bereits vorhanden/gepinnt).
- Offene Punkte: `contracts/task-routing.json` ist keine formal per JSON-Schema geprüfte Struktur (nur Pytest-Strukturchecks) — bewusst so belassen, da keine Notwendigkeit für ein weiteres Schema erkennbar war. Layout-Renderer unterstützt keine automatische Textumbruch-Messung (nur CSS `white-space:pre-wrap`); für sehr lange Texte kann Inhalt die Layer-Box überschreiten, ohne Fehler zu werfen.

## Nachtrag — Schritte 0–6: Stack-Härtung, Projektanlage, Locks, QC, Kosten-Router, Acceptance run3

- Datum: 2026-09-20/21. Schreibender Agent: Claude Code, direkter Nutzerauftrag. Branch: `feature/system-core` (von `integration/internal-v1` @ 45ec154). Risiko: begrenzte Verhaltensänderung plus ein bewusst dokumentierter, nicht behobener Versions-Mismatch (F13/Python).
- Schritt 0: `flyer-1.png/pdf`, `flyer-2.png/pdf`, `burned.mp4` nach `video-toolkit-media/output/acceptance-examples/` kopiert (gitignored, nicht committet).
- Commits: `1e7faf1` (Stack-Minimums + F13-Härtung), `f759ecb` (project_init + task-routing-Schema), `4412062` (reference_registry + job_spec), `b5f561e` (qc_pipeline + DELIVERY-Gate), `3ed5ab2` (cost_router), `c2e6dd5` (Acceptance run3). `integration/internal-v1` **nicht** vorgezogen (18/19, nicht "alles grün").
- Schritt 1: FFmpeg 9.0.1→9.0.2 (`brew upgrade ffmpeg`, nur diese Formel), Node 22.22.2→22.23.2 (`fnm install/default`, v24.21.0 für n8n unangetastet), Remotion + alle `@remotion/*` einheitlich 4.0.520→4.0.526 (root `npm install` nach vollständigem `node_modules`-Neuaufbau, da npm mit stehendem Lockfile in einen ERESOLVE-Konflikt lief; `templates/ai-engineering-review` bewusst ausgenommen — kein Workspace-Mitglied, hatte nie ein installiertes `node_modules`, also keine "bereits installierte" Version zum Hochziehen). Ollama nur gemeldet (0.34.2), nicht aktualisiert.
  - **Live-Fund:** `_stack_versions()`s Remotion-Check nutzte `remotion --version`, was nie funktioniert hat (`stack-manifest.json` zeigte deshalb dauerhaft `"remotion": null`); jetzt über `remotion versions` inkl. Konsistenzprüfung aller `@remotion/*`-Pakete.
  - **Bewusster Nicht-Fix:** `contracts/stack-manifest.json` fordert `python>=3.14.7`; das projekteigene, absichtlich auf `<3.13` gepinnte `.venv` (Migration 2026-09-04, mlx-whisper/Apple-Silicon-Kompatibilität) meldet 3.12.14. Der Pin wurde **nicht** angehoben — das wäre eine nicht beauftragte, riskante Abhängigkeitsänderung außerhalb dieses Auftrags gewesen. F13 schlägt deshalb dauerhaft und absichtlich an genau dieser einen Metrik fehl; per Test in `tests/acceptance/test_acceptance.py` festgeschrieben, kein stiller Workaround.
- Schritt 2: `tools/project_init.py` legt `video-toolkit-media/projects/<id>/{brief,specs,manifests,analysis,qc,prompts,jobs,provenance}/` an, schreibt ein gegen `project-manifest.schema.json` validiertes Manifest; `load_project_manifest`/`save_project_manifest` sind die einzige Schreib-Schnittstelle für spätere Schritte (jede Änderung erneut schema-validiert). Bestehendes Remotion-`project.json`-System unangetastet. `contracts/task-routing.schema.json` neu, in `validate_contracts.py` als Kind `"routing"` registriert.
- Schritt 3: `tools/asset_record.py` bekam `role="REFERENCE"` mit `reference_kind`/`purpose_binding`/`edit_approval` (rein additiv, keine Schema-Änderung — `asset-manifest.schema.json` sah das längst vor, nur der Code konnte es nicht erzeugen). `tools/reference_registry.py` verifiziert jedes Member erneut gegen die Platte (Record, Rolle, reference_kind, Hash) vor dem Hashen des Sets; PERSON_LOCK-Pflichtansichten und Rechte-Validierung laufen über den bestehenden zentralen Validator, nicht dupliziert. `tools/job_spec.py` bindet aktive Locks mit Hash in die Job-Spec und lehnt bei Drift ab.
  - **Gefundener und behobener Bug:** `from tools.project_init import PROJECTS_ROOT` in `job_spec.py` band den Pfad beim Import fest — spätere Änderungen an `project_init.PROJECTS_ROOT` (z.B. in Tests) wurden nie gesehen. Per Test aufgedeckt, behoben durch `from tools import project_init` + dynamischen Zugriff.
- Schritt 4: `contracts/qc-verdict.schema.json` neu. `tools/qc_pipeline.py` führt echte technische Prüfungen (media_validation, Subtitle-QC, Layout-Strukturcheck) aus; die vier visuellen Prüfungen sind immer `needs_human` — ein automatischer Lauf kann nie `accept` liefern, nur `apply_review()` mit benanntem Reviewer. `register_derived(..., role="DELIVERY", ...)` verlangt jetzt ein akzeptiertes Verdikt für mindestens einen Parent (per Late-Import, um den Zyklus mit `qc_pipeline` zu vermeiden).
  - **Gefundener und behobener Bug (Auswirkung erst in Schritt 6 sichtbar):** `build_asset_record()` konnte `ai_involvement.ai_generated` nie auf einen definiten Wert setzen (immer `"unknown"`), aber DELIVERY verlangt `none/partial/full` — der einzige bestehende DELIVERY-Test umging das, indem er einen Fixture-Record von Hand statt über `register_asset()` schrieb. Neuer Parameter `ai_generated` (Default `"unknown"`, gegen das Schema-Enum geprüft) macht den echten Registrierungspfad erstmals tatsächlich DELIVERY-fähig.
- Schritt 5: `tools/cost_router.py` erzwingt cached_asset > local_deterministic > included_approved_surface > external_specialist > premium anhand `task-routing.json`s Lokalität; Cache-Treffer über `derivation.params_sha256` (neues optionales Feld an `register_derived`). `external_specialist`/`premium` brauchen eine Freigabedatei (`cost_router.py approve`) **und** werden danach zusätzlich vom bestehenden Egress-Guard blockiert (in diesem `internal_only`-Setup daher praktisch immer, per Test bewiesen). Jede Entscheidung geht validiert ins Projektmanifest und als Zeile in ein append-only `cost-log.jsonl`.
- Schritt 6: F16 (Locks), F17 (QC), F18 (Kosten), F19 (Projekt) ergänzt, `CAPABILITY_IDS` auf F01–F19 erweitert. **Gefundener und behobener Bug:** zwei hartcodierte `"... von 15"`-Strings in `_write_reports()`/`main()` (aus der Zeit vor Schritt 6) zeigten nach der Erweiterung `"PASS 19 von 15"` an; jetzt `len(CAPABILITY_IDS)` überall. Lauf: **18/19 PASS**, nur F13 (siehe oben) fehlt. Berichte unter `docs/ACCEPTANCE-2026-09-20-run3.{md,json}`, Baseline und run2 unverändert.
- Tests: `uv run pytest -q` vollständig `237 passed`; Ruff/mypy einzeln für alle 17 in diesem Branch geänderten Python-Dateien grün; `contracts/validate_contracts.py selftest` grün; `git diff --check` über den ganzen Branch sauber.
- Egress/Rechte: Kein Push, keine Netzwerkzugriffe im Tool-Code; `npm install`/`brew upgrade`/`fnm install` waren für Schritt 1 ausdrücklich als Upgrade-Wege erlaubt (nicht "neue Installationen" im Sinne der harten Regel) und liefen einmalig, kontrolliert, mit Netzwerkzugriff nur für den Paketmanager selbst. Egress-Guard und Rechte-Gate wurden nicht abgeschwächt, sondern in Schritt 5 zusätzlich als eigenständige Sperre demonstriert.
- Zusätzlich uncommittet (bewusst, wie Schritt 0): `video-toolkit-media/.gitignore` bekam `!assets/**/*.refset.json` ergänzt (Reference-Sets sollen im Media-Store verfolgt werden), passend zur Vorgabe aus Schritt 3. Separates Repo mit echtem GitHub-Remote — hier wird grundsätzlich nichts committet oder gepusht.
- Offene Punkte: F13 bleibt absichtlich rot (Python-Pin, siehe oben) — Entscheidung, ob Pin oder Mindestversion angepasst wird, liegt beim Menschen. `integration/internal-v1` daher bewusst nicht vorgezogen; verbleibt auf `45ec154`, bis das geklärt ist.

## Nachtrag — Schritte 1–9: F13-Fix, Push-Sperre, Plattform-Profile, Reframe, Semantik, Provenance, Release-Paket, Adapter-Trockenlauf, Acceptance run4

- Datum: 2026-09-20/21. Schreibender Agent: Claude Code, direkter Nutzerauftrag ("Schritte 1 bis 9, selbstständig, erst am Ende berichten"). Branch: `feature/system-core` (auf `11d9aaa`, Basis `integration/internal-v1@45ec154`). Risiko: Schritte 1/2 begrenzte Verhaltensänderung + Repo-Konfiguration (Push-URL), Schritte 3–8 additive neue Fähigkeiten, Schritt 9 Testinfrastruktur.
- Commits (video-toolkit): `62547e5` (F13-Fix: Python-Minimum aus pyproject statt fixem Ziel), `ea38951` (Egress-Audit: Repo-Push-Status), `8497dc1` (Plattform-Profile Schema+Daten+Lib), `665e70d` (Reframe ohne Blind-Crop), `681fe25` (Semantik-Analyse-Vertrag + Cloud-Scope-Prüfung), `e3978c1` (Plattform-Varianten-Export + technische QC), `36c79da` (Provenance-Bericht + Labeling-Status), `dadc7b9` (Release-Paket mit harten Gates), `3b23782` (Publish-Adapter-Trockenlauf), `4407d31` (Acceptance run4, F20–F25, 25/25 PASS).
- Commit (video-toolkit-media, Branch `feature/media-pipeline`): `aafd404` (`.gitignore`: `!assets/**/*.refset.json` getrackt, aus Schritt 3 der Vorsession nachgeholt).
- Schritt 1: `contracts/stack-manifest.json`s Python-Minimum folgt jetzt `pyproject.toml`s `requires-python` (`>=3.12`) statt eines unabhängig gesetzten Ziels; F13 prüft weiterhin exakt das projekteigene, bewusst auf `<3.13` gepinnte venv (3.12.14, mlx-whisper/Apple-Silicon). Damit ist der in der Vorsession offen gelassene F13-Mismatch aufgelöst, ohne den venv-Pin anzufassen.
- Schritt 2: `video-toolkit-media`s Push-URL für `origin` auf `DISABLED_INTERNAL_ONLY` gesetzt (Fetch unverändert) — dieses Repo hat einen echten GitHub-Remote, `video-toolkit` selbst wurde **bewusst nicht** angefasst (Auftrag war auf das Media-Repo begrenzt; siehe „Offene Punkte" unten). `tools/egress_audit.py` meldet jetzt pro Repo (`video-toolkit`, `video-toolkit-media`) alle Remotes und ob deren Push-URL deaktiviert ist, mit echten Temp-Git-Repos getestet.
- Schritt 3: `contracts/platform-profiles.schema.json` + `contracts/platform-profiles.json` mit genau 13 benannten Profilen (youtube_long/short, instagram_reel/feed, facebook_video, tiktok, x_video, website_hero, ecommerce_video/image, ad_16x9/1x1/9x16), alle **UNVERIFIED**, `verified_at`/`source_url` `null`, konservative Werte. Verifizierung ist ausdrücklich ein späterer manueller Schritt des Menschen.
- Schritt 4: `tools/reframe.py` verweigert ohne Fokus-Spec jede Ausgabe (`needs_human`, kein stiller Center-Crop); `--allow-center-crop` nur mit Begründung, dann als QC-Warnung protokolliert. Fokus-Spec wird als `EDITABLE_SOURCE` registriert, Output als `VARIANT` mit beiden Eltern (Master + Spec). Pixel-Beweistest bestätigt, dass unterschiedliche Fokuspunkte tatsächlich unterschiedliche Crops erzeugen.
- Schritt 5: `tools/semantic_analysis.py` — `prepare` erlaubt Cloud-Modelle nur bei `provider_data_scope=cloud_approved` **und** Provider in `approved_providers`, sonst Ablehnung mit Log; `ingest` validiert ein Agent-Ergebnis gegen das neue Schema und registriert es als Text-Asset (`ai_generated=partial`). Dabei zwei echte Bestandslücken in `tools/asset_record.py` gefunden und behoben: `set_rights()` hatte keinen `approved_providers`-Parameter, und `_inherited_rights()` vererbte ihn nicht (Fix: Schnittmenge über alle cloud_approved-Eltern, Fehler bei leerer Schnittmenge).
- Schritt 6: `tools/platform_export.py` `make-variant` erzeugt bei UNVERIFIED-Profil nur einen Draft (nicht release-fähig); rendert Reframe/Loudness/Encode/Thumbnail, registriert `VARIANT` mit Eltern, schreibt technisches QC-Verdikt gegen die Profilgrenzen. Dabei echte Sicherheitslücke in `qc_pipeline.py` gefunden: ein rein technischer Checks-Lauf ohne visuelle `needs_human`-Prüfungen konnte `_overall()` legitim `"accept"` liefern, obwohl nur `apply_review()` das setzen darf — `write_verdict()`/`retry_qc()` stufen ein berechnetes `"accept"` jetzt immer auf `"needs_human"` herab.
- Schritt 7: `tools/provenance_report.py` erzeugt pro Projekt einen rekursiven Provenance-Graphen (JSON+MD) inkl. unsigniertem C2PA-Ingredient-Mapping (kein Zertifikat, keine Bibliothek); `set-labeling` setzt `ai_labeling_status` nie automatisch, nur per explizitem Kommando mit Begründung. Dabei fehlende Infrastruktur entdeckt: `project.manifest.json`s `asset_ids` wurde nirgends befüllt — neues `project_init.add_asset_id()`, in `qc_pipeline`, `semantic_analysis` und `platform_export` nachgerüstet.
- Schritt 8: `contracts/release-metadata.schema.json` + `tools/release_package.py` `create`/`approve` — ein Paket entsteht nur, wenn Projekt-Manifest gültig, jede Variante das Delivery-Gate besteht, Profil VERIFIED ist, Labeling gesetzt ist, ein aktueller Provenance-Bericht existiert und Metadaten vorhanden sind; Freigabe ausschließlich über `approve()`. `tools/publish_adapters/{base,youtube,instagram,facebook,tiktok,ecommerce}.py`: `validate()` prüft lokal, `send()` ist in jedem Adapter durch `require_egress()` blockiert; ein statischer AST-Test beweist, dass kein Adapter eine Netzwerkbibliothek importiert. `youtube.py` dupliziert bewusst die Limit-Konstanten aus `tools/youtube_upload.py` statt es zu importieren (dieses Modul bricht beim Import ohne installiertes `googleapiclient` sofort mit `sys.exit(1)` ab).
- Schritt 9: `tools/acceptance.py` um F20–F25 erweitert (`CAPABILITY_IDS` jetzt F01–F25). Lauf: **25/25 PASS**, Berichte unter `docs/ACCEPTANCE-2026-09-21-run4.{md,json}` (ältere Baseline/run2/run3 unverändert). `integration/internal-v1` deshalb per `--ff-only` auf `feature/system-core@4407d31` vorgezogen.
- Tests: `uv run pytest -q` vollständig `347 passed`; `contracts/validate_contracts.py selftest` grün (13/13); Ruff/mypy einzeln für jede in diesem Auftrag geänderte Python-Datei grün.
- Egress/Rechte: Kein Push, keine Netzwerkzugriffe im Tool-Code, Egress-Guard/Rechte-Gate nicht abgeschwächt — im Gegenteil zweimal als echte Sperre nachgewiesen (Schritt 8 `send()`, Schritt 9 F25). `contracts/egress-allowlist.json` bekam 5 neue False-Positive-Einträge (Plattformnamen in Adapter-Dateinamen/-Docstrings sowie in `tools/acceptance.py`s F20-Profilliste), jeweils nach dem bestehenden Muster begründet, keine Schwächung der Erkennung selbst.
- Zusätzlich uncommittet (unabhängig von diesem Auftrag, aus einer vorherigen Shell-Reparatur): `.nvmrc` wurde auf die exakte Version `22.23.2` gepinnt (vorher `22`), mit Nutzerfreigabe, aber bewusst nicht committet — bleibt für eine separate, ausdrückliche Freigabe offen.
- Offene Punkte: `video-toolkit`s eigener `origin`-Remote hat weiterhin eine aktive Push-URL — der Auftrag begrenzte die Push-Sperre ausdrücklich auf `video-toolkit-media`. Alle 13 Plattform-Profile sind weiterhin UNVERIFIED (bewusst, echte Werte müssen vom Menschen verifiziert werden, bevor ein Release-Paket produktionsreif werden kann). `.nvmrc`-Änderung wartet auf separate Commit-Freigabe.

## Nachtrag — Finaler Abschlusscheck feature/system-core

- Datum: 2026-09-21. Schreibender Agent: Codex, direkter Nutzerauftrag. Branch/Worktree: `feature/system-core` in `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`. Risiko: reine Verifikation; keine Produktcode- oder Architekturänderung.
- Organigramm: Der Knoten heißt bereits ausschließlich `Codex 2`; die Phrase „getrennte Colleague-Instanz“ ist im Organigramm nicht vorhanden, daher keine Änderung.
- Browser-Rendering: Playwright 1.63.0 und Chromium sind lokal vorhanden. Der Mach-Port-`SIGTRAP` in der eingeschränkten Sandbox wurde außerhalb dieser Einschränkung reproduktionsfrei geprüft: 23 fokussierte Layout-/Subtitle-Tests PASS sowie F02/F03/F10 PASS. Kein Projektfehler und kein Code-Fix erforderlich.
- Plattformprofile: Alle genau 13 Profile schema-valide und unverändert `UNVERIFIED`; keine realen Plattformwerte ergänzt.
- Runtime/Remote: `.nvmrc` ist bereits uncommitted auf `22.23.2` gepinnt; mit `fnm use 22.23.2` ist sie mit `engines.node = 22.x` sowie F13 konsistent. `origin` fetch bleibt GitHub, push ist tatsächlich `DISABLED_INTERNAL_ONLY`; nichts am Remote geändert.
- Prüfungen: `npm run verify` mit Node 22.23.2 PASS (347 pytest, TypeScript, Ruff, mypy, drei Remotion-Bundles). `uv run python tools/acceptance.py` PASS 25/25 (F01–F25). Berichte neu und uncommitted: `docs/ACCEPTANCE-2026-09-21.md` und `.json`.
- Skills/Plugins: Kein reproduzierbarer lokaler Defekt (12 Skill-Manifeste, keine defekten Links und keine fehlenden Registry-Pfade); keine Löschung oder Installation.
- Offene Punkte: Die 13 Profile bleiben absichtlich UNVERIFIED und verhindern reale Veröffentlichungsfreigaben; das blockiert nicht den internen Systemabschluss. Kein Commit, Push, Remote- oder Berechtigungswechsel.

## Nachtrag — Lokale Multi-Provider-Vision-Anbindung

- Datum: 2026-09-21. Schreibender Agent: Codex, direkter Nutzerauftrag. Branch/Worktree: `feature/system-core` in `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`. Risiko: strukturelle, aber unaktivierte lokale Adapter-Erweiterung; unabhängiges Review durch Claude steht noch aus.
- Geändert: Neu `tools/vision_providers.py` mit gemeinsamen, fail-closed Adaptern für LM Studio (OpenAI-kompatibles `/v1/models` + `/v1/chat/completions`) und Ollama (`/api/tags` + `/api/chat`). Provider und Modell werden ohne Modell-Default als `VisionSettings(provider, model)` getrennt gesetzt. Vor einer Anfrage wird das genaue Modell beim gewählten Provider ermittelt; Timeouts, Offline-Zustände, unbekannte Modelle und ungültige Antworten schlagen fehl. Es gibt keinen Provider- oder Modell-Fallback. `tools/vision_qc.py` verwendet den Adapter nur bei expliziter Angabe von `--vision-provider` und `--vision-model`; Production-QC bleibt unverändert standardmäßig deaktiviert.
- Capability: `contracts/vision-capability-status.json` speichert nur unabhängige semantische Testergebnisse. Der belegte Status für `ollama/qwen2.5vl:3b` ist `FAIL` mit Verweis auf die Gegenprüfung. Technische Discovery führt `installed`, `inference` und `vision_capability` getrennt; alle nicht geprüften Modelle, einschließlich Gemma, bleiben `NOT_TESTED`.
- Tests: Neu `tests/test_vision_providers.py`: LM Studio/Ollama online/offline, Modell vorhanden/nicht vorhanden, API-Antwort, Timeout, ungültige Antwort, Base64/Data-URL-Vision-Input, getrennte Capability-Statusdatei und kein Fallback. Fokussiert 43 PASS; komplette Suite außerhalb der Sandbox 412 PASS. Ruff und mypy für die neuen/berührten Python-Dateien PASS; `npm run typecheck` PASS; `git diff --check` PASS.
- Live-Discovery: LM Studio auf `127.0.0.1:1234` OFFLINE (connection refused). Ollama auf `127.0.0.1:11434` ONLINE; u. a. `qwen2.5vl:3b` und die tatsächliche lokale Gemma-ID `gemma4:e4b` gefunden. Keine Modelle installiert/heruntergeladen, keine Secrets geändert, kein Commit/Push/Deployment.
- Nächster Schritt: Vor einer möglichen Production-QC-Aktivierung einen realen Capability-Test für das konkret gewählte LM-Studio-/Gemma-Modell durchführen und unabhängig reviewen; bis dahin bleibt Production-QC deaktiviert.

## Nachtrag — Lokale Medien-Härtung und n8n-Loopback

- Datum: 2026-09-27. Task-ID: `LOCAL-MEDIA-HARDENING-20260927-01`.
  Aktions-Hash: `3f92501c96b751ac732248adef1f5f0a0ae6412b97de572f6bae88cd0ff457a9`.
  Schreibender Agent: Codex, direkter Nutzerauftrag. Risiko: Stufe 1; lokale,
  reversible Konfigurationsänderungen plus ausdrücklich beauftragte Löschung
  eines verifizierten unvollständigen Alt-Caches.
- Gelöscht: `~/.cache/huggingface/hub/models--dgrauet--ltx-2.3-mlx-q8`
  (acht `.incomplete`-Dateien, zusammen rund 5 GB). Der aktive
  `MrMofer/ltx-2.5-mlx-q8`-Cache blieb vorhanden.
- Geändert: `tools/subtitle_translate.py` erzwingt für Argos' gebündelten
  Stanza-Satztrenner `download_method=None`. Dadurch werden ausschließlich die
  bereits installierten lokalen de↔en-Modelle verwendet und kein GitHub-Update
  mehr angefragt. `tests/test_subtitle_translate.py` enthält den fokussierten
  Regressionstest für diese Eigenschaft.
- Außerhalb des Repositories geändert:
  `~/Library/LaunchAgents/com.user.n8n.plist` bindet n8n über
  `N8N_LISTEN_ADDRESS=127.0.0.1`; `~/.local/bin/ai-runtime-check` wählt für den
  Ollama-Probelauf dynamisch das kleinste installierte Modell und akzeptiert
  aktive n8n-Workflows nur bei bestätigter Loopback-Bindung;
  `~/.local/bin/ai-health-check` ignoriert flüchtige Codex-PATH-Einträge und
  prüft Symlinkziele socket-sicher.
- Verifikation: Argos-Regressionstest `1 passed`; echter de→en-Lauf bei
  blockiertem Netzwerk erfolgreich (`The local system works.`); n8n-Health
  `{"status":"ok"}` und Listener ausschließlich `127.0.0.1:5678`;
  `ai-runtime-check` 0 Fehler; `ai-health-check` 0 Fehler/1 bekannte Warnung
  (66 bereits zuvor uncommittete Pfade im Repository).
- Bekannte Altlast: Der vollständige Lauf von `tests/test_subtitle_translate.py`
  hat weiterhin zwei bereits vor diesem Auftrag vorhandene DeepL-Tests, obwohl
  DeepL im aktuellen Tool bewusst entfernt ist. Ergebnis daher `3 passed, 2
  failed`; diese widersprüchlichen fremden Änderungen wurden nicht gelöscht.
  Ruff meldet ebenfalls bereits vorhandene Zeilenlängen. Kein Commit, Push,
  Upload oder Plattformzugriff ausgeführt.
- Nächster Schritt: Öffentliche Social-/Shop-Webhooks später über einen
  abgesicherten HTTPS-Reverse-Proxy oder Tunnel mit Authentifizierung
  bereitstellen; Port 5678 selbst bleibt lokal.

### Nachtrag — DeepL-Reste entfernt

- Datum: 2026-09-27. Auf ausdrücklichen Nutzerauftrag wurden die zwei veralteten
  DeepL-Tests sowie DeepL-Erwähnungen aus aktivem Tool-Text, Registry und
  Projektanleitung entfernt. Argos ist jetzt die lokale Standardengine;
  Gemini ist nur noch eine ausdrücklich gewählte Cloud-Option.
- Prüfung: `tests/test_subtitle_translate.py` jetzt vollständig `4 passed`;
  Registry-JSON gültig; `git diff --check` bestanden; keine aktiven exakten
  `DeepL`-/`DEEPL_API_KEY`-Treffer außerhalb historischer Handoff-, Aufgaben-
  und Review-Protokolle. Credential-Dateien wurden nicht gelesen oder verändert.

### Nachtrag — Z-Image-Qualitätsmodus optimiert

- Datum: 2026-09-27. Schreibender Agent: Codex, direkter Nutzerauftrag.
- `~/manuell.sh`: Bildgenerierung bietet jetzt Qualität (9 Schritte,
  Standard/empfohlen) und Schnell (4 Schritte). Erweiterte Einstellungen
  unterstützen einen optionalen Negativ-Prompt; Text-zu-Bild und
  Bild-zu-Bild verwenden dieselbe Auswahl.
- `tools/z_image.py`: Standard von 4 auf die vom installierten MLX-Z-Image-
  Backend dokumentierten 9 Turbo-Schritte gesetzt; Projektanleitung angepasst.
- Verifikation: Bash-Syntax, Python-Kompilierung, `manuell.sh --check` und
  `git diff --check` bestanden. Echter lokaler 512×512-Render mit 9 Schritten,
  Seed und Negativ-Prompt erfolgreich in 29,7 Sekunden; temporäres Testbild
  anschließend gelöscht. Kein Cloud-Aufruf, kein Commit oder Upload.

### Nachtrag — Lokale Ton- und Videoqualität optimiert

- Datum: 2026-09-27. Schreibender Agent: Codex, direkter Nutzerauftrag.
- `~/manuell.sh`: Kokoro-Sprachausgabe bietet jetzt verlustfreie 24-Bit-WAV
  als empfohlenen Standard und MP3 als kompakte Qualitätsoption. Das
  Videomenü bietet Querformat 704×480, Hochformat 480×704 und Quadrat 576×576
  sowie Distilled (geprüft/Standard), Two-stage (Qualität) und Two-stage HQ
  (Maximum). Breite/Höhe werden explizit an den LTX-Wrapper übergeben.
- `tools/kokoro_tts.py`: WAV-Zwischen-/Zieldaten werden als PCM_24 geschrieben;
  MP3 nutzt `libmp3lame -q:a 0`. Projektanleitung entsprechend ergänzt.
- Verifikation: Bash-Syntax, Python-Kompilierung, LTX-CLI-Modi,
  `manuell.sh --check` und `git diff --check` bestanden. Reale deutsche
  Kokoro-Ausgabe als WAV (`pcm_s24le`, 24 Bit, 24 kHz) und MP3 (maximale
  VBR-Qualität) erfolgreich; temporäre Testdateien gelöscht.
- Distilled LTX-2.5 bleibt der bereits live geprüfte Standard. Two-stage und
  Two-stage HQ sind vom lokalen Runtime-Code unterstützt und nun auswählbar,
  wurden in diesem kurzen Auftrag aber nicht durch einen mehrminütigen Render
  erneut live ausgeführt. Kein Cloud-Aufruf, Commit oder Upload.

### Nachtrag — Kreativ-Studio Gesamtprüfung und Bedienhärtung

- Datum: 2026-09-27. Schreibender Agent: Codex, direkter Nutzerauftrag.
- Außerhalb des Repositories wurde `~/manuell.sh` erweitert: versionierte
  Arbeitskopien externer Bildvorlagen, HEIC/HEIF/AVIF→PNG, geprüfte Auswahl
  von Audio-/Videodateien, Whisper Medium/Small, Kokoro/Piper sowie
  Argos de↔en als leichter vollständig lokaler Übersetzungspfad.
- Der Systemcheck zeigt Medien-/Sprachmodelle, freien Speicher,
  Ollama-RAM-Belegung und Qualitätsprofile. Die Rückgabe von
  `show_active_job` wurde korrigiert, damit ohne Aktivjob wieder die letzte
  Jobhistorie erscheint.
- Verifikation: Bash-Syntax, `--check`, `--help`, Menü-/Abbruchpfade,
  Argos de→en, Audioauswahl, Job-Historie, Bildkopie, echter AVIF→PNG-Import
  und reale Piper-WAV bestanden. Whisper Medium ist lokal gecacht; der
  erneute Sandbox-Lauf konnte wegen des erwarteten fehlenden Metal-Geräts
  nicht rechnen. Keine Repository-Quelldatei wurde für diesen Nachtrag
  verändert; kein Download, Cloud-Aufruf, Commit, Push oder Upload.
- SHA-256 `~/manuell.sh`:
  `4daffd7e075eff925d81d1729985f32e22fca0f8cc9be0fbc82c572b411d92ce`.

### Nachtrag — Grafisches lokales Kreativ-Studio (MVP)

- Datum: 2026-09-27. Schreibender Agent: Codex, direkter Nutzerauftrag.
- Neues separates Projekt: `~/PROJEKTE/kreativ-studio/`; Starter:
  `~/.local/bin/kreativ-studio`. Das Dashboard verändert keine Toolkit-
  Quelldatei, sondern ruft die vorhandenen lokalen Wrapper und die gemeinsame
  `manuell`-Jobsperre auf.
- Enthalten: Bild, Video, Kokoro/Piper, Whisper Medium/Small, Argos de↔en,
  Systemstatus und Ergebnisliste. Nur `127.0.0.1:7865`, kein Share-Link,
  Analytics/Modelldownloads aus, sensible Home-Verzeichnisse blockiert.
- Verifikation: Selbsttest vollständig grün; Python-/zsh-Syntax; echter
  Sperren- und Piper-Job; Argos de→en; visuelle Chrome-Prüfung bestanden.
  Keine Installation, kein Cloud-Aufruf, Commit, Push oder externer Upload.
- Vollständige Übergabe und spätere Nicht-Ziele stehen in
  `~/PROJEKTE/kreativ-studio/AI_HANDOFF.md`.

### Nachtrag — Lokale Audio-Routen und ElevenLabs-Entfernung

- Task: `KIS-AUDIO-OFFLINE-20260928-04`; freigegebener Aktions-Hash:
  `84792fdd7f6cbbef074a3806ee4f376b344645cd29f155e78c71acf2250f2f7c`.
- ElevenLabs-Dependency, Skill und aktive Redub-/Setup-/Voiceover-Anleitungen
  entfernt. `uv.lock` enthält `mlx-audio==0.5.4` als optionales `local-voice`
  Extra; `uv sync --extra local-voice` erfolgreich, ElevenLabs wurde aus dem
  Projekt-venv entfernt.
- Kokoro: lokaler deutscher WAV-Smoke am 28.09.2026 erfolgreich.
- Lokales Qwen3-TTS Voice Cloning/Dubbing: Codepfad und Consent-Schranke
  implementiert und unabhängig geprüft. Modellabruf von Hugging Face blieb trotz
  Wiederaufnahme bei 259 MB der 1,83-GB-Hauptgewichte hängen; daher bleiben
  Dubbing und Voice Cloning **PLANNED / NOT ACTIVE**, bis Cache und lokaler
  Ende-zu-Ende-Smoke vollständig sind. Im HF-Cache liegen fortsetzbare
  unvollständige Downloads.
- Schutzkorrekturen: Ausgabe kann Referenz-/Quelldateien nicht überschreiben;
  Orchestrator blockiert Premium-Ausführung vor jeder Verzeichnis- oder
  Statusänderung. Unabhängige Read-only-Prüfung ohne Findings für diese Guards.
- Kein API-Key, Konto, Cloud-TTS, Upload oder bezahlter Anbieter aufgerufen;
  keine Commit-/Push-Aktion. Bestehende unabhängige Änderungen im Arbeitsbaum
  wurden beibehalten.

### Aktualisierung 28.09.2026 — Qwen3-TTS lokal fertiggestellt

- Kostenloser HF-Download über `HF_HUB_DISABLE_XET=1` abgeschlossen;
  lokaler Cache enthält `model.safetensors` (1.829.344.448 Bytes) und den
  Speech-Tokenizer (682.293.092 Bytes). Das optionale `local-voice` Extra ist
  installiert.
- Qwen3-TTS Einzelsynthese mit synthetischer Kokoro-Referenz erfolgreich.
- Lokaler Dubbing-E2E-Smoke erfolgreich: MLX Whisper tiny → Argos en→de →
  Qwen3-TTS, zwei Segmente, MP4 mit H.264/AAC, 8,491 s. Deutsche Whisper-Small-
  Rückprobe war verständlich, einzelne Wörter aber fehlerhaft; QC/Hörprüfung
  bleibt je Produktion erforderlich.
- Status im kanonischen Organigramm auf **LIVE / VERIFIED** aktualisiert.
  Die Claude.ai-Artefaktseite ist damit nicht automatisch geändert.
- Nur lokale synthetische Teststimme und Testclip verarbeitet; keine Cloud-API,
  kein Upload, keine Zahlung. Kein Kreativ-Studio geändert.

### Übergabe an Claude Code — Claude.ai KI-Systemorganigramm aktualisieren

- **Nächster Auftrag für Claude Code:** Aktualisiere die sichtbare
  Audio-/Speech-Statusanzeige im Artefakt
  <https://claude.ai/code/artifact/3f508f27-5b7b-45a0-9583-a975418fc122>,
  damit sie dem kanonischen lokalen Stand in `~/docs/KI-SYSTEM-ROUTING.md` und
  `~/docs/KI-UND-ENTWICKLUNGSSYSTEM-ORGANIGRAMM.md` entspricht.
- Kokoro TTS als **aktiv** anzeigen (deutsche WAV-Erzeugung lokal geprüft).
- Dubbing / Voice Cloning **aktiv** anzeigen: Qwen3-TTS ist vollständig lokal
  gecacht; der MLX-Whisper → Argos → Qwen3-TTS Ende-zu-Ende-Smoke war
  erfolgreich. Voice Cloning verlangt bestätigte Rechte/Einwilligung; Dub und
  Übersetzung vor Veröffentlichung anhören und prüfen.
- ElevenLabs vollständig aus aktiven Routen/Optionen entfernen, nicht nur als
  deprecated markieren. Historische Dokumentation darf bleiben.
- Das separate Kreativ-Studio nicht verändern. Nach der Artefaktänderung die
  sichtbare Seite bzw. einen Screenshot zur Kontrolle zeigen.
- Diese Notiz ist eine lokale Übergabe, keine direkte Nachricht und kein
  Nachweis, dass die Claude.ai-Artefaktseite bereits geändert wurde.

### Status 29.09.2026 — Claude.ai-Artefakt weiterhin offen

- Hannibal meldete, dass die beiden Audio-Badges im Claude.ai-Artefakt weiterhin
  gelb angezeigt werden. Codex hat nur die lokale Kopie
  `~/Downloads/KI-Systemorganigramm.html` aktualisiert; das ändert die
  Online-Artefaktseite nicht.
- Codex hat den angegebenen Artefaktlink in seiner Browser-Sitzung geöffnet;
  er leitete dort zu einer Claude-Neuchat-Seite um. Es gab keinen angemeldeten
  Artefaktzugriff und keine Änderung an der Online-Seite.
- **Offener Auftrag für Claude Code nach Wiederherstellung des Kontingents bzw.
  eines angemeldeten Zugriffs:** die oben beschriebene Audio-/Speech-Anzeige im
  Artefakt selbst ändern und die aktualisierte Ansicht als Screenshot zeigen.
  Kokoro und lokales Dubbing/Voice Cloning müssen aktiv erscheinen; ElevenLabs
  aus aktiven Routen/Optionen entfernen. Das Kreativ-Studio bleibt unberührt.
- Diese Übergabe wartet auf Claude-Zugriff; sie löst weder einen automatischen
  Start noch eine Authentifizierung oder Änderung aus.

### Nachtrag — Qwen3-Audiohinweise mit lokalen Modulen abgeglichen

- Task-ID: `KREATIV-QWEN3-STUDIO-AUDIO-20260928-01`. Die lokale
  Studio-Erweiterung bleibt ein eigenes Projekt; dieses Toolkit-Handoff hält
  nur die CLI-Grenze und Dokumentation fest.
- Nach benannter Stufe-2-Zustimmung von Code Reviewer (read-only), gebunden an
  den Aktions-Hash
  `69682f36765b28b704329a06db0b9eb20814964f1fbcd0900443a4c5b5439bb1`, wurde
  `CLAUDE.md` in den Audioabschnitten korrigiert: Voiceover listet die
  tatsächlich angebotenen lokalen Provider, die Beispiele verwenden
  `qwen3-local` bzw. `tools/redub.py`, und der separate Standalone-Cloudpfad
  ist klar optional und potenziell kostenpflichtig.
- Finale unabhängige Read-only-Prüfung: keine Blocker. `voiceover.py --help`
  bestätigt `kokoro`, `piper`, `qwen3-local`; `redub.py --help` bestätigt die
  dokumentierten lokalen Referenz-/Consent-Flags; `git diff --check -- CLAUDE.md`
  sauber. Kosten/Downloads/Cloud-Aufrufe: 0. Kein Commit oder Push.
- Nachher SHA-256 für `CLAUDE.md`:
  `b5c1aa9937d6eeaa9a870a7b3bb732ce6e8fc33bb976c9571cc1c768da9ad40f`.

### Blender CLI-/UI-Prototyp — umgesetzt und lokal smoke-geprüft

- Task-ID: `BLENDER-TOOLKIT-PROTOTYPE-20260929-01`. Branch `feature/system-core`,
  Basis `84cf38062299a5115cb4fc5e41800783729c66e8`. Schreiber: Codex 1.
- Umfang: Blender-5.2-Add-on mit `Video Studio`-Workspace, persistenten
  Starteinstellungen sowie gemeinsamem UI-/Headless-Pfad unter
  `tools/blender_cli/`. Nach dem zunächst dokumentierten Setup-Blocker setzte
  Hannibal die Arbeit ausdrücklich fort; Workspace-Löschung läuft über
  `workspace.delete_all_others` und wird nach einer UI-Timer-Runde geprüft.
- Keine zusätzlichen Pakete installiert; kein Modell/Cloud-Aufruf, Upload,
  Commit oder Push.
- Backup vor Einrichtung:
  `projects/blender-prototype/backups/blender-5.2/20260929-2125/`;
  SHA256-Prüfung beider gesicherten Dateien bestanden. Blender add-on symlink
  liegt unter `~/Library/Application Support/Blender/5.2/scripts/addons/`;
  `userpref.blend` hat das Add-on aktiviert. Die erzeugte `startup.blend` ist
  zusätzlich vor Anpassungen gesichert unter
  `projects/blender-prototype/backups/blender-5.2/startup-repair/`.
- Startdatei-Liveprüfung: nur Workspace `Video Studio`; Add-on enabled; EEVEE,
  1280×720, 24 fps, 72 Frames, metrische Meter; leerer Mesh-Start; 3D-View-
  Sidebar geöffnet. Erwartete Editoren: View 3D, Outliner, Properties, Timeline.
- Laufzeitprüfung: synthetisches OBJ-Asset lief über den Headless-Pfad und die
  Add-on-Operatoren vollständig durch Import → Szene prüfen → PNG-Render → H.264-
  MP4-Export; zusätzlich `.blend`-Export über CLI. Beide Renderpfade Exit 0;
  `ffprobe` bestätigte H.264, 320×320, 24 fps und einen Frame. FFmpeg 9.0.2 mit
  `libx264` live vorhanden. Headless-Aufruf benötigt auf diesem Mac
  `--gpu-backend metal`; ohne den Override trat vor Python ein Blender-Crash auf.
- Prüfnachweis: Backup-SHA256 und Startdatei-Backup-SHA256 verifiziert;
  `git diff --check` ohne Befund. E2E-Smokes decken OBJ ab, nicht alle
  beworbenen Austauschformate. Kein unabhängiger Peer-Review. Der bestehende
  Arbeitsbaum war vor dem Ticket umfangreich verändert; bestehende Änderungen
  wurden erhalten.
- Nächster Schritt: weitere echte FBX/GLB/GLTF/STL-Assets bei Bedarf separat
  durch den Importpfad führen; dieser erste Prototyp ist für den lokalen OBJ-
  Render-/Video-Clip-Pfad end-to-end nachgewiesen.

### Blender-Agentenschnittstelle — JSON-Vertrag ergänzt

- Task-ID: `BLENDER-AGENT-CONTRACT-20260929-01`. Umsetzung durch Codex 1 im
  selben freigegebenen Video-Toolkit-Arbeitsumfang; keine Blender-Installation,
  User-Preferences oder Startdatei geändert.
- `tools/blender_cli/run_pipeline.py` liefert jetzt nach Erfolg eine
  `PIPELINE_RESULT`-JSON-Zeile (`schema_version: 1`) mit Input, Validierung,
  Renderparametern und Artefaktpfaden. Pipeline-Fehler liefern
  `PIPELINE_ERROR`-JSON nach stderr und Exit-Code 1. Rendermaße werden vor der
  Validierung gesetzt, Mindestmaße sind 16×16.
- `tools/blender_cli/AGENT-GUIDE.md` dokumentiert den gemeinsamen Aufruf für
  Claude Code, Codex und lokale Python-Module einschließlich Fehler- und
  Ergebnisvertrag. Lokale Modelle werden nicht automatisch aufgerufen.
- Verifikation: Blender 5.2.2 Headless, OBJ → Szeneprüfung → 1 Frame → H.264
  MP4, Exit 0; JSON-Ergebnis enthielt die erwarteten Pfade und 320×320/24fps.
  `ffprobe` bestätigte H.264, 320×320, 24/1 fps. `git diff --check` sauber.
  Blender stürzte im Sandbox-Lauf einmal vor Skriptstart ab; der Live-Lauf
  außerhalb der Sandbox bestand. Kein unabhängiges Review.
- Formatmatrix ergänzt: synthetische Blender-Assets `.blend`, `.fbx`, `.glb`,
  `.gltf`, `.obj`, `.stl` jeweils durch Headless-Import, Validierung, 1-Frame-
  Render und MP4-Export geführt; alle sechs Exit 0. Für alle sechs Ausgaben
  bestätigte `ffprobe` H.264, 320×320 und 24/1 fps. Das belegt Basisimport,
  nicht beliebige Material-/Rig-/Animationskompatibilität realer Produktionsassets.
- Bedienpfad harmonisiert: Add-on-Dateiauswahl filtert jetzt unterstützte
  3D-Dateien einschließlich ZIP; Beschriftungen trennen Frame-Render und MP4-
  Export; eigener Button sichert eine neue `.blend`-Kopie. Die Szenenprüfung
  verwendet die in der Toolkit-Seitenleiste gewählten Maße.
- Meshy-ZIP unterstützt ein einzelnes GLB mit temporärem, größenbegrenztem
  Streaming-Import; Archivpfade werden nie extrahiert. Synthetischer ZIP-Test
  mit `../../outside/renamed.glb` bestand Import → Prüfung → Render → MP4; auch
  der Add-on-Operatorpfad ZIP → Prüfung → Render → MP4 + `.blend` lief ohne
  Fehler. Ein echtes Meshy-Archiv wurde nicht verwendet.
- Meshy-MCP/Cloud-API wurde nicht eingerichtet oder aufgerufen. Es bleibt eine
  optionale, konten- und kreditgebundene Erweiterung; lokale GLB/ZIP-Dateien
  funktionieren ohne Meshy-Bridge.
- Keine Pakete, Cloud-Dienste, Commits oder Pushes.

### BLOCKIERT VOR INSTALLATION — unabhängiger Meshy-Plugin-Security-Review

- Task-ID: `MESHY-PLUGIN-INSTALL-20260929-01`.
- Nutzerauftrag: Meshy Blender Plugin installieren und aktivieren. Der
  Bridge-Server soll dabei **nicht gestartet** werden; kein Meshy-API-Aufruf,
  keine Kontoanmeldung und kein Credit-Verbrauch.
- Paket: `/Users/constantinbarhoumi/Downloads/meshy-blender-plugin-v0.6.1.zip`
  SHA-256 `74e6b77bcb9359d127cf5dcd5d7fdf216fafa280c5cace5090adbe6c6c34e0ec`.
  Entpackter Ordner stimmt dateiweise mit dem ZIP überein. Add-on liegt noch
  nicht im Blender-Addon-Verzeichnis und wurde nicht aktiviert.
- Prüfhinweis für Read-only-Reviewer: `BridgePanel.py` bindet in Zeile 203 mit
  `TCPServer(("", 5324), ...)` an alle Interfaces; `/import` verarbeitet
  POST-Daten, nimmt darin eine `url` entgegen und lädt sie per `requests.get`
  (Zeilen 93–123). Der Handler verlangt keine Authentifizierung. Bitte
  unabhängig bewerten, ob Installation/Aktivierung bei dauerhaft gestopptem
  Bridge-Server vertretbar ist, welche konkreten Schutzmaßnahmen fehlen und ob
  das Add-on in diesem Umfang freigegeben werden kann. ZIP-Inhalt nur lesend
  prüfen; keine Installation, Aktivierung oder Bridge-Ausführung.
- Aktions-JSON, kanonisch sortiert und kompakt:
  `{ "action": "Install and enable Meshy Blender plugin v0.6.1 in Blender 5.2 user add-ons; leave its Bridge server stopped", "expected_side_effects": "Add-on code becomes available to Blender and loads when enabled; no bridge listener, API call, Meshy account access, or credit usage", "resource": "/Users/constantinbarhoumi/Downloads/meshy-blender-plugin-v0.6.1.zip", "resource_sha256": "74e6b77bcb9359d127cf5dcd5d7fdf216fafa280c5cace5090adbe6c6c34e0ec", "scope": "Blender 5.2 per-user add-on installation and enablement", "task_id": "MESHY-PLUGIN-INSTALL-20260929-01" }`
- Aktions-SHA-256: `c3c6bbb67d6dd7b2b67ddeaac608763801e8b75ce8867350aab4bd57ab2241f0`.
- Erforderliche Übergabe: Claude Code oder anderer qualifizierter,
  modellfremder Reviewer prüft diesen festen Paketstand ausschließlich lesend
  und gibt explizit approve/reject für Task-ID und Aktionshash zurück. Die im
  Chat gezeigte vorherige Prüfung meldet denselben Bridge-Befund, ihre
  Modellunabhängigkeit ist jedoch nicht nachgewiesen. Bis zum neuen Review
  bleibt die Installation gesperrt. Bei `approve` für genau diesen Hash den
  bereits beauftragten Install-/Enable-Schritt ausführen, Bridge dabei gestoppt
  lassen; bei `reject` nicht installieren und Befund an Hannibal zurückgeben.
- Schreiber dieser Handoff-Notiz: Codex 1. Keine Paket-, Blender- oder
  Preference-Änderung vorgenommen.

## Nachtrag — Arabische TTS-Dialekte mit Azure Speech

- Datum: 2026-10-10. Task-ID: `ARABIC-TTS-AZURE-20261010-01`.
  Aktions-Hash: `891328f1f206511bdfc64917eb839bc559fc98ccb889b9a2ece00cef1a8895f0`.
- Schreibender Agent: Codex 1. Branch/Worktree: `chore/ltx25-adapter` /
  `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`. Der Arbeitsbaum war
  bereits umfangreich verändert; alle nicht auf diese Aufgabe bezogenen
  Änderungen wurden erhalten.
- Umfang: optionaler Azure-Speech-TTS-Adapter für Tunesisch (`ar-TN`),
  Algerisch (`ar-DZ`), Marokkanisch (`ar-MA`), Libanesisch (`ar-LB`),
  Syrisch (`ar-SY`) und Ägyptisch (`ar-EG`). `ar-msa` ist ausdrücklich eine
  Saudi-Stimmen-Annäherung und keine behauptete neutrale MSA-Stimme.
- Geändert: `tools/azure_tts.py`, Azure-spezifische Integration in
  `tools/voiceover.py`, `tests/test_azure_tts.py`,
  `.claude/commands/generate-voiceover.md`, `_internal/toolkit-registry.json`,
  `CLAUDE.md` sowie dieser Handoff-Nachtrag. Azure bleibt optional; Live-Aufrufe
  erfordern `--confirm-cloud` und vorhandene `AZURE_SPEECH_KEY`/
  `AZURE_SPEECH_REGION`. Keine Credentials gelesen/geschrieben, kein Azure-
  Request, keine Ressourcenerstellung und keine Abrechnung.
- Verifikation: `uv run pytest -q tests/test_azure_tts.py` (6 passed),
  `uv run ruff check tools/azure_tts.py tests/test_azure_tts.py`,
  `uv run python -m py_compile tools/azure_tts.py tools/voiceover.py
  tests/test_azure_tts.py`, Registry-JSON-Parsing und `git diff --check`
  bestanden. Azure-Dry-Runs für `ar-TN` und `ar-msa` zuvor bestanden; kein
  Live-Test mangels Azure-Key/Region.
- Review: Hannibal beauftragte ein unabhängiges lokales OpenCode/Devstral-
  Read-only-Review. Mehrere Versuche scheiterten technisch (OpenCode-Read-Tool
  mit ungültigem Schema; CLI übergab Dateianhänge nicht an das Modell). Es liegt
  daher kein unabhängiger Review-Befund vor; Änderung bleibt `umgesetzt`, nicht
  `geprüft`. Keine Selbstprüfung als Ersatz gewertet.
- Nächster Schritt: Unabhängigen Read-only-Review auf einem funktionierenden
  OpenCode-Prüfpfad nachholen. Bei Befunden Patch korrigieren, Prüfungen und
  Review auf neuem Prüfstand wiederholen. Kein Commit, Push, Deployment oder
  Azure-Liveaufruf ausgeführt.

## Nachtrag — LTX-2.5-MLX Clip-Fortsetzung und Registry-Korrektur

- Datum: 2026-10-20. Task-ID: `LTX25-MLX-CONTINUATION-20261020-01`.
  Schreiber: Codex 1. Arbeitsverzeichnis:
  `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`.
- `tools/ltx25_mlx_adapter.py` unterstützt jetzt `--continue-from`: FFmpeg
  dekodiert das letzte Frame des vorherigen Clips verlustfrei als temporäres
  PNG; der bestehende MLX-I2V-Pfad nutzt es als First-Frame-Anker und räumt es
  nach Erfolg, Fehler oder Timeout wieder auf. `--image` und `--continue-from`
  schließen sich aus; fehlende Eingabedateien scheitern vor Modellstart.
- `_internal/toolkit-registry.json` verweist für `ltx2_local` nicht länger auf
  die nicht existente Datei `tools/ltx2_local.py`, sondern auf den realen
  Adapter. `CLAUDE.md` dokumentiert den Fortsetzungsaufruf. Gepinnter Runtime,
  Modellgewichte und bestehende Standardparameter blieben unverändert; keine
  Downloads, Cloud-Aufrufe, Kosten, Commits oder Pushes.
- Verifikation: fokussiert `7 passed`; Ruff, Python-Compile, Registry-JSON und
  `git diff --check` bestanden. Ein realer synthetischer Rot→Blau-Clip bestätigte
  die Endframe-Dekodierung (extrahierter 1×1-RGB-Wert `0 0 255`). Ein echter
  MLX-Render war in der Sandbox nicht möglich, weil Metal dort nicht verfügbar
  ist. Gesamtsuite: `435 passed, 9 failed`; alle neun Fehler sind vorhandene
  Umgebungs-/Fremdbaustellen (Node/Ollama-Status, fehlendes Media-Remote,
  Egress-Allowlist sowie durch Sandbox blockierte Chromium-/Remotion-Starts),
  nicht im LTX-Änderungspfad.
- Kein unabhängiger Review durchgeführt; die Änderung ist umgesetzt und lokal
  verifiziert, aber nicht unabhängig abgenommen.

## Nachtrag — Lokale LTX-2.5-Mehrclip-Kette aktiviert

- Datum: 2026-10-20. Task-ID: `LTX25-LOCAL-CHAIN-20261020-02`.
  Schreiber: Codex 1. Branch/Worktree: `chore/ltx25-adapter` /
  `/Users/constantinbarhoumi/PROJEKTE/video-toolkit`.
- `tools/chain_video.py` verwendet jetzt standardmäßig und ausschließlich den
  vorhandenen lokalen `ltx25_mlx_adapter.py` statt des älteren Cloud-LTX-Pfads.
  Der erste Clip erhält das gewählte Startbild; jeder Folgeclip wird direkt mit
  `--continue-from` an den vorherigen Clip übergeben. Endframe-Dekodierung,
  temporäre Dateien und frühe Eingabeprüfung besitzen damit nur noch eine
  verantwortliche Implementierung im Adapter.
- Registry und CLI-Dokumentation beschreiben den tatsächlich aktiven lokalen
  Mehrclip-Pfad. Es wurden keine Modelle installiert, keine Cloud-Dienste
  aufgerufen und keine Kosten, Commits oder Pushes ausgelöst.
- Verifikation: fokussiert `9 passed`; Ruff, Python-Compile, Registry-JSON und
  `git diff --check` bestanden. Kein echter MLX-Render, weil die Änderung nur
  das bereits getestete Adapter-Routing betrifft und ein vollständiger Render
  mehrere Minuten GPU-Zeit beansprucht.
- Kein verlustbehafteter Post-Render-Pixel-Lock ergänzt: Dafür müsste jeder
  Folgeclip vollständig neu kodiert werden. Der bereits vorhandene verlustlose
  PNG-Anker ist die fokussierte Qualitätsverbesserung ohne zusätzliche
  Generations- oder Transcoding-Schicht. Kein unabhängiger Review durchgeführt.

## Nachtrag — LTX-Produktionsaussagen gegen Primärquellen abgegrenzt

- Datum: 2026-10-20. Task-ID: `LTX-PRODUCTION-ASSESSMENT-20261020-03`.
  Schreiber: Codex 1. Neue Dokumentation:
  `docs/LTX-PRODUCTION-ASSESSMENT-2026-10-20.md`.
- Übernommen wurden die offiziell belegten Prinzipien Open Weights, lokale
  Inferenz sowie upstream verfügbares Standard-/IC-LoRA-Training. Der lokale
  MLX-Adapter bleibt davon klar getrennt: LoRA-Training ist dort nicht
  installiert oder live verifiziert.
- Nicht als aktiver Systemstatus übernommen wurden native Alpha-Ausgabe,
  Echtzeit auf dem M4 Pro, garantierte Final-Pixel-Qualität und das nicht über
  offizielle Quellen bestätigte Asteria-Pilotprojekt. Der lokale Messwert von
  rund 191 Sekunden für 97 Frames widerspricht einer Echtzeitdarstellung des
  vorhandenen Setups.
- Keine Runtime-, Modell-, Pipeline- oder Cloud-Änderung; keine Downloads,
  Kosten, Commits oder Pushes. Dokumentprüfung und `git diff --check`
  bestanden. Kein unabhängiger Review durchgeführt.

### Quellenkorrektur — Alpha Gen und Layout to Render offiziell belegt

- Die nachgereichten Quellen bestätigen zwei offizielle LTX-2.5-VFX-Betas:
  Layout to Render für 3D-/Referenzvideo-geführte Frames und Alpha Gen als
  separates RGB-zu-Graustufenmatte-IC-LoRA. Die vorherige pauschale Aussage,
  Alpha sei nicht offiziell belegt, wurde korrigiert.
- Weiterhin nicht zulässig ist die Behauptung, der normale lokale MP4-Adapter
  liefere native Transparenz. Alpha Gen benötigt einen eigenen IC-LoRA-Lauf;
  das zugangsbeschränkte Modell ist lokal nicht vorhanden und wurde im
  gepinnten MLX-Pfad nicht live getestet. Offizielle Grenzen: maximal 145
  Frames, maximal 1920×1088, keine Objektwahl per Prompt oder Maske.
- Der MLX-Runtime-Quellstand besitzt grundsätzlich IC-LoRA und LoRA-Fusion,
  was eine spätere technische Prüfung sinnvoll macht. Es erfolgten bewusst
  kein Hugging-Face-Login, keine Lizenzannahme, kein Download und kein Render.

### Systementscheidung — VFX-Module sichtbar, aber fail-closed

- `ltx25_layout_to_render` wurde in der Registry als `planned` und
  `ltx25_alpha_gen` als `blocked` erfasst. Beide Einträge besitzen konkrete
  Aktivierungsgates; keiner ist derzeit routbar.
- Grund: Der vorhandene MLX-IC-LoRA-Pfad unterstützt zwar LoRA-Fusion und
  Referenzvideos, ist aber zweistufig; `--skip-stage-2` erzeugt laut lokaler
  CLI nur halbe Auflösung. Das ist kein Nachweis für die von Alpha Gen
  geforderte native, framegleiche Matte.
- Aktiver Standard bleibt LTX-2.5-MLX für lokale Previsualisierung, I2V und
  Mehrclip-Fortsetzung. Der veraltete Cloud-/Kostenstatus des Registry-Eintrags
  `chain_video` wurde auf den bereits implementierten lokalen Adapter korrigiert.
  Kein nutzloser Wrapper, Download oder Login wurde ergänzt.

### 2026-10-22 — SOTA Integration: LTX-2.5 Motion Trajektorien, SDR-to-HDR IC-LoRA & Dispatcher Härtung

- **Schreiber:** Antigravity CLI
- **Auftrag:** Vollständige Integration und Fertigstellung der LTX-2.5 Evaluierungserkenntnisse (DEV vs. Distilled Motion Profiling, SDR-to-HDR IC-LoRA) in das kanonische Playbook, den Dispatcher und die Agentenskills.
- **Durchgeführte Arbeiten:**
  1. `docs/SOTA-AI-MODELS-2026.md`:
     - Abschnitt 1.3: LTX-2.5 Kinematische Trajektorien (DEV 40-Step für Workspace-Stabilität & Feinkontakt vs. Distilled 8–12 Step für Okklusions-Re-Identifikation; End-Anchor-Metrik $\neq$ Bewegungsgüte).
     - Abschnitt 1.4: LTX-2.5 SDR-to-HDR IC-LoRA Pipeline (ComfyUI V2V Tiled Fusion, ACEScg Half-Float EXR bis Peak 55.0 Luminanz, 10-Bit HLG BT.2020 Master; Anti-Banding-Regel: `streaming encode: ON`, `use_tiled_encode: OFF`).
     - Matrix: SDR-zu-HDR Rekonstruktion (10-Bit) verankert.
  2. `tools/video_generate.py`:
     - `seedance_2_mini` vollwertig in `TIER_MODELS["cloud"]`, `MODEL_TO_TIER` und `MODEL_RATES` (0.03 $/s) registriert.
     - `--motion-profile` (`auto`, `steady-workspace`, `occlusion-recovery`) integriert.
     - Qualitäts-Verdikt mit SOTA Draft- & Mastering-Empfehlungen erweitert.
  3. `~/.agents/skills/sota-media-engine/SKILL.md`:
     - Globaler Skill synchronisiert mit Trajektorien-Profiling und SDR-to-HDR IC-LoRA Pipeline.
- **Verifikation & Qualitätssicherung:**
  - `pytest`: 449 von 449 Tests bestanden (100% grün).
  - `tools/acceptance.py`: 25 von 25 Fähigkeiten (F01–F25) PASS.
  - CLI & Cost-Estimation Smoke-Tests für `seedance_2_mini` und `--motion-profile` erfolgreich validiert.
  - Hannibal Pre-Commit Check & Identity Check PASS.
- **Nächste Schritte / Reviewer:** Unabhängiges Review durch Codex / Hannibal Freigabe für Git Push.
