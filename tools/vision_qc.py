#!/usr/bin/env python3
"""Vision-based QC evaluation: robust visual ground-truth comparison.

This module provides the integration point for vision model inference in
production QC. It is deliberately NOT activated by default — the Production-QC
run() function does NOT call into this module unless explicitly configured.

The module provides:
- VisionEvaluation: Evaluates a frame against a ground-truth description
- HallucinationDetector: Detects claims about objects not present in the image
- Error handling for missing images, inference failures, and invalid responses
- Fail-closed behavior: any error or uncertainty defaults to WARNING/NEEDS_HUMAN
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.vision_providers import (
    VisionProviderError,
    VisionSettings,
    create_provider,
    discover_local_providers,
    format_discovery,
    load_capability_statuses,
)

PASS = "PASS"
FAIL = "FAIL"
WARNING = "WARNING"
NEEDS_HUMAN = "NEEDS_HUMAN"


class VisionQCError(RuntimeError):
    """Vision QC evaluation could not be performed."""


@dataclass
class GroundTruth:
    """Verifiable visual ground truth for a frame."""

    scene: str
    main_subject: str
    visible_objects: list[str]
    has_people: bool
    legible_text: list[str]
    spatial_relationships: list[str]


@dataclass
class VisionResult:
    """Result of a vision QC evaluation."""

    status: str
    findings: list[dict[str, str]] = field(default_factory=list)
    hallucinations: list[str] = field(default_factory=list)
    model_used: str = ""
    inference_time_ms: int = 0
    error: str = ""


@dataclass
class ModelClaim:
    """A claim made by a vision model about an image."""

    main_subject: str
    objects: list[str]
    people_present: bool
    text_identified: list[str]
    confidence: float
    raw_response: str = ""


def _load_image(path: Path) -> Path:
    """Validate that an image file exists and is readable."""
    if not path.is_file():
        raise VisionQCError(f"Bilddatei fehlt: {path}")
    if path.stat().st_size <= 0:
        raise VisionQCError(f"Bilddatei ist leer: {path}")
    return path


def _validate_model_response(response: dict[str, Any]) -> None:
    """Validate that a model response has the required structure."""
    if not isinstance(response, dict):
        raise VisionQCError("Modell-Antwort ist kein JSON-Objekt")
    required_fields = ["main_subject", "objects", "confidence"]
    missing = [f for f in required_fields if f not in response]
    if missing:
        raise VisionQCError(f"Modell-Antwort fehlt Felder: {', '.join(missing)}")
    if not isinstance(response["objects"], list):
        raise VisionQCError("Modell-Antwort 'objects' ist keine Liste")
    if not isinstance(response["confidence"], (int, float)):
        raise VisionQCError("Modell-Antwort 'confidence' ist keine Zahl")
    if not (0 <= response["confidence"] <= 1):
        raise VisionQCError("Modell-Antwort 'confidence' außerhalb von [0,1]")
    if not response["objects"]:
        raise VisionQCError("Modell-Antwort 'objects' ist leer")


def _detect_hallucinations(claim: ModelClaim, ground_truth: GroundTruth) -> list[str]:
    """Detect claims about objects that are NOT in the ground truth.

    This is robust against phrasing variations — it checks for core object
    names and known non-existent objects, not exact string matching.
    """
    hallucinations: list[str] = []

    # Objects claimed by the model that are NOT in the ground truth
    # and are NOT the main subject or a known visual element
    known_visual_elements = {
        "color bar",
        "color bars",
        "smpte",
        "test pattern",
        "timecode",
        "timeline",
        "headline",
        "text",
        "checkerboard",
        "diagonal band",
        "gradient",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "frame",
        "resolution",
        "video frame",
    }

    for obj in claim.objects:
        obj_lower = obj.lower().strip()
        if obj_lower in known_visual_elements:
            continue
        if obj_lower in [gt.lower() for gt in ground_truth.visible_objects]:
            continue
        # Check if the object sounds like a hallucination
        # (a physical object that would not be in a test pattern)
        hallucination_indicators = [
            "car",
            "vehicle",
            "building",
            "structure",
            "architecture",
            "person",
            "face",
            "body",
            "human",
            "figure",
            "animal",
            "futuristic",
            "sci-fi",
            "spaceship",
            "mountain",
            "ocean",
            "sky",
            "nature",
            "forest",
            "house",
            "room",
            "interior",
        ]
        if any(indicator in obj_lower for indicator in hallucination_indicators):
            hallucinations.append(f"Halluzination erkannt: '{obj}' ist nicht im Bild vorhanden")

    # Check if the model claims a main subject that's wrong
    if ground_truth.main_subject.lower() not in claim.main_subject.lower():
        if any(
            indicator in claim.main_subject.lower()
            for indicator in ["car", "building", "structure", "futuristic", "space"]
        ):
            hallucinations.append(
                f"Hauptmotiv-Fehler: Modell beschreibt '{claim.main_subject}', "
                f"erwartet wird '{ground_truth.main_subject}'"
            )

    # Check for people claims when there are none
    if claim.people_present and not ground_truth.has_people:
        hallucinations.append("Personen behauptet, aber keine Personen im Bild")

    return hallucinations


def evaluate(
    image_path: Path,
    ground_truth: GroundTruth,
    *,
    model_response: dict[str, Any] | None = None,
    model_used: str = "",
    timeout_ms: int = 120000,
) -> VisionResult:
    """Evaluate a vision model's response against ground truth.

    If model_response is provided, it's validated and compared against
    ground_truth directly (for testing). If model_response is None,
    the function returns a WARNING indicating that inference is needed.

    Fail-closed: any error or uncertainty defaults to WARNING or NEEDS_HUMAN,
    never silently to PASS.

    Args:
        image_path: Path to the image file to evaluate
        ground_truth: The known ground truth for the image
        model_response: Optional pre-fetched model response dict
        model_used: Provider/model identifier used for a supplied response
        timeout_ms: Timeout for inference in milliseconds

    Returns:
        VisionResult with status, findings, and hallucination list
    """
    result = VisionResult(
        status=NEEDS_HUMAN,
        model_used=model_used,
    )

    # Step 1: Validate image
    try:
        _load_image(image_path)
    except VisionQCError as error:
        result.status = FAIL
        result.error = str(error)
        result.findings.append({"status": FAIL, "message": f" Bildfehler: {error}"})
        return result

    # Step 2: If no model response provided, return NEEDS_HUMAN
    if model_response is None:
        result.status = NEEDS_HUMAN
        result.findings.append(
            {"status": NEEDS_HUMAN, "message": "Vision-Inference nicht durchgeführt."}
        )
        return result

    # Step 3: Validate model response structure
    try:
        _validate_model_response(model_response)
    except VisionQCError as error:
        result.status = FAIL
        result.error = str(error)
        result.findings.append({"status": FAIL, "message": f" Ungültige Modell-Antwort: {error}"})
        return result

    # Step 4: Build ModelClaim from response
    claim = ModelClaim(
        main_subject=model_response.get("main_subject", ""),
        objects=model_response.get("objects", []),
        people_present=model_response.get("people_present", False),
        text_identified=model_response.get("text_identified", []),
        confidence=model_response["confidence"],
        raw_response=json.dumps(model_response),
    )

    # Step 5: Detect hallucinations
    hallucinations = _detect_hallucinations(claim, ground_truth)
    result.hallucinations = hallucinations

    # Step 6: Determine status based on hallucinations and confidence
    if hallucinations:
        result.status = FAIL
        result.findings.append(
            {"status": FAIL, "message": f" Halluzinationen erkannt: {'; '.join(hallucinations)}"}
        )
        for h in hallucinations:
            result.findings.append({"status": FAIL, "message": h})
    elif claim.confidence < 0.5:
        result.status = NEEDS_HUMAN
        result.findings.append(
            {"status": NEEDS_HUMAN, "message": f" Niedrige Konfidenz: {claim.confidence}"}
        )
    elif ground_truth.main_subject.lower() in claim.main_subject.lower():
        result.status = PASS
        result.findings.append({"status": PASS, "message": " Hauptmotiv korrekt erkannt."})
    else:
        result.status = NEEDS_HUMAN
        result.findings.append({"status": NEEDS_HUMAN, "message": " Hauptmotiv nicht bestätigt."})

    return result


def infer_and_evaluate(
    image_path: Path,
    ground_truth: GroundTruth,
    *,
    vision_provider: str,
    vision_model: str,
    timeout_ms: int = 120000,
) -> VisionResult:
    """Run explicitly configured local vision inference and evaluate it.

    This is an opt-in integration point. It calls exactly the configured local
    provider, validates the response, and evaluates against ground truth.
    It deliberately has no default provider/model and never attempts fallback.

    Fail-closed: Any inference error, timeout, or invalid response results
    in FAIL or NEEDS_HUMAN, never silently PASS.

    Args:
        image_path: Path to the image file
        ground_truth: The known ground truth for the image
        vision_provider: ``lmstudio`` or ``ollama``
        vision_model: Exact local model identifier discovered at that provider
        timeout_ms: Timeout for inference

    Returns:
        VisionResult with evaluation results
    """
    result = VisionResult(
        status=NEEDS_HUMAN,
        model_used=f"{vision_provider}:{vision_model}",
    )

    # Validate image first
    try:
        _load_image(image_path)
    except VisionQCError as error:
        result.status = FAIL
        result.error = str(error)
        result.findings.append({"status": FAIL, "message": f" Bildfehler: {error}"})
        return result

    # Attempt only the explicitly selected provider; no provider/model fallback.
    try:
        prompt = (
            "Analyze this image. Describe exactly what you see:\n\n"
            f"Ground truth reference: {ground_truth.scene}\n\n"
            "Provide a structured JSON response with:\n"
            "- main_subject: the primary subject\n"
            "- objects: list of visible objects\n"
            "- people_present: true/false\n"
            "- text_identified: list of legible text\n"
            "- confidence: 0-1\n"
        )
        provider = create_provider(
            VisionSettings(
                provider=vision_provider,
                model=vision_model,
                timeout_ms=timeout_ms,
            )
        )
        model_response = provider.infer(image_path, prompt)
        return evaluate(
            image_path,
            ground_truth,
            model_response=model_response,
            model_used=result.model_used,
        )
    except (ValueError, VisionProviderError) as error:
        result.status = FAIL
        result.error = str(error)
        result.findings.append({"status": FAIL, "message": f" Inference-Fehler: {error}"})

    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vision-based QC evaluation")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--ground-truth", type=str)
    parser.add_argument("--vision-provider", choices=("lmstudio", "ollama"))
    parser.add_argument("--vision-model")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    parser.add_argument(
        "--discover", action="store_true", help="Discover local providers without inference"
    )
    parser.add_argument(
        "--capability-status-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "contracts" / "vision-capability-status.json",
        help="Validated semantic capability outcomes; not a provider health check",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.discover:
        try:
            statuses = load_capability_statuses(args.capability_status_file)
        except VisionProviderError as error:
            print(f"Vision-QC: ERROR — {error}", file=sys.stderr)
            return 1
        print(
            format_discovery(
                discover_local_providers(
                    timeout_ms=args.timeout_ms,
                    capability_statuses=statuses,
                )
            )
        )
        return 0
    if not all((args.image, args.ground_truth, args.vision_provider, args.vision_model)):
        print(
            (
                "Vision-QC: --image, --ground-truth, --vision-provider "
                "und --vision-model sind erforderlich"
            ),
            file=sys.stderr,
        )
        return 2
    try:
        ground_truth = GroundTruth(**json.loads(args.ground_truth))
        result = infer_and_evaluate(
            args.image,
            ground_truth,
            vision_provider=args.vision_provider,
            vision_model=args.vision_model,
            timeout_ms=args.timeout_ms,
        )
    except VisionQCError as error:
        print(f"Vision-QC: ERROR — {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": result.status,
                "findings": result.findings,
                "hallucinations": result.hallucinations,
                "error": result.error,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
