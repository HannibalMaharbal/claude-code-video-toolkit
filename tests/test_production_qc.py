from __future__ import annotations

from pathlib import Path

from tools.production_qc import FAIL, NEEDS_HUMAN, PASS, _category, _status


def test_status_keeps_hard_fail_above_all_other_states() -> None:
    assert _status([{"status": PASS}, {"status": "WARNING"}, {"status": FAIL}]) == FAIL


def test_status_keeps_human_gate_explicit() -> None:
    category = _category("SEMANTIC", [{"status": PASS}, {"status": NEEDS_HUMAN}])
    assert category["status"] == NEEDS_HUMAN


def test_status_not_run_does_not_become_pass() -> None:
    assert _status([{"status": "not_run"}]) == PASS


def test_overall_rejects_when_any_check_fails() -> None:
    from tools.qc_pipeline import _overall
    checks = [{"name": "technical", "status": "fail", "evidence": "boom"}]
    assert _overall(checks) == "reject"


def test_audio_findings_handles_missing_audio_gracefully(tmp_path: Path) -> None:
    from tools.production_qc import FAIL, _audio_findings
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    item = {"audio_plan": {"voiceover": "missing.wav"}}
    findings = _audio_findings(video, item, tmp_path)
    assert any(f["status"] == FAIL for f in findings)


def test_subtitle_findings_handles_corrupted_subtitles(tmp_path: Path) -> None:
    from tools.production_qc import FAIL, _subtitle_findings
    bad_srt = tmp_path / "bad.srt"
    bad_srt.write_text("corrupted content not valid srt", encoding="utf-8")
    findings = _subtitle_findings(bad_srt)
    assert any(f["status"] == FAIL for f in findings)


def test_video_findings_handles_missing_video(tmp_path: Path) -> None:
    from tools.production_qc import FAIL, _audio_findings
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    item = {"audio_plan": {"voiceover": str(tmp_path / "missing.wav")}}
    findings = _audio_findings(video, item, tmp_path)
    assert any(f["status"] == FAIL for f in findings)


def test_run_vision_qc_invokes_explicit_local_provider(
    tmp_path: Path, monkeypatch
) -> None:
    from tools import production_qc
    from tools.vision_qc import GroundTruth, VisionResult

    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        __import__("json").dumps(
            {
                "vision_frame": "frame.png",
                "ground_truth": {
                    "scene": "test",
                    "main_subject": "test pattern",
                    "visible_objects": ["color bars"],
                    "has_people": False,
                    "legible_text": [],
                    "spatial_relationships": [],
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_infer(image_path, ground_truth: GroundTruth, **kwargs):
        captured.update(kwargs)
        assert image_path == frame
        assert ground_truth.main_subject == "test pattern"
        return VisionResult(
            status=PASS,
            findings=[{"status": PASS, "message": "inference ran"}],
            model_used="ollama:example-vl",
        )

    monkeypatch.setattr(production_qc, "_vision_infer_and_evaluate", fake_infer)

    findings = production_qc._run_vision_qc(
        manifest,
        tmp_path,
        vision_provider="ollama",
        vision_model="example-vl",
        vision_timeout_ms=4321,
    )

    assert findings == [{"status": PASS, "message": "inference ran"}]
    assert captured == {
        "vision_provider": "ollama",
        "vision_model": "example-vl",
        "timeout_ms": 4321,
    }
