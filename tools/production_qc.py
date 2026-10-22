#!/usr/bin/env python3
"""Final production QC: combine existing deterministic checks without claiming taste.

The manifest is intentionally declarative. It lets production state what must be
preserved across formats; undeclared visual semantics remain NEEDS_HUMAN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import format_layout, media_validation, platform_profiles, visual_qc
from tools.subtitle_burn import parse_subtitle_cues
from tools.transcribe import validate_subtitle_cues
from tools.video_ingest import probe_media

try:
    from tools.vision_qc import GroundTruth as _GroundTruth
    from tools.vision_qc import VisionQCError
    from tools.vision_qc import infer_and_evaluate as _vision_infer_and_evaluate
    _VISION_AVAILABLE = True
except ImportError:
    _VISION_AVAILABLE = False

PASS = "PASS"
FAIL = "FAIL"
WARNING = "WARNING"
NEEDS_HUMAN = "NEEDS_HUMAN"
STATUSES = {PASS, FAIL, WARNING, NEEDS_HUMAN}


class ProductionQcError(RuntimeError):
    pass


def _status(findings: list[dict[str, str]]) -> str:
    states = {finding["status"] for finding in findings}
    if FAIL in states:
        return FAIL
    if NEEDS_HUMAN in states:
        return NEEDS_HUMAN
    if WARNING in states:
        return WARNING
    return PASS


def _category(name: str, findings: list[dict[str, str]]) -> dict[str, Any]:
    return {"category": name, "status": _status(findings), "findings": findings}


def _path(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ProductionQcError(f"Pfad außerhalb des Manifest-Verzeichnisses: {value}")
    return candidate


def _subtitle_findings(path: Path) -> list[dict[str, str]]:
    try:
        cues = parse_subtitle_cues(path)
    except Exception as error:  # noqa: BLE001
        return [{"status": FAIL, "message": f"Untertitel konnte nicht geparst werden: {error}"}]
    errors = validate_subtitle_cues(cues)
    findings = [{"status": FAIL, "message": error} for error in errors]
    if not errors:
        findings.append(
            {
                "status": PASS,
                "message": f"{len(cues)} Cues: Struktur, Dauer und Zeilenlänge valide.",
            }
        )
    for index, cue in enumerate(cues, start=1):
        lines = str(cue["text"]).splitlines()
        if len(lines) > 2:
            findings.append({"status": FAIL, "message": f"Cue {index}: mehr als zwei Zeilen."})
        if str(cue["text"]).rstrip().endswith("-"):
            findings.append(
                {
                    "status": WARNING,
                    "message": f"Cue {index}: endet mit Bindestrich; Worttrennung prüfen.",
                }
            )
    return findings


def _audio_findings(video: Path, item: dict[str, Any], root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        report = media_validation.validate_audio(video)
    except media_validation.MediaValidationError as error:
        return [{"status": FAIL, "message": str(error)}]
    findings.append(
        {
            "status": PASS,
            "message": (
                f"{report.details['loudnessLufs']} LUFS, "
                f"{report.details['truePeakDbfs']} dBFS True Peak."
            ),
        }
    )
    plan = item.get("audio_plan") or {}
    for role in ("voiceover", "music", "sfx"):
        expected = plan.get(role)
        if expected is None:
            continue
        source = _path(root, str(expected))
        findings.append(
            {
                "status": PASS if source.is_file() else FAIL,
                "message": f"{role}: {'vorhanden' if source.is_file() else 'fehlt'}",
            }
        )
    voiceover = plan.get("voiceover")
    if voiceover:
        voice = _path(root, str(voiceover))
        if voice.is_file():
            try:
                voice_duration = float(probe_media(voice)["duration"])
                video_duration = float(probe_media(video)["duration"])
                difference = abs(video_duration - voice_duration)
                findings.append(
                    {
                        "status": PASS if difference <= 0.25 else WARNING,
                        "message": f"Voiceover-/Videodauer-Differenz: {difference:.3f}s.",
                    }
                )
            except Exception as error:  # noqa: BLE001
                findings.append(
                    {
                        "status": WARNING,
                        "message": f"Voiceover-/Videodauer-Differenz konnte nicht ermittelt werden: {error}",
                    }
                )
    mix_report = plan.get("mix_report")
    if plan.get("music") and mix_report:
        report_path = _path(root, str(mix_report))
        try:
            mix = json.loads(report_path.read_text(encoding="utf-8"))
            ducked = bool(mix.get("music_ducked"))
        except (OSError, json.JSONDecodeError):
            ducked = False
        findings.append(
            {
                "status": PASS if ducked else FAIL,
                "message": "Music ducking bestätigt."
                if ducked
                else "Music ducking nicht nachweisbar.",
            }
        )
    elif plan.get("music"):
        findings.append(
            {
                "status": WARNING,
                "message": "Music vorgesehen, aber kein Mix-Report für Ducking-Nachweis.",
            }
        )
    return findings


def _run_vision_qc(
    manifest_path: Path,
    root: Path,
    *,
    vision_provider: str,
    vision_model: str,
    vision_timeout_ms: int,
) -> list[dict[str, str]]:
    """Run vision-based QC evaluation if the vision_qc module is available.

    This is a fail-closed integration point. If vision_qc is not available,
    or if any error occurs, the result defaults to NEEDS_HUMAN findings.
    Production-QC is NOT activated by default — vision_enabled must be
    explicitly set to True.

    Returns:
        List of finding dicts for the SEMANTIC category
    """
    if not _VISION_AVAILABLE:
        return [
            {
                "status": NEEDS_HUMAN,
                "message": "Vision-QC-Modul nicht verfügbar.",
            }
        ]

    # Check if manifest has a vision frame reference
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest_data = json.loads(manifest)
    frame_path = manifest_data.get("vision_frame")
    if not frame_path:
        return [
            {
                "status": NEEDS_HUMAN,
                "message": "Kein vision_frame im Manifest konfiguriert.",
            }
        ]

    full_frame_path = (root / frame_path).resolve()
    if not full_frame_path.is_file():
        return [
            {
                "status": FAIL,
                "message": f"Vision-Frame nicht gefunden: {full_frame_path}",
            }
        ]

    # Build ground truth from manifest
    try:
        ground_truth = _GroundTruth(**manifest_data.get("ground_truth", {}))
    except (TypeError, KeyError) as error:
        return [
            {
                "status": NEEDS_HUMAN,
                "message": f"Ungültige ground_truth-Konfiguration: {error}",
            }
        ]

    try:
        result = _vision_infer_and_evaluate(
            full_frame_path,
            ground_truth,
            vision_provider=vision_provider,
            vision_model=vision_model,
            timeout_ms=vision_timeout_ms,
        )
        return [
            {"status": result.status, "message": msg["message"]}
            for msg in result.findings
        ]
    except VisionQCError as error:
        return [
            {"status": FAIL, "message": f"Vision-QC-Fehler: {error}"}
        ]
    except Exception as error:
        return [
            {
                "status": NEEDS_HUMAN,
                "message": f"Vision-QC unerwarteter Fehler: {error}",
            }
        ]


def run(
    manifest_path: Path,
    *,
    vision_enabled: bool = False,
    vision_provider: str | None = None,
    vision_model: str | None = None,
    vision_timeout_ms: int = 120000,
) -> dict[str, Any]:
    """Run production QC.

    vision_enabled (default False): When True, attempts to run vision-based
    semantic evaluation. Production-QC is NOT activated by default.
    Any vision error is fail-closed (never silently PASS).
    """
    root = manifest_path.parent.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProductionQcError(f"Manifest nicht lesbar: {error}") from error
    variants = manifest.get("variants")
    if not isinstance(variants, list) or len(variants) < 2:
        raise ProductionQcError("Manifest benötigt mindestens zwei Varianten.")
    required = set(manifest.get("required_element_ids") or [])
    caption_reference: str | None = None
    resolved_variants: list[tuple[dict[str, Any], dict[str, Any], Path, Path]] = []
    technical: list[dict[str, str]] = []
    layout: list[dict[str, str]] = []
    subtitle: list[dict[str, str]] = []
    audio: list[dict[str, str]] = []
    format_findings: list[dict[str, str]] = []
    for item in variants:
        if not isinstance(item, dict):
            raise ProductionQcError("Jede Variante muss ein Objekt sein.")
        profile_name = str(item["profile"])
        profile = {**platform_profiles.get_profile(profile_name), "name": profile_name}
        video = _path(root, str(item["video"]))
        captions = _path(root, str(item["captions"]))
        scene = _path(root, str(item["scene_layout"]))
        if not video.is_file() or not captions.is_file() or not scene.is_file():
            raise ProductionQcError(f"Unvollständige Variantendateien für {profile_name}.")
        visual = visual_qc.check(video, profile, scene_layout=scene, subtitles=captions)
        technical.extend(
            {
                "status": check["status"].upper() if check["status"] != "not_run" else WARNING,
                "message": f"{profile_name}: {check['name']} — {check['evidence']}",
            }
            for check in visual
            if check["name"] in {"frame", "black_frames", "freeze_frames"}
        )
        resolved = None
        try:
            resolved = format_layout.resolve_scene_file(scene, profile_name)
        except Exception as error:  # noqa: BLE001
            layout.append({"status": FAIL, "message": f"{profile_name}: Layout konnte nicht aufgelöst werden: {error}"})
        if resolved is not None:
            layout.extend(
                {"status": FAIL, "message": f"{profile_name}: {issue}"} for issue in resolved["issues"]
            )
            if not resolved["issues"]:
                layout.append(
                    {
                        "status": PASS,
                        "message": f"{profile_name}: alle deklarativen Texte innerhalb Safe Area.",
                    }
                )
        subtitle.extend(
            {**finding, "message": f"{profile_name}: {finding['message']}"}
            for finding in _subtitle_findings(captions)
        )
        audio.extend(
            {**finding, "message": f"{profile_name}: {finding['message']}"}
            for finding in _audio_findings(video, item, root)
        )
        content = " ".join(str(cue["text"]) for cue in parse_subtitle_cues(captions))
        if caption_reference is None:
            caption_reference = content
        elif content != caption_reference:
            format_findings.append(
                {"status": FAIL, "message": f"{profile_name}: Caption-Inhalt weicht ab."}
            )
        element_ids = {str(element["id"]) for element in resolved["elements"] if element["visible"]}
        missing = required - element_ids
        format_findings.append(
            {
                "status": FAIL if missing else PASS,
                "message": (
                    f"{profile_name}: Pflichtinformationen "
                    f"{'fehlen: ' + ', '.join(sorted(missing)) if missing else 'vorhanden'}"
                ),
            }
        )
        resolved_variants.append((item, resolved, video, captions))
    baseline = resolved_variants[0][1]
    baseline_elements = {
        (element["id"], element["content"], element["priority"])
        for element in baseline["elements"]
        if element["visible"]
    }
    consistency: list[dict[str, str]] = []
    for item, resolved, _video, _captions in resolved_variants[1:]:
        current = {
            (element["id"], element["content"], element["priority"])
            for element in resolved["elements"]
            if element["visible"]
        }
        consistency.append(
            {
                "status": PASS if current == baseline_elements else FAIL,
                "message": (
                    f"{item['profile']}: deklarierte Text-/Prioritätsinformationen "
                    f"{'konsistent' if current == baseline_elements else 'abweichend'}."
                ),
            }
        )
    # SEMANTIC category: vision evaluation if enabled, otherwise NEEDS_HUMAN
    if vision_enabled and _VISION_AVAILABLE and vision_provider and vision_model:
        vision_findings = _run_vision_qc(
            manifest_path,
            root,
            vision_provider=vision_provider,
            vision_model=vision_model,
            vision_timeout_ms=vision_timeout_ms,
        )
        semantic_findings = [
            {"status": PASS, "message": "Deklarierte Pflichtinformationen sind maschinell prüfbar."},
        ] + vision_findings
    else:
        reason = (
            "Vision-QC ist nicht aktiviert."
            if not vision_enabled
            else "Vision-QC benötigt einen expliziten lokalen Provider und ein exaktes Modell."
        )
        semantic_findings = [
            {"status": PASS, "message": "Deklarierte Pflichtinformationen sind maschinell prüfbar."},
            {
                "status": NEEDS_HUMAN,
                "message": reason,
            },
        ]
    categories = [
        _category("TECHNICAL", technical),
        _category("LAYOUT", layout),
        _category("TEXT", layout),
        _category("SUBTITLE", subtitle),
        _category("SEMANTIC", semantic_findings),
        _category("CONSISTENCY", consistency),
        _category("AUDIO", audio),
        _category("FORMAT", format_findings),
    ]
    hard = [category for category in categories if category["status"] == FAIL]
    final_status = (
        FAIL
        if hard
        else NEEDS_HUMAN
        if any(category["status"] == NEEDS_HUMAN for category in categories)
        else WARNING
        if any(category["status"] == WARNING for category in categories)
        else PASS
    )
    categories.append(
        _category(
            "FINAL MASTER",
            [
                {
                    "status": final_status,
                    "message": "Harte Gates fehlgeschlagen."
                    if hard
                    else (
                        "Alle harten automatisierbaren Gates bestanden; "
                        "Human-Gates bleiben explizit."
                    ),
                }
            ],
        )
    )
    return {
        "project": manifest.get("project", "unknown"),
        "status": final_status,
        "categories": categories,
        "vad": "optional / später",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final local production QC.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--vision-enabled", action="store_true",
                        help="Enable vision-based semantic QC (not activated by default)")
    parser.add_argument("--vision-provider", choices=("lmstudio", "ollama"))
    parser.add_argument("--vision-model")
    parser.add_argument("--vision-timeout-ms", type=int, default=120000)
    args = parser.parse_args()
    if args.vision_enabled and not (args.vision_provider and args.vision_model):
        parser.error("--vision-enabled requires --vision-provider and --vision-model")
    try:
        result = run(
            args.manifest,
            vision_enabled=args.vision_enabled,
            vision_provider=args.vision_provider,
            vision_model=args.vision_model,
            vision_timeout_ms=args.vision_timeout_ms,
        )
    except ProductionQcError as error:
        parser.error(str(error))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
