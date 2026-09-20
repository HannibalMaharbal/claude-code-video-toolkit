# Acceptance Baseline

| Fähigkeit | Status | Kurzgrund | Dauer |
|---|---|---|---:|
| F01 | PASS | Pillow-Transformationen und drei Formate gerendert. | 0.998s |
| F02 | MISSING | Kein vorhandener, allgemeiner Bild-Text-Renderer mit Spec-JSON-Vertrag gefunden. | 0.000s |
| F03 | MISSING | Kein vorhandener Flyer-/Poster-Renderer mit Vorlage, A4/A5-Spec und PDF+PNG-Export gefunden. | 0.000s |
| F04 | PASS | Trim/Concat mit Audio gerendert. | 0.226s |
| F05 | PASS | Reframe, Tempo, XFade-Blende und Overlay gerendert. | 0.296s |
| F06 | PASS | Silence-Cutter auf lokales Pausenmaterial angewendet. | 0.280s |
| F07 | PASS | Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft. | 0.174s |
| F08 | PASS | Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt. | 2.844s |
| F09 | PASS | Deutsch und Englisch lokal mit zeitgestempelten Segmenten transkribiert. | 3.953s |
| F10 | MISSING | SRT/VTT validiert, aber Burn-In fehlt: Der installierte FFmpeg-Build enthält keinen subtitles/libass-Filter. Remotion-Alternative ist nicht als Renderer implementiert. | 0.024s |
| F11 | PASS | Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes. | 9.075s |
| F12 | MISSING | Routing-Tabelle docs/KI-SYSTEM-ROUTING.md fehlt. | 0.000s |
| F13 | PASS | Versionen erfasst und Startwert angelegt. | 1.156s |
| F14 | MISSING | Pipeline ausgeführt, aber SRT/VTT und Transcript sind nicht als abgeleitete Text-Assets mit parent_ids registrierbar. | 6.559s |
| F15 | PASS | Bestehende Egress- und Delivery-Gate-Tests bestanden. | 0.357s |

FERTIG: nein, PASS 10 von 15
