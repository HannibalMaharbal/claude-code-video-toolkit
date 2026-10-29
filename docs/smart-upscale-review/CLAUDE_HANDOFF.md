# Claude-Übergabe: Smart-Upscale und kontrollierter Live-Test

Stand: 29.10.2026. Arbeitsverzeichnis: `~/PROJEKTE/video-toolkit`; Branch `audit/claude-review`; vorheriger Commit `7ea0600`.

## Auftrag und verbindliche Freigaben

Hannibal möchte einen belegten Live-Test von Seedance 2.5 (480p, 10 s) mit anschließendem ByteDance-Upscale (1080p, Preset aigc). Vor **jedem** kostenpflichtigen Schritt den tatsächlichen Preis abfragen und anzeigen; auf Hannibals ausdrückliche Freigabe für genau diesen Schritt warten. Der Basisclip darf höchstens 30 Credits kosten; darüber nur nach weiterer ausdrücklicher Freigabe. Upload nur nach ausdrücklicher Freigabe und nur des einen Testclips. Keine Wiederholung bei Timeout oder Fehler; zuerst Anbieterstatus und mögliche Abbuchung klären. Commit und Push dieser Übergabe wurden ausdrücklich beauftragt; weitere Veröffentlichungen erfordern Freigabe.

## Gesicherter Stand

- Letzte kostenlose Preisabfrage am 29.10.2026: `seedance_2_5`, Prompt `A slow camera movement`, Dauer 10 s, 480p = 30 Credits. Vor einem Auftrag erneut abfragen; Preise können sich ändern.
- Hannibal hat die Beauftragung des Basisclips nach Vorlage des Preises noch nicht ausdrücklich freigegeben. Kein Job erstellt, kein Testclip hochgeladen, 0 Credits verbraucht.
- ByteDance-Preisabfrage ohne Video scheitert, da `video_references` erforderlich ist. Darum sind Upscale-Preis, Gesamtkosten und Bildqualität nicht belegt.
- Kosten- und Upload-Schutz, getrennte Basisstufe, Timeout- und Download-Fehlerbehandlung wurden implementiert. Automatisches Chaining bleibt bei unbekanntem Gesamtpreis gesperrt.
- Vollständige Testsuite mit Projekt-venv und erforderlichem lokalen Zugriff: `.venv/bin/python -m pytest -q` → 524 bestanden. Die Tests ersetzen keinen Live-Test.
- Modellfremdes unabhängiges Review steht aus. Review-Auftrag: `docs/smart-upscale-review/REVIEW.md`. Der lokale Diff-Snapshot liegt in `scratch/smart-upscale-review/changes.diff`; den veröffentlichten Diff liefert `git show` des jeweiligen Commits.

## Dateien dieses Übergabestands

- `AI_HANDOFF.md`
- `tests/test_smart_upscale.py`
- `tools/higgsfield_video.py`
- `tools/video_generate.py`

Bitte vor einem späteren Commit den aktuellen Git-Status und Diff prüfen und bestehende Nutzeränderungen erhalten. Die oben genannten Review-Dateien nur nach bewusster Entscheidung in ein Repository übernehmen; persönliche oder sensible Daten vor öffentlichem Push prüfen.

## Fortsetzung nach Freigabe

1. Basispreis erneut abfragen; bei mehr als 30 Credits stoppen. Nur mit ausdrücklicher Preisfreigabe den einmaligen Basisjob ausführen und den Clip lokal erhalten.
2. Für die Upscale-Kostenabfrage ist der Upload des Clips erforderlich: vorher separate ausdrückliche Uploadfreigabe einholen. Preis zeigen und auf separate Freigabe für den Upscale warten.
3. Nach Freigabe Upscale einmal ausführen. Bei Fehler oder Timeout Anbieterstatus und mögliche Abbuchung prüfen, niemals automatisch erneut beauftragen.
4. Beide Dateien und gleiche Frames für Hannibals visuellen Vergleich bereitstellen; Auflösung, Größe und Dauer messen. Kosten aus tatsächlich angezeigter Abrechnung belegen.
5. Automatik nur freischalten, wenn ein Test die Einhaltung der Kosten- und Freigabegrenzen belegt. Einen einmaligen Preis nicht als dauerhaft gültig behandeln; bei jedem Auftrag aktuelle Kosten neu prüfen.
6. Vollständige Tests erneut ausführen, modellfremdes Review durchführen und `AI_HANDOFF.md` aktualisieren. Abschluss als Tabelle mit belegt/offen, ohne unbelegte Prozentwerte.
