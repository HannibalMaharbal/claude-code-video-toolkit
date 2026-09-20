# Acceptance Baseline

| Fähigkeit | Status | Kurzgrund | Dauer |
|---|---|---|---:|
| F01 | PASS | Pillow-Transformationen und drei Formate gerendert. | 0.024s |
| F02 | PASS | Spec-JSON-Vertrag (Form+Bild+Text) via Playwright/Chromium gerendert. | 0.503s |
| F03 | PASS | A5-Flyer-Vorlage als PNG+PDF gerendert; Text/Höhe/Schrift per `set` geändert und neu gerendert unterscheidet sich vom ersten Lauf. | 0.575s |
| F04 | PASS | Trim/Concat mit Audio gerendert. | 0.206s |
| F05 | PASS | Reframe, Tempo, XFade-Blende und Overlay gerendert. | 0.288s |
| F06 | PASS | Silence-Cutter auf lokales Pausenmaterial angewendet. | 0.261s |
| F07 | PASS | Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft. | 0.178s |
| F08 | PASS | Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt. | 2.714s |
| F09 | PASS | Deutsch und Englisch lokal mit zeitgestempelten Segmenten transkribiert. | 3.006s |
| F10 | PASS | SRT/VTT validiert und lokal via Remotion eingebrannt. | 2.104s |
| F11 | PASS | Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes. | 2.074s |
| F12 | PASS | Routing-Tabelle deckt alle 12 Aufgabentypen ab; lokale Backends live geprüft (ai_router_check); Cloud-Backends bestätigt blockiert (internal_only). | 0.472s |
| F13 | PASS | Versionen erfasst und mit vorhandenem Startwert verglichen. | 0.613s |
| F14 | PASS | Pipeline vollständig registriert: Video, SRT/VTT/Übersetzung/Transcript als abgeleitete Text-Assets sowie Schnitt (MASTER) und Normalisierung (VARIANT) mit vererbten Rechten. | 3.912s |
| F15 | PASS | Bestehende Egress- und Delivery-Gate-Tests bestanden. | 0.340s |

FERTIG: ja, PASS 15 von 15
