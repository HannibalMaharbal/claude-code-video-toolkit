# Unabhängiges Review: Smart Upscale

Bitte prüfe den Commit-Diff (`git show`) read-only auf Kostenabsicherung, Upload-Freigaben, ungewollte Wiederholungen, Datenverlust, Timeouts und korrekte CLI-Weitergabe. Nenne Schweregrad, Datei, konkrete Auswirkung und Reproduktion; keine Änderungen ausführen.

Kontext: Basisclip Seedance 2.5, 480p, 10 s; Preisabfrage 30 Credits. Noch kein bezahlter Job, kein Clip-Upload, kein Live-Upscale. Automatisches Chaining ist bei unbekanntem Gesamtpreis gesperrt. Basisclip und Upscale sind getrennte Bezahlaufträge mit Credit-Limit und Upload-Gate. Anbieterpreise und End-to-End-Qualität sind unbestätigt.

Prüfe insbesondere die temporäre Bereitstellung von Downloads, Kosten- und Guthabenprüfung, Preislimits und Warnungen bei unklarem Jobstatus. Ein separat arbeitender Codex-Agent derselben Modellfamilie hat bereits geprüft; dieses Review soll modellfremd sein.

Vollständige Testsuite: 524 bestanden mit `.venv/bin/python -m pytest -q` und lokalem Browser-/Ollama-Zugriff.
