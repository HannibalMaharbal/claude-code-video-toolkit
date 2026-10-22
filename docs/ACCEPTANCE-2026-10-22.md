# Acceptance Baseline

| Fähigkeit | Status | Kurzgrund | Dauer |
|---|---|---|---:|
| F01 | PASS | Pillow-Transformationen und drei Formate gerendert. | 0.534s |
| F02 | PASS | Spec-JSON-Vertrag (Form+Bild+Text) via Playwright/Chromium gerendert. | 0.490s |
| F03 | PASS | A5-Flyer-Vorlage als PNG+PDF gerendert; Text/Höhe/Schrift per `set` geändert und neu gerendert unterscheidet sich vom ersten Lauf. | 0.563s |
| F04 | PASS | Trim/Concat mit Audio gerendert. | 0.226s |
| F05 | PASS | Reframe, Tempo, XFade-Blende und Overlay gerendert. | 0.300s |
| F06 | PASS | Silence-Cutter auf lokales Pausenmaterial angewendet. | 0.282s |
| F07 | PASS | Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft. | 0.201s |
| F08 | PASS | Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt. | 2.625s |
| F09 | FAIL | RuntimeError: MLX-Whisper lieferte für de keine Zeitsegmente. | 0.906s |
| F10 | PASS | SRT/VTT validiert und lokal via Remotion eingebrannt. | 1.801s |
| F11 | PASS | Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes. | 15.842s |
| F12 | PASS | Routing-Tabelle deckt alle 12 Aufgabentypen ab; lokale Backends live geprüft (ai_router_check); Cloud-Backends bestätigt blockiert (internal_only). | 1.078s |
| F13 | PASS | Versionen erfasst und mit vorhandenem Startwert verglichen; alle Mindestversionen erfüllt. | 0.683s |
| F14 | FAIL | RuntimeError: MLX-Whisper lieferte kein Pipeline-Transkript. | 1.986s |
| F15 | PASS | Bestehende Egress- und Delivery-Gate-Tests bestanden. | 0.566s |
| F16 | PASS | PERSON_LOCK-Set angelegt/verifiziert/gebunden, Job enthält den Lock; ein nach der Registrierung manipuliertes Member wird von verify_set und job_spec.build abgelehnt. | 0.035s |
| F17 | PASS | QC-Verdikt geschrieben, DELIVERY ohne Accept abgelehnt und nach Review erlaubt, Retry-Limit durchgesetzt. | 0.585s |
| F18 | PASS | Cache-Treffer wiederverwendet ein bestehendes Asset; premium bleibt ohne Freigabedatei blockiert und selbst mit Freigabe zusätzlich durch den Egress-Guard blockiert. | 0.009s |
| F19 | PASS | project_init erzeugt alle Projektordner und ein schema-valides Manifest. | 0.001s |
| F20 | PASS | 13 Plattform-Profile vorhanden, schema-valide, alle UNVERIFIED. | 0.003s |
| F21 | PASS | Reframe ohne Fokus-Spec abgelehnt (needs_human); mit Spec erzeugen unterschiedliche Fokuspunkte nachweislich unterschiedliche Ausgaben. | 0.557s |
| F22 | PASS | prepare extrahiert Frames; Cloud-Anfrage ohne Freigabe abgelehnt und geloggt; ingest validiert das Ergebnis und registriert es als ai_generated=partial. | 0.158s |
| F23 | PASS | Provenance-Bericht (JSON+MD, inkl. unsigniertem C2PA-Mapping) erzeugt; provenance_status und ai_labeling_status gesetzt. | 0.031s |
| F24 | PASS | Release-Paket ohne Labeling/Provenance/Metadaten abgelehnt; mit allen dreien erzeugt und erst nach approve() freigegeben. | 0.545s |
| F25 | PASS | Alle 5 Publish-Adapter validieren das freigegebene Paket ohne Befunde; send() bleibt für jeden Adapter durch den Egress-Guard blockiert. | 0.580s |

FERTIG: nein, PASS 23 von 25
