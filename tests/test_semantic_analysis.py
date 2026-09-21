from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from contracts.validate_contracts import validate
from tools import asset_record, project_init, semantic_analysis


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
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-t",
            "5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _valid_result(asset_id: str, *, scope: str = "local", provider: str | None = None) -> dict:
    analyzer = {"name": "claude", "version": "1.0", "scope": scope}
    if provider is not None:
        analyzer["provider"] = provider
    return {
        "schema_version": "1.0.0",
        "asset_id": asset_id,
        "analyzer": analyzer,
        "created_at": "2026-09-21T00:00:00+00:00",
        "highlights": [{"start_s": 0.0, "end_s": 1.5, "reason": "Intro mit Produkt", "score": 0.8}],
        "topics": ["produkt", "intro"],
        "subject_boxes": [
            {
                "frame_ref": "frame-0000.png",
                "boxes": [
                    {
                        "x": 0.1,
                        "y": 0.1,
                        "width": 0.3,
                        "height": 0.4,
                        "confidence": 0.9,
                        "label": "person",
                    }
                ],
            }
        ],
    }


# --- schema -------------------------------------------------------------------------


def test_valid_result_validates() -> None:
    result = _valid_result("ast_" + "a" * 12)
    assert validate("semantic_analysis", result) == []


def test_schema_rejects_highlight_end_before_start() -> None:
    result = _valid_result("ast_" + "a" * 12)
    result["highlights"][0]["end_s"] = 0.0
    assert validate("semantic_analysis", result) != []


def test_schema_rejects_cloud_scope_without_provider() -> None:
    result = _valid_result("ast_" + "a" * 12, scope="cloud_approved")
    assert "provider" not in result["analyzer"]
    assert validate("semantic_analysis", result) != []


# --- prepare() ------------------------------------------------------------------------


def test_prepare_local_extracts_frames(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)

    result = semantic_analysis.prepare("demo-project", record["asset_id"], interval_s=2.0)

    assert result["local_allowed"] is True
    assert result["cloud_allowed"] is False
    assert len(result["frames"]) >= 2
    for frame in result["frames"]:
        assert Path(frame).is_file()


def test_prepare_caps_frame_count(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)

    result = semantic_analysis.prepare(
        "demo-project", record["asset_id"], interval_s=0.5, max_frames=3
    )

    assert len(result["frames"]) <= 3


def test_prepare_cloud_without_approval_is_rejected_and_logged(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)

    with pytest.raises(semantic_analysis.SemanticAnalysisError, match="Cloud"):
        semantic_analysis.prepare("demo-project", record["asset_id"], requested_scope="cloud")

    log_path = env / "projects" / "demo-project" / "analysis" / "cloud-rejections.log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["asset_id"] == record["asset_id"]


def test_prepare_cloud_with_approval_succeeds(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    asset_record.set_rights(
        record["asset_id"],
        provider_data_scope="cloud_approved",
        approved_providers=["openai"],
        note="Freigabe fuer Test",
    )

    result = semantic_analysis.prepare("demo-project", record["asset_id"], requested_scope="cloud")

    assert result["cloud_allowed"] is True
    assert result["approved_providers"] == ["openai"]


# --- ingest() ---------------------------------------------------------------------------


def test_ingest_writes_semantic_json_and_registers_variant(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    result_path = env / "result.json"
    result_path.write_text(json.dumps(_valid_result(record["asset_id"])), encoding="utf-8")

    outcome = semantic_analysis.ingest("demo-project", result_path)

    semantic_path = Path(outcome["semantic_path"])
    assert semantic_path.is_file()
    on_disk = json.loads(semantic_path.read_text(encoding="utf-8"))
    assert validate("semantic_analysis", on_disk) == []
    assert outcome["asset_record"]["role"] == "VARIANT"
    assert outcome["asset_record"]["ai_involvement"] == {"ai_generated": "partial"}
    assert outcome["asset_record"]["parent_ids"] == [record["asset_id"]]


def test_ingest_refuses_to_overwrite_existing_semantic_json(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    result_path = env / "result.json"
    result_path.write_text(json.dumps(_valid_result(record["asset_id"])), encoding="utf-8")
    semantic_analysis.ingest("demo-project", result_path)

    with pytest.raises(semantic_analysis.SemanticAnalysisError, match="existiert bereits"):
        semantic_analysis.ingest("demo-project", result_path)


def test_ingest_rejects_unverified_cloud_scope_claim(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)  # provider_data_scope stays cloud_not_approved
    result_path = env / "result.json"
    result_path.write_text(
        json.dumps(_valid_result(record["asset_id"], scope="cloud_approved", provider="openai")),
        encoding="utf-8",
    )

    with pytest.raises(semantic_analysis.SemanticAnalysisError, match="Scope-Nachweis"):
        semantic_analysis.ingest("demo-project", result_path)

    log_path = env / "projects" / "demo-project" / "analysis" / "cloud-rejections.log.jsonl"
    assert log_path.is_file()


def test_ingest_accepts_verified_cloud_scope_claim(env: Path) -> None:
    video = _make_video(env)
    record = asset_record.register_asset(video)
    asset_record.set_rights(
        record["asset_id"],
        provider_data_scope="cloud_approved",
        approved_providers=["openai"],
        note="Freigabe fuer Test",
    )
    result_path = env / "result.json"
    result_path.write_text(
        json.dumps(_valid_result(record["asset_id"], scope="cloud_approved", provider="openai")),
        encoding="utf-8",
    )

    outcome = semantic_analysis.ingest("demo-project", result_path)

    assert Path(outcome["semantic_path"]).is_file()


def test_ingest_rejects_malformed_result(env: Path) -> None:
    result_path = env / "result.json"
    result_path.write_text(json.dumps({"not": "valid"}), encoding="utf-8")

    with pytest.raises(semantic_analysis.SemanticAnalysisError, match="Schema"):
        semantic_analysis.ingest("demo-project", result_path)
