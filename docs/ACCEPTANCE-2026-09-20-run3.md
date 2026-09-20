# Acceptance Baseline

| Fähigkeit | Status | Kurzgrund | Dauer |
|---|---|---|---:|
| F01 | PASS | Pillow-Transformationen und drei Formate gerendert. | 0.028s |
| F02 | PASS | Spec-JSON-Vertrag (Form+Bild+Text) via Playwright/Chromium gerendert. | 0.328s |
| F03 | PASS | A5-Flyer-Vorlage als PNG+PDF gerendert; Text/Höhe/Schrift per `set` geändert und neu gerendert unterscheidet sich vom ersten Lauf. | 0.563s |
| F04 | PASS | Trim/Concat mit Audio gerendert. | 0.228s |
| F05 | PASS | Reframe, Tempo, XFade-Blende und Overlay gerendert. | 0.391s |
| F06 | PASS | Silence-Cutter auf lokales Pausenmaterial angewendet. | 0.314s |
| F07 | PASS | Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft. | 0.190s |
| F08 | PASS | Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt. | 3.019s |
| F09 | PASS | Deutsch und Englisch lokal mit zeitgestempelten Segmenten transkribiert. | 3.352s |
| F10 | PASS | SRT/VTT validiert und lokal via Remotion eingebrannt. | 2.645s |
| F11 | PASS | Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes. | 2.131s |
| F12 | PASS | Routing-Tabelle deckt alle 12 Aufgabentypen ab; lokale Backends live geprüft (ai_router_check); Cloud-Backends bestätigt blockiert (internal_only). | 0.507s |
| F13 | FAIL | RuntimeError: python: Ist 'Python 3.12.14' erfüllt nicht >=3.14.7. | 0.622s |
| F14 | PASS | Pipeline vollständig registriert: Video, SRT/VTT/Übersetzung/Transcript als abgeleitete Text-Assets sowie Schnitt (MASTER) und Normalisierung (VARIANT) mit vererbten Rechten. | 5.516s |
| F15 | PASS | Bestehende Egress- und Delivery-Gate-Tests bestanden. | 0.345s |
| F16 | PASS | PERSON_LOCK-Set angelegt/verifiziert/gebunden, Job enthält den Lock; ein nach der Registrierung manipuliertes Member wird von verify_set und job_spec.build abgelehnt. | 0.015s |
| F17 | PASS | QC-Verdikt geschrieben, DELIVERY ohne Accept abgelehnt und nach Review erlaubt, Retry-Limit durchgesetzt. | 0.517s |
| F18 | PASS | Cache-Treffer wiederverwendet ein bestehendes Asset; premium bleibt ohne Freigabedatei blockiert und selbst mit Freigabe zusätzlich durch den Egress-Guard blockiert. | 0.008s |
| F19 | PASS | project_init erzeugt alle Projektordner und ein schema-valides Manifest. | 0.001s |

FERTIG: nein, PASS 18 von 19
