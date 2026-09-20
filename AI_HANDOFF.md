## Betriebsmodus: INTERN-ONLY. Kein Upload/Publish/Posting, fail-closed (unknown/UNKNOWN), additiv, Assets unveränderlich, keine Cloud/Kosten ohne Freigabe, Personenreferenzen nie an Anbieter ohne Consent, ein Schritt = ein Branch/Commit, kein Push. Einzige spätere Öffnung: release-ready/ nach manueller Freigabe. Stand: Phase 1 abgeschlossen (integration/internal-v1), Phase 2 Schritte 1–5 abgeschlossen (Text-Assets, Routing, Layout-Engine, Subtitle-Burn, Acceptance run2 15/15 PASS); integration/internal-v1 per --ff-only auf feature/capabilities @ 5391a66 vorgezogen, kein Push. Phase 3 (feature/system-core, Schritte 0–6) abgeschlossen: Stack-Härtung, Projektanlage, Referenz-Locks, QC-Verdikt, Kosten-Router, Acceptance run3 18/19 PASS (F13 bleibt bewusst FAIL: Python-Pin 3.12 vs. neue Mindestversion 3.14.7). integration/internal-v1 deshalb NICHT vorgezogen, bleibt @ 45ec154.

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
