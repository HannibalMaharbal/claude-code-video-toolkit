# Release- und Staging-Checkliste

## Vorgesehener Betrieb

Lokale Ausführung nutzt Node 22, Python 3.12, `npm ci` und `uv sync --frozen`.
Cloud-/Modal-/GPU-Ausführung ist optional, providerabhängig und kostenpflichtig;
vor jedem solchen Lauf sind Provider, Budget und Zugangsdaten ausdrücklich
freizugeben. Artefakte gehen in jobbezogene temporäre Verzeichnisse und danach in
den freigegebenen Artefaktspeicher; Secrets und lokale Modelle bleiben außerhalb
des Git-Repositories.

Jobs erhalten stabile IDs, atomare Statusdateien, Wiederaufnahme nach transienten
Fehlern und feste Timeouts: Provider 120 s, Medien-Smoke 120 s, mit kontrolliertem
Kindprozess-Abbruch. Fertige Artefakte werden bei Wiederholung wiederverwendet.

## GitHub-Einstellungen

Für `main` erforderlich: Pull Request, Review, aktuelle Branchbasis, keine
Force-Pushes/Branchlöschung, Required Checks `verify` und `analyze`. Dependency
Graph, Dependabot Alerts/Security Updates, CodeQL, Secret Scanning und Push
Protection aktivieren. Workflows und SHA-Pins sind lokal vorbereitet; keine
Repository-Einstellung wurde verändert.

