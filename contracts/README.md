# P0-Verträge — Übergabe an Codex

Stand: 2026-09-20. Basis: Audit 58321-MASTER + Ist-Stand-Bericht.

## Entscheidungen (aus dem Ist-Stand abgeleitet)

- **Code-Root:** `PROJEKTE/video-toolkit` (neuere Ingest-/Analyse-/Subtitle-Arbeit, aber aktuell uncommitted).
- **Asset-Root:** `PROJEKTE/video-toolkit-media` (nur Medien, `assets/{source,references,editable_source,master,variant,delivery}`). Kein neuer Code dort.
- **Kein dritter Root.** Worktrees `gap-fill-video` / `gap-merge-video-main` sind Spender für `qc_verdict_log.py`, `subtitle_translate.py` und `references/{brand,person,product,style}`; sie werden gezielt und additiv übernommen, nicht überschrieben.
- Bestehendes `project.json` bleibt unverändert. Neue Projekte bekommen zusätzlich `manifests/project.manifest.json`.

## Inhalt

| Datei | Zweck |
|---|---|
| `asset-manifest.schema.json` | 1 Record pro Asset: Rolle, SHA-256, Parent-IDs, Lifecycle, Rechte/Consent, KI-Angabe |
| `reference-set.schema.json` | Gehashte Referenzliste, an die ein Lock gebunden wird |
| `project-manifest.schema.json` | Projekt: Assets, Lock-Policy, Route, Kostenkaskade pro Schritt, Delivery, Provenance, KI-Kennzeichnung |
| `validate_contracts.py` | Validator + Selbsttest (`python validate_contracts.py selftest`) |
| `examples/` | 5 gültige, 8 bewusst ungültige Beispiele |

Der Selbsttest ist grün (13/13).

## Was die Schemas hart erzwingen

- `MASTER`/`VARIANT`/`DELIVERY` ohne `parent_ids` + `derivation` → ungültig.
- `DELIVERY` mit `UNKNOWN`/`RESTRICTED`, `commercial_use != allowed`, fehlendem/unklarem Consent oder ohne `ai_involvement` → ungültig.
- Personenreferenz ohne dokumentierten Consent, Zweckbindung und Bearbeitungsfreigabe → ungültig. Produkt-/Brand-Referenz ohne Zweckbindung und Bearbeitungsfreigabe → ungültig.
- `provider_data_scope = cloud_approved` ohne Provider-Liste → ungültig (Standardhaltung: `cloud_not_approved`).
- Aktiver Lock ohne `reference_set_id` + `reference_set_sha256` + `on_drift` → ungültig.
- `premium` ohne Freigabe/Begründung, `approved` ohne Person/Zeit → ungültig.
- Pfade nur relativ, kein `..`.

Nur im Validator (nicht im Schema): `set_sha256` = SHA-256 über die nach `asset_id` sortierten Zeilen `asset_id:sha256`; PERSON_LOCK-Set braucht mindestens Front, Profil, 3/4.

## Bewusst offen (nicht P0)

- `qc_verdict.schema.json` (P2), Plattform-Profile (P3), C2PA-Mapping (P5).
- Ob `PUBLIC_DOMAIN` in Delivery erlaubt bleibt (aktuell ja, wie im Audit).
- Rechtliche Prüfung der KI-Kennzeichnung: `ai_labeling_status` ist nur ein Statusfeld, keine Rechtsbewertung.

## Codex-Prompt zur Umsetzung

```
Ziel: P0-Verträge additiv einführen. Vorher nichts überschreiben.

1. In PROJEKTE/video-toolkit: Erst git status prüfen. Wenn uncommitted Änderungen vorliegen, NICHT anfassen; stattdessen mich fragen, ob ein Checkpoint-Commit gewünscht ist.
2. Neuen Branch von der aktuellen HEAD anlegen: feature/p0-contracts.
3. Ordner contracts/ anlegen und den Inhalt von p0-contracts/ (3 Schemas, validate_contracts.py, examples/) 1:1 hineinkopieren. Keine Schema-Änderung ohne Rückfrage.
4. python contracts/validate_contracts.py selftest ausführen (pip: jsonschema); Ergebnis melden.
5. In PROJEKTE/video-toolkit-media/assets/ die Ordner source, references/{person,product,brand,style,scene}, editable_source, master, variant, delivery anlegen (nur leere Ordner + .gitkeep). Keine bestehenden Dateien verschieben.
6. Nichts aus den Worktrees übernehmen, nichts migrieren, keine n8n-Workflows aktivieren.
7. Berichte: geänderte/neu angelegte Pfade, Selbsttest-Ergebnis, offene Konflikte.
```
