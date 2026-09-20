from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from contracts.validate_contracts import validate
from tools import asset_record, project_init, qc_pipeline


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    return tmp_path


def _make_video(tmp_path: Path, name: str = "video.mp4") -> Path:
    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_run_qc_on_valid_video_has_pass_technical_and_needs_human_overall(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)

    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    assert validate("qc_verdict", verdict) == []
    checks = {check["name"]: check["status"] for check in verdict["checks"]}
    assert checks["technical"] == "pass"
    assert checks["audio"] == "pass"
    assert checks["subtitle"] == "not_run"
    assert checks["layout"] == "not_run"
    for name in qc_pipeline.VISUAL_CHECKS:
        assert checks[name] == "needs_human"
    assert verdict["overall"] == "needs_human"
    assert verdict["retry_count"] == 0
    assert "reviewer" not in verdict


def test_technical_check_fails_on_a_broken_video_file(env: Path) -> None:
    # A file that a lenient ffprobe would still register as "video" (so it can
    # reach run_qc's dispatch), but that media_validation.validate_video's
    # stricter first/last-frame decode fails on.
    broken = env / "broken.mp4"
    broken.write_bytes(b"not a real video file")

    check = qc_pipeline._run_technical(broken, "video")

    assert check["name"] == "technical"
    assert check["status"] == "fail"
    assert check["evidence"]


def test_overall_is_reject_when_any_check_fails() -> None:
    checks = [
        {"name": "technical", "status": "fail", "evidence": "boom"},
        *qc_pipeline._visual_checks(),
    ]
    assert qc_pipeline._overall(checks) == "reject"


def test_overall_is_needs_human_when_no_check_fails() -> None:
    checks = [
        {"name": "technical", "status": "pass", "evidence": "ok"},
        *qc_pipeline._visual_checks(),
    ]
    assert qc_pipeline._overall(checks) == "needs_human"


def test_overall_is_accept_only_when_nothing_fails_or_needs_human() -> None:
    checks = [{"name": "technical", "status": "pass", "evidence": "ok"}]
    assert qc_pipeline._overall(checks) == "accept"


def test_run_qc_on_subtitle_asset_runs_subtitle_check(env: Path) -> None:
    srt = env / "cues.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8")
    record = asset_record.register_asset(srt)

    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    checks = {check["name"]: check["status"] for check in verdict["checks"]}
    assert checks["subtitle"] == "pass"
    assert checks["technical"] == "not_run"
    assert checks["audio"] == "not_run"


def test_run_qc_on_layout_render_output_runs_layout_check(env: Path, monkeypatch) -> None:
    from PIL import Image

    png = env / "flyer.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(png)
    spec = env / "spec.json"
    spec.write_text('{"canvas": {"preset": "A5"}, "layers": []}', encoding="utf-8")
    spec_record = asset_record.register_asset(spec, role="EDITABLE_SOURCE")
    record = asset_record.register_derived(
        png, parents=[spec_record["asset_id"]], role="MASTER",
        tool="layout_render", operation="render_png",
    )

    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    checks = {check["name"]: check["status"] for check in verdict["checks"]}
    assert checks["layout"] == "pass"


def test_retry_qc_increments_count_and_refuses_past_limit(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"], retry_limit=1)

    retried = qc_pipeline.retry_qc("demo-project", verdict["verdict_id"])
    assert retried["retry_count"] == 1

    with pytest.raises(qc_pipeline.QcPipelineError, match="Retry-Limit"):
        qc_pipeline.retry_qc("demo-project", verdict["verdict_id"])


def test_retry_qc_clears_a_prior_review(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"], retry_limit=3)
    qc_pipeline.apply_review(
        "demo-project", verdict["verdict_id"], reviewer="qa", overall="accept"
    )

    retried = qc_pipeline.retry_qc("demo-project", verdict["verdict_id"])

    assert "reviewer" not in retried
    assert retried["overall"] == "needs_human"


def test_apply_review_sets_accept_with_reviewer(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    reviewed = qc_pipeline.apply_review(
        "demo-project", verdict["verdict_id"], reviewer="qa-lead", overall="accept"
    )

    assert reviewed["overall"] == "accept"
    assert reviewed["reviewer"] == "qa-lead"
    assert validate("qc_verdict", reviewed) == []


def test_apply_review_rejects_empty_reviewer(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    with pytest.raises(qc_pipeline.QcPipelineError, match="reviewer"):
        qc_pipeline.apply_review(
            "demo-project", verdict["verdict_id"], reviewer="  ", overall="accept"
        )


def test_apply_review_rejects_invalid_overall(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])

    with pytest.raises(qc_pipeline.QcPipelineError, match="overall"):
        qc_pipeline.apply_review(
            "demo-project", verdict["verdict_id"], reviewer="qa", overall="maybe"
        )


def test_find_accepted_verdict_returns_none_when_no_verdict_exists(env: Path) -> None:
    assert qc_pipeline.find_accepted_verdict("ast_doesnotexist000") is None


def test_find_accepted_verdict_ignores_non_accepted_verdicts(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    qc_pipeline.run_qc("demo-project", record["asset_id"])  # stays needs_human

    assert qc_pipeline.find_accepted_verdict(record["asset_id"]) is None


def test_find_accepted_verdict_finds_an_accepted_verdict(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    verdict = qc_pipeline.run_qc("demo-project", record["asset_id"])
    qc_pipeline.apply_review(
        "demo-project", verdict["verdict_id"], reviewer="qa-lead", overall="accept"
    )

    found = qc_pipeline.find_accepted_verdict(record["asset_id"])

    assert found is not None
    assert found["verdict_id"] == verdict["verdict_id"]
