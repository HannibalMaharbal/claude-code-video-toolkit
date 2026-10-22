from __future__ import annotations

from pathlib import Path

import pytest

from tools.vision_qc import (
    GroundTruth,
    ModelClaim,
    VisionQCError,
    _detect_hallucinations,
    _validate_model_response,
    evaluate,
)

# --- Ground truth fixtures for the Qwen test frame ---

QWEN25VL_GROUND_TRUTH = GroundTruth(
    scene="test-pattern composition with SMPTE color bars",
    main_subject="DIE ZUKUNFT DER KI headline text",
    visible_objects=[
        "red color bar", "green color bar", "yellow color bar",
        "blue color bar", "magenta color bar", "cyan color bar",
        "headline text", "timecode display", "diagonal gradient",
        "checkerboard pattern",
    ],
    has_people=False,
    legible_text=[
        "DIE ZUKUNFT DER KI",
        "Die Zukunft der KI beginnt nicht irgendwann.",
        "Sie entsteht jetzt.",
        "00:00:10.000",
    ],
    spatial_relationships=[
        "color bars span full height side by side",
        "headline centered in upper third",
        "timecode anchored top-left",
    ],
)


# --- Helper functions ---

def _valid_response(main_subject: str, objects: list[str], confidence: float = 0.9) -> dict:
    return {
        "main_subject": main_subject,
        "objects": objects,
        "people_present": False,
        "text_identified": [],
        "confidence": confidence,
    }


def _hallucination_response() -> dict:
    return {
        "main_subject": "futuristic structure and car",
        "objects": ["futuristic car", "sci-fi building", "red color bar"],
        "people_present": False,
        "text_identified": [],
        "confidence": 0.85,
    }


# --- Test _validate_model_response ---

def test_validate_valid_response() -> None:
    response = _valid_response("main subject", ["obj1", "obj2"], 0.9)
    _validate_model_response(response)


def test_validate_missing_fields() -> None:
    response = {"main_subject": "test"}
    with pytest.raises(VisionQCError, match="fehlt Felder"):
        _validate_model_response(response)


def test_validate_invalid_confidence() -> None:
    response = _valid_response("test", ["obj"], 1.5)
    with pytest.raises(VisionQCError, match="confidence"):
        _validate_model_response(response)


def test_validate_not_a_dict() -> None:
    with pytest.raises(VisionQCError, match="kein JSON-Objekt"):
        _validate_model_response("not a dict")


# --- Test _detect_hallucinations ---

def test_no_hallucination_on_correct_response() -> None:
    claim = ModelClaim(
        main_subject="DIE ZUKUNFT DER KI headline text",
        objects=["red color bar", "green color bar", "headline text"],
        people_present=False,
        text_identified=[],
        confidence=0.9,
        raw_response="{}",
    )
    hallucinations = _detect_hallucinations(claim, QWEN25VL_GROUND_TRUTH)
    assert hallucinations == []


def test_detects_car_hallucination() -> None:
    claim = ModelClaim(
        main_subject="futuristic structure and car",
        objects=["futuristic car", "sci-fi building", "red color bar"],
        people_present=False,
        text_identified=[],
        confidence=0.85,
        raw_response="{}",
    )
    hallucinations = _detect_hallucinations(claim, QWEN25VL_GROUND_TRUTH)
    assert len(hallucinations) > 0
    assert any("car" in h.lower() for h in hallucinations)


def test_detects_people_hallucination() -> None:
    claim = ModelClaim(
        main_subject="person standing in front of building",
        objects=["person", "building", "car"],
        people_present=True,
        text_identified=[],
        confidence=0.8,
        raw_response="{}",
    )
    hallucinations = _detect_hallucinations(claim, QWEN25VL_GROUND_TRUTH)
    assert any("Personen" in h for h in hallucinations)


def test_detects_main_subject_hallucination() -> None:
    claim = ModelClaim(
        main_subject="futuristic architecture",
        objects=["building", "car", "structure"],
        people_present=False,
        text_identified=[],
        confidence=0.9,
        raw_response="{}",
    )
    hallucinations = _detect_hallucinations(claim, QWEN25VL_GROUND_TRUTH)
    assert any("Hauptmotiv" in h for h in hallucinations)


def test_no_hallucination_on_color_bars_only() -> None:
    claim = ModelClaim(
        main_subject="color bars and text",
        objects=["red color bar", "green color bar", "text"],
        people_present=False,
        text_identified=[],
        confidence=0.95,
        raw_response="{}",
    )
    hallucinations = _detect_hallucinations(claim, QWEN25VL_GROUND_TRUTH)
    assert hallucinations == []


# --- Test evaluate() ---

def test_evaluate_pass_on_correct_response(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_valid_response(
            "DIE ZUKUNFT DER KI headline text",
            ["red color bar", "green color bar", "headline text"],
        ),
    )
    assert result.status == "PASS"
    assert result.hallucinations == []


def test_evaluate_fail_on_hallucination(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_hallucination_response(),
    )
    assert result.status == "FAIL"
    assert len(result.hallucinations) > 0
    assert any("car" in h.lower() for h in result.hallucinations)


def test_evaluate_fail_on_missing_image(tmp_path: Path) -> None:
    image = tmp_path / "missing.png"
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_valid_response("test", ["obj"]),
    )
    assert result.status == "FAIL"
    assert result.error


def test_evaluate_needs_human_when_no_model_response(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(image, QWEN25VL_GROUND_TRUTH, model_response=None)
    assert result.status == "NEEDS_HUMAN"


def test_evaluate_fail_on_invalid_json(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response="not valid json",  # type: ignore
    )
    assert result.status == "FAIL"
    assert result.error


def test_evaluate_fail_on_low_confidence(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_valid_response(
            "DIE ZUKUNFT DER KI headline text",
            ["red color bar"],
            confidence=0.3,
        ),
    )
    assert result.status == "NEEDS_HUMAN"


def test_evaluate_fail_on_missing_fields(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response={"main_subject": "test"},  # missing objects, confidence
    )
    assert result.status == "FAIL"


def test_evaluate_fail_on_empty_objects(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_valid_response("test", []),
    )
    assert result.status == "FAIL"


def test_evaluate_pass_with_all_ground_truth_objects(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    response = _valid_response(
        "DIE ZUKUNFT DER KI headline text",
        QWEN25VL_GROUND_TRUTH.visible_objects,
        confidence=0.95,
    )
    result = evaluate(image, QWEN25VL_GROUND_TRUTH, model_response=response)
    assert result.status == "PASS"


def test_evaluate_does_not_pass_with_hallucination(tmp_path: Path) -> None:
    """Ensure a model that hallucinates a car cannot get PASS."""
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response=_hallucination_response(),
    )
    assert result.status == "FAIL"
    assert result.hallucinations != []


# --- Test that technical errors never silently become PASS ---

def test_no_silent_pass_on_inference_error(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    # Simulate an inference error by passing None as model_response
    result = evaluate(image, QWEN25VL_GROUND_TRUTH, model_response=None)
    assert result.status != "PASS"


def test_no_silent_pass_on_invalid_response(tmp_path: Path) -> None:
    image = tmp_path / "test.png"
    image.write_bytes(b"fake png data")
    result = evaluate(
        image, QWEN25VL_GROUND_TRUTH,
        model_response="not json",  # type: ignore
    )
    assert result.status == "FAIL"
    assert not result.status == "PASS"
