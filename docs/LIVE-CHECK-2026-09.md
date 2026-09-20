# Live Check — 2026-09

Alle Prüfungen liefen lokal mit bereits vorhandenen Tools und Artefakten. Es gab
keine externen Downloads, Uploads, Account-Aktionen oder Workflow-Starts.

| Komponente | Status | Befund |
| --- | --- | --- |
| Ollama | VERIFIED | Lokaler Dienst antwortete auf `ollama list`; lokale Modelle `gemma-code`, `devstral-small-2` und `gemma4:26b-a4b-it-qat` sind gelistet. Cloud-Modell-Referenzen wurden nur gelistet, nicht aufgerufen. |
| Kokoro TTS | VERIFIED | Bereits gecachte ONNX-/Voice-Dateien und Python-Bindings vorhanden; lokaler Satz wurde in einem Temp-Verzeichnis zu WAV erzeugt (1,71 s). |
| Lokaler Ingest + Asset-Record | VERIFIED | Vorhandene kleine WAV-Testdatei wurde in einem Temp-Asset-Root lokal ingestiert; ein SOURCE-Record mit `UNKNOWN`-Rechten entstand und wurde gelesen. Der echte Media-Store blieb unangetastet. |
| n8n HTTP-Dienst | VERIFIED — nicht erreichbar | Kein Listener am lokalen Standard-Health-Endpunkt auf Port 5678. Es wurden keine Dienste gestartet oder gestoppt. |
| n8n CLI-Prozesse | VERIFIED | Bereits laufende `n8n execute`-Prozesse für lokale Workflow-Ausführung waren sichtbar; daraus folgt kein erreichbarer n8n-HTTP-Dienst. |
| NotebookLM-LaunchAgent | VERIFIED | Der Agent verarbeitet lokale Dateien, extrahiert bei Medien Text/Audio und übergibt diesen über `nlm source add` an NotebookLM; er schreibt nicht in die Asset-Registry. |

## Grenzen

- Keine Cloud-Modelle, URLs oder Plattform-Importe wurden aufgerufen.
- Die n8n-Workflow-Definitionen und der LaunchAgent wurden nur gelesen.
- Temporäre Smoke-Test-Ausgaben wurden außerhalb der Projekt- und Media-Roots erzeugt und entfernt.
