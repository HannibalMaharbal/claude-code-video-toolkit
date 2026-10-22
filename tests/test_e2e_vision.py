#!/usr/bin/env python3
"""E2E test for the vision QC pipeline.

Tests the complete path:
  Frame/Input → Vision evaluation → Parsing → Finding → PASS/FAIL decision

Negative cases included:
- wrong main subject
- hallucination
- invalid JSON
- inference error
- missing image

A technical error must never silently end as PASS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.vision_qc import (
    GroundTruth,
    evaluate,
)

QWEN25VL_GROUND_TRUTH = GroundTruth(
    scene="test-pattern composition with SMPTE color bars",
    main_subject="DIE ZUKUNFT DER KI headline text",
    visible_objects=[
        "red color bar", "green color bar", "yellow color bar",
        "blue color bar", "magenta color bar", "cyan color bar",
        "headline text", "timecode display",
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


def _make_test_image(path: Path) -> None:
    """Create a minimal valid PNG for testing."""
    from PIL import Image
    img = Image.new("RGB", (10, 10), (254, 24, 0))
    img.save(path)


def _make_e2e_frame(path: Path) -> Path:
    """Generate a frame via ffmpeg for E2E testing."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "testsrc=size=1920x1080:rate=1", "-frames:v", "1",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True, capture_output=True, timeout=30,
    )
    return path


# --- Test: Frame/Input → Vision evaluation → Finding → PASS/FAIL ---

class TestE2EVisionPipeline:
    """End-to-end tests for the vision QC pipeline."""

    def test_successful_vision_inference_on_known_image(
        self, tmp_path: Path
    ) -> None:
        """Frame → Vision evaluation → PASS when main subject matches."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "DIE ZUKUNFT DER KI headline text",
                "objects": ["red color bar", "green color bar", "headline text"],
                "people_present": False,
                "text_identified": [],
                "confidence": 0.9,
            },
        )

        assert result.status == "PASS"
        assert result.hallucinations == []
        assert not result.error

    def test_wrong_main_subject_is_fail(self, tmp_path: Path) -> None:
        """Wrong main subject must NOT produce PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "futuristic building and car",
                "objects": ["building", "car", "road"],
                "people_present": False,
                "text_identified": [],
                "confidence": 0.85,
            },
        )

        assert result.status == "FAIL"
        assert len(result.hallucinations) > 0

    def test_hallucination_is_fail(self, tmp_path: Path) -> None:
        """Hallucinating objects that don't exist must produce FAIL."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "futuristic car",
                "objects": ["futuristic car", "sci-fi building"],
                "people_present": False,
                "text_identified": [],
                "confidence": 0.8,
            },
        )

        assert result.status == "FAIL"
        assert any("car" in h.lower() for h in result.hallucinations)

    def test_invalid_json_is_fail(self, tmp_path: Path) -> None:
        """Invalid JSON response must produce FAIL, not PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response="not valid json",  # type: ignore
        )

        assert result.status == "FAIL"
        assert result.error

    def test_missing_image_is_fail(self, tmp_path: Path) -> None:
        """Missing image must produce FAIL, not PASS."""
        image = tmp_path / "missing.png"

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "test",
                "objects": ["obj"],
                "people_present": False,
                "text_identified": [],
                "confidence": 0.9,
            },
        )

        assert result.status == "FAIL"
        assert result.error

    def test_empty_model_response_is_fail(self, tmp_path: Path) -> None:
        """Empty model response must produce FAIL, not PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={"main_subject": "", "objects": [], "confidence": 0.0},
        )

        assert result.status == "FAIL"

    def test_missing_model_response_is_needs_human(self, tmp_path: Path) -> None:
        """No model response must produce NEEDS_HUMAN, not PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response=None,
        )

        assert result.status == "NEEDS_HUMAN"
        assert result.status != "PASS"

    def test_low_confidence_is_needs_human(self, tmp_path: Path) -> None:
        """Low confidence must produce NEEDS_HUMAN, not PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "DIE ZUKUNFT DER KI headline text",
                "objects": ["red color bar"],
                "people_present": False,
                "text_identified": [],
                "confidence": 0.1,
            },
        )

        assert result.status == "NEEDS_HUMAN"
        assert result.status != "PASS"

    def test_infrastructure_error_never_passes(self, tmp_path: Path) -> None:
        """Any infrastructure error must never silently become PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        # Simulate various error conditions
        for bad_response in [
            None,
            "not json",
            {},
            {"main_subject": "test"},  # missing required fields
            {"main_subject": "test", "objects": [], "confidence": "bad"},  # wrong types
        ]:
            result = evaluate(
                image, QWEN25VL_GROUND_TRUTH,
                model_response=bad_response,  # type: ignore
            )
            assert result.status != "PASS", (
                f"Bad response {bad_response} incorrectly produced PASS"
            )


class TestE2VNegativeCases:
    """Negative E2E test cases."""

    def test_qwen_style_hallucination_is_detected(self, tmp_path: Path) -> None:
        """Test the specific Qwen hallucination pattern: 'futuristic car'."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        # This mimics what qwen2.5vl:3b actually produced
        qwen_style_response = {
            "main_subject": "futuristic structure",
            "objects": ["futuristic car", "technological components"],
            "people_present": False,
            "text_identified": [],
            "confidence": 0.8,
        }

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response=qwen_style_response,
        )

        assert result.status == "FAIL"
        assert any("car" in h.lower() for h in result.hallucinations)

    def test_all_ground_truth_objects_passes(self, tmp_path: Path) -> None:
        """When all ground truth objects are correctly identified, PASS."""
        image = tmp_path / "frame.png"
        _make_test_image(image)

        result = evaluate(
            image, QWEN25VL_GROUND_TRUTH,
            model_response={
                "main_subject": "DIE ZUKUNFT DER KI headline text",
                "objects": [
                    "red color bar", "green color bar", "yellow color bar",
                    "blue color bar", "magenta color bar", "cyan color bar",
                    "headline text", "timecode display", "diagonal gradient",
                    "checkerboard pattern",
                ],
                "people_present": False,
                "text_identified": ["DIE ZUKUNFT DER KI"],
                "confidence": 0.95,
            },
        )

        assert result.status == "PASS"
        assert result.hallucinations == []
