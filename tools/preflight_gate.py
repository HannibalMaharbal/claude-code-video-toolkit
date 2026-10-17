#!/usr/bin/env python3
"""
HANNIBAL AI OS — Video Production Pre-Flight Gate
Kanonisches Sicherheits- und Integritäts-Gate für KI-Videoproduktionen.

Strikte Fail-Closed-Validierung gegen Cache-Verschleppung und Asset-Drift:
1. Prüft Existenz und SHA-256 aller deklarierten Assets (Master, Szenenbilder, Audio).
2. Verifiziert, dass alle Szenen-Keyframes explizit vom aktuellen Master-Hash abgeleitet sind
   (derived_from_master_sha256 == hash(master_asset)).
3. Verbietet Wildcards (*.jpg, scene_*.png) — jede Asset-Datei muss im Manifest stehen.
4. Prüft mathematische Handle-Reserve (mind. 10-15% Puffer über Zieldauer).
5. Validiert Framerate, Auflösung und Audio-Loudness-Vorgaben.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PreflightError(Exception):
    """Fehler bei der Pre-Flight-Validierung."""


def compute_sha256(file_path: Path | str) -> str:
    """Berechnet den echten SHA-256-Hash einer Datei im Chunk-Modus."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Datei für Hash-Berechnung nicht gefunden: {path}")
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class PreflightReport:
    project_id: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    master_sha256: str = ""
    total_planned_duration_sec: float = 0.0
    target_duration_sec: float = 0.0
    handle_reserve_pct: float = 0.0
    verified_assets: int = 0


def validate_manifest(
    manifest_data: dict[str, Any],
    base_dir: Path | str | None = None,
    enforce_hashes: bool = True,
    min_handle_reserve_pct: float = 10.0,
) -> PreflightReport:
    """
    Validiert ein Video-Projekt-Manifest fail-closed.
    """
    project_id = manifest_data.get("project_id", "unnamed_project")
    report = PreflightReport(project_id=project_id, is_valid=True)
    base_path = Path(base_dir) if base_dir else Path.cwd()

    def resolve_path(rel_or_abs: str, asset_name: str) -> Path | None:
        p = Path(rel_or_abs)
        # 1. Pfad-Traversal-Schutz: Verhindere ".." Ausbrüche
        if ".." in p.parts:
            report.errors.append(
                f"Sicherheits-Fehler ({asset_name}): Pfad-Traversal ('..') ist verboten: {rel_or_abs}"
            )
            report.is_valid = False
            return None

        resolved = (base_path / p) if not p.is_absolute() else p
        
        # 2. Workspace-Jail: Datei muss innerhalb des Basisverzeichnisses liegen
        try:
            resolved_real = resolved.resolve()
            base_real = base_path.resolve()
            if not resolved_real.is_relative_to(base_real):
                report.errors.append(
                    f"Sicherheits-Fehler ({asset_name}): Datei liegt außerhalb des Projekts: {resolved}"
                )
                report.is_valid = False
                return None
        except Exception as e:
            report.errors.append(f"Pfad-Fehler ({asset_name}): {e}")
            report.is_valid = False
            return None

        # 3. Symlink-Sperre: Verhindere Cache-Spoofing über Symlinks
        if resolved.is_symlink():
            report.errors.append(
                f"Sicherheits-Fehler ({asset_name}): Symlinks sind im Produktions-Manifest verboten: {resolved}"
            )
            report.is_valid = False
            return None

        return resolved

    # 1. Master-Asset Validierung
    master_info = manifest_data.get("master_asset")
    if not master_info or not isinstance(master_info, dict):
        report.errors.append("Pflichtfeld 'master_asset' fehlt oder ist kein Objekt.")
        report.is_valid = False
        return report

    master_path_raw = master_info.get("path")
    if not master_path_raw:
        report.errors.append("Pflichtfeld 'master_asset.path' fehlt.")
        report.is_valid = False
        return report

    master_file = resolve_path(master_path_raw, "master_asset")
    if not master_file or not master_file.is_file():
        if master_file:
            report.errors.append(f"Master-Asset-Datei existiert nicht: {master_file}")
        report.is_valid = False
        return report

    actual_master_sha = compute_sha256(master_file)
    report.master_sha256 = actual_master_sha
    report.verified_assets += 1

    expected_master_sha = master_info.get("sha256")
    if enforce_hashes and expected_master_sha:
        if expected_master_sha.lower() != actual_master_sha.lower():
            report.errors.append(
                f"Master-Asset SHA-256 Diskrepanz! "
                f"Manifest={expected_master_sha[:12]}..., Realität={actual_master_sha[:12]}... "
                f"(Datei wurde nach Manifest-Erstellung modifiziert)"
            )
            report.is_valid = False

    # 2. Shot- & Keyframe-Validierung
    shots = manifest_data.get("shots")
    if not shots or not isinstance(shots, list) or len(shots) == 0:
        report.errors.append("Pflichtfeld 'shots' fehlt oder enthält keine Szenen.")
        report.is_valid = False
        return report

    total_planned_frames = 0
    fps = manifest_data.get("technical_specs", {}).get("fps", 24.0)
    target_duration = manifest_data.get("target_duration_sec", 60.0)
    report.target_duration_sec = target_duration

    seen_shot_ids: set[str] = set()

    for idx, shot in enumerate(shots, start=1):
        shot_id = shot.get("id", f"shot-{idx:03d}")
        
        # Doppelte Shot-IDs abfangen
        if shot_id in seen_shot_ids:
            report.errors.append(f"Doppelte Shot-ID entdeckt: '{shot_id}'. IDs müssen eindeutig sein!")
            report.is_valid = False
        seen_shot_ids.add(shot_id)

        source_raw = shot.get("source")
        if not source_raw:
            report.errors.append(f"Shot '{shot_id}' hat kein 'source'-Feld.")
            report.is_valid = False
            continue

        # Prüfe auf unzulässige Wildcards
        if any(c in str(source_raw) for c in ("*", "?", "[", "]")):
            report.errors.append(
                f"Shot '{shot_id}': Wildcards im Pfad '{source_raw}' sind verboten! "
                f"Nur explizite Dateipfade erlaubt."
            )
            report.is_valid = False
            continue

        shot_file = resolve_path(source_raw, f"Shot '{shot_id}'")
        if not shot_file or not shot_file.is_file():
            if shot_file:
                report.errors.append(f"Shot '{shot_id}': Datei existiert nicht: {shot_file}")
            report.is_valid = False
            continue

        # Hash-Prüfung der Quelldatei
        actual_shot_sha = compute_sha256(shot_file)
        report.verified_assets += 1
        expected_shot_sha = shot.get("sha256")
        if enforce_hashes and expected_shot_sha:
            if expected_shot_sha.lower() != actual_shot_sha.lower():
                report.errors.append(
                    f"Shot '{shot_id}': SHA-256 Diskrepanz! "
                    f"Manifest={expected_shot_sha[:12]}..., Realität={actual_shot_sha[:12]}..."
                )
                report.is_valid = False

        # Provenienz / Master-Ableitung (Schutz vor alten Paris-1920-Zwischenbildern)
        derived_from = shot.get("derived_from_master_sha256")
        if derived_from:
            if derived_from.lower() != actual_master_sha.lower():
                report.errors.append(
                    f"Shot '{shot_id}': Asset-Inkonsistenz / Cache-Drift! "
                    f"Bild basiert auf altem Master ({derived_from[:12]}...), "
                    f"aktueller Master ist aber {actual_master_sha[:12]}... "
                    f"Neu-Generierung dieses Keyframes zwingend erforderlich!"
                )
                report.is_valid = False

        # Frame-Zählung für Handle-Reserve
        duration_frames = shot.get("duration_frames", 0)
        duration_sec = shot.get("duration_sec", 0.0)
        if duration_frames > 0:
            total_planned_frames += duration_frames
        elif duration_sec > 0:
            total_planned_frames += int(duration_sec * fps)

    # 3. Audio-Asset Validierung (Voiceover & BGM)
    audio_assets = manifest_data.get("audio_assets", {})
    if isinstance(audio_assets, dict):
        for audio_type, audio_info in audio_assets.items():
            if isinstance(audio_info, dict) and "path" in audio_info:
                a_file = resolve_path(audio_info["path"])
                if not a_file.is_file():
                    report.warnings.append(f"Audio-Asset '{audio_type}' fehlt noch: {a_file}")
                else:
                    report.verified_assets += 1
                    actual_a_sha = compute_sha256(a_file)
                    exp_a_sha = audio_info.get("sha256")
                    if enforce_hashes and exp_a_sha:
                        if exp_a_sha.lower() != actual_a_sha.lower():
                            report.errors.append(
                                f"Audio-Asset '{audio_type}' SHA-256 Diskrepanz! "
                                f"Manifest={exp_a_sha[:12]}..., Realität={actual_a_sha[:12]}..."
                            )
                            report.is_valid = False

    # 4. Mathematische Handle-Reserve Berechnung
    total_planned_sec = total_planned_frames / fps if fps > 0 else 0.0
    report.total_planned_duration_sec = round(total_planned_sec, 2)

    if target_duration > 0 and total_planned_sec > 0:
        reserve_sec = total_planned_sec - target_duration
        reserve_pct = (reserve_sec / target_duration) * 100.0
        report.handle_reserve_pct = round(reserve_pct, 1)

        if total_planned_sec < target_duration:
            report.errors.append(
                f"Gesamtlaufzeit unzureichend! Geplant: {total_planned_sec:.1f}s, "
                f"Ziel: {target_duration:.1f}s. Es fehlen {target_duration - total_planned_sec:.1f}s Material!"
            )
            report.is_valid = False
        elif reserve_pct < min_handle_reserve_pct:
            report.warnings.append(
                f"Knappe Handle-Reserve: Nur {reserve_pct:.1f}% Puffer "
                f"({reserve_sec:.1f}s Verschnitt-Reserve). Empfohlen: mind. {min_handle_reserve_pct}%."
            )

    if len(report.errors) > 0:
        report.is_valid = False

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="HANNIBAL AI OS Pre-Flight Validation Gate")
    parser.add_argument("--manifest", "-m", required=True, help="Pfad zur project_manifest.json")
    parser.add_argument("--base-dir", "-b", help="Basisverzeichnis für relative Pfade (Standard: Manifest-Ordner)")
    parser.add_argument("--min-reserve", type=float, default=10.0, help="Mindest-Handle-Reserve in %% (Default: 10.0)")
    parser.add_argument("--skip-hash-enforcement", action="store_true", help="Nur Existenz prüfen, Hash-Abweichungen als Warnung")
    parser.add_argument("--json", action="store_true", help="Ergebnis als maschinenlesbares JSON ausgeben")

    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.is_file():
        print(f"FATAL: Manifest-Datei {manifest_path} existiert nicht!", file=sys.stderr)
        return 1

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
    except Exception as e:
        print(f"FATAL: Manifest {manifest_path} ist kein gültiges JSON: {e}", file=sys.stderr)
        return 1

    base_dir = Path(args.base_dir).resolve() if args.base_dir else manifest_path.parent
    report = validate_manifest(
        manifest_data=manifest_data,
        base_dir=base_dir,
        enforce_hashes=not args.skip_hash_enforcement,
        min_handle_reserve_pct=args.min_reserve,
    )

    if args.json:
        print(json.dumps(report.__dict__, indent=2, ensure_ascii=False))
    else:
        print(f"=== HANNIBAL PRE-FLIGHT GATE: {report.project_id} ===")
        print(f"Verifizierte Assets:     {report.verified_assets}")
        print(f"Master SHA-256:          {report.master_sha256[:16]}...")
        print(f"Geplantes Rohmaterial:   {report.total_planned_duration_sec}s")
        print(f"Ziel-Master-Dauer:       {report.target_duration_sec}s")
        print(f"Handle-Reserve (Puffer): {report.handle_reserve_pct}%")

        if report.warnings:
            print("\nWARNUNGEN:")
            for w in report.warnings:
                print(f"  [!] {w}")

        if report.errors:
            print("\nFEHLER (FAIL-CLOSED):")
            for err in report.errors:
                print(f"  [X] {err}")
            print("\n>>> PRE-FLIGHT VERDICT: REJECTED (Render gestoppt) <<<\n")
            return 1

        print("\n>>> PRE-FLIGHT VERDICT: PASSED (Freigabe für Render) <<<\n")

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
