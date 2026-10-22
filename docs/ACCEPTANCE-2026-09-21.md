# Acceptance Baseline

| Fähigkeit | Status | Kurzgrund | Dauer |
|---|---|---|---:|
| F01 | PASS | Pillow-Transformationen und drei Formate gerendert. | 0.065s |
| F02 | PASS | Spec-JSON-Vertrag (Form+Bild+Text) via Playwright/Chromium gerendert. | 0.339s |
| F03 | PASS | A5-Flyer-Vorlage als PNG+PDF gerendert; Text/Höhe/Schrift per `set` geändert und neu gerendert unterscheidet sich vom ersten Lauf. | 0.572s |
| F04 | PASS | Trim/Concat mit Audio gerendert. | 0.204s |
| F05 | PASS | Reframe, Tempo, XFade-Blende und Overlay gerendert. | 0.301s |
| F06 | PASS | Silence-Cutter auf lokales Pausenmaterial angewendet. | 0.286s |
| F07 | PASS | Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft. | 0.186s |
| F08 | PASS | Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt. | 3.138s |
| F09 | PASS | Deutsch und Englisch lokal mit zeitgestempelten Segmenten transkribiert. | 4.049s |
| F10 | PASS | SRT/VTT validiert und lokal via Remotion eingebrannt. | 1.868s |
| F11 | PASS | Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes. | 5.177s |
| F12 | PASS | Routing-Tabelle deckt alle 12 Aufgabentypen ab; lokale Backends live geprüft (ai_router_check); Cloud-Backends bestätigt blockiert (internal_only). | 0.839s |
| F13 | PASS | Versionen erfasst und mit vorhandenem Startwert verglichen; alle Mindestversionen erfüllt. | 0.620s |
| F14 | PASS | Pipeline vollständig registriert: Video, SRT/VTT/Übersetzung/Transcript als abgeleitete Text-Assets sowie Schnitt (MASTER) und Normalisierung (VARIANT) mit vererbten Rechten. | 4.024s |
| F15 | PASS | Bestehende Egress- und Delivery-Gate-Tests bestanden. | 0.392s |
| F16 | PASS | PERSON_LOCK-Set angelegt/verifiziert/gebunden, Job enthält den Lock; ein nach der Registrierung manipuliertes Member wird von verify_set und job_spec.build abgelehnt. | 0.017s |
| F17 | PASS | QC-Verdikt geschrieben, DELIVERY ohne Accept abgelehnt und nach Review erlaubt, Retry-Limit durchgesetzt. | 0.527s |
| F18 | PASS | Cache-Treffer wiederverwendet ein bestehendes Asset; premium bleibt ohne Freigabedatei blockiert und selbst mit Freigabe zusätzlich durch den Egress-Guard blockiert. | 0.007s |
| F19 | PASS | project_init erzeugt alle Projektordner und ein schema-valides Manifest. | 0.001s |
| F20 | PASS | 13 Plattform-Profile vorhanden, schema-valide, alle UNVERIFIED. | 0.002s |
| F21 | PASS | Reframe ohne Fokus-Spec abgelehnt (needs_human); mit Spec erzeugen unterschiedliche Fokuspunkte nachweislich unterschiedliche Ausgaben. | 0.426s |
| F22 | PASS | prepare extrahiert Frames; Cloud-Anfrage ohne Freigabe abgelehnt und geloggt; ingest validiert das Ergebnis und registriert es als ai_generated=partial. | 0.160s |
| F23 | PASS | Provenance-Bericht (JSON+MD, inkl. unsigniertem C2PA-Mapping) erzeugt; provenance_status und ai_labeling_status gesetzt. | 0.030s |
| F24 | PASS | Release-Paket ohne Labeling/Provenance/Metadaten abgelehnt; mit allen dreien erzeugt und erst nach approve() freigegeben. | 0.523s |
| F25 | PASS | Alle 5 Publish-Adapter validieren das freigegebene Paket ohne Befunde; send() bleibt für jeden Adapter durch den Egress-Guard blockiert. | 0.522s |

FERTIG: ja, PASS 25 von 25
