# AI Handoff

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
