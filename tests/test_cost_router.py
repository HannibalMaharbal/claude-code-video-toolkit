from __future__ import annotations

import json
from pathlib import Path

import pytest

from contracts.validate_contracts import validate
from tools import asset_record, cost_router, project_init
from tools.egress_guard import EgressBlocked


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "assets")
    monkeypatch.setattr(project_init, "PROJECTS_ROOT", tmp_path / "projects")
    project_init.init_project("demo-project")
    return tmp_path


def test_decide_local_task_type_is_local_deterministic_without_approval(env: Path) -> None:
    result = cost_router.decide(
        "demo-project", "render_flyer",
        task_type="layout", tool="layout_render", operation="render_png",
        params_sha256="a" * 64,
    )

    decision = result["decision"]
    assert decision["cost_class"] == "local_deterministic"
    assert decision["approval_required"] is False
    assert "approval_status" not in decision
    assert result["cached_asset"] is None

    manifest = project_init.load_project_manifest("demo-project")
    assert manifest["cost_decisions"] == [decision]
    assert validate("project", manifest) == []


def test_decide_mixed_locality_is_included_approved_surface_without_file_gate(
    env: Path,
) -> None:
    result = cost_router.decide(
        "demo-project", "write_code",
        task_type="code", tool="claude-code", operation="edit",
        params_sha256="b" * 64,
    )

    decision = result["decision"]
    assert decision["cost_class"] == "included_approved_surface"
    # The routing table marks "code" as requires_approval=True, but that is a
    # governance flag, not the cost-router's own approval-file gate: it is
    # recorded as a system approval, never a per-step human file.
    assert decision["approval_required"] is True
    assert decision["approval_status"] == "approved"
    assert decision["approved_by"] == "system:task-routing"


def test_decide_cloud_task_type_without_approval_is_rejected(env: Path) -> None:
    with pytest.raises(cost_router.CostRouterError, match="Freigabe"):
        cost_router.decide(
            "demo-project", "generate_image",
            task_type="image_generate", tool="external-gen", operation="txt2img",
            params_sha256="c" * 64,
        )

    manifest = project_init.load_project_manifest("demo-project")
    assert manifest["cost_decisions"] == []


def test_decide_cloud_task_type_with_approval_is_still_blocked_by_egress_guard(
    env: Path,
) -> None:
    cost_router.approve("demo-project", "generate_image", by="hannibal")

    with pytest.raises(EgressBlocked):
        cost_router.decide(
            "demo-project", "generate_image",
            task_type="image_generate", tool="external-gen", operation="txt2img",
            params_sha256="c" * 64,
        )

    # Approval alone must not have written a cost_decision -- egress blocked first.
    manifest = project_init.load_project_manifest("demo-project")
    assert manifest["cost_decisions"] == []


def test_premium_without_fallback_reason_is_rejected(env: Path) -> None:
    with pytest.raises(cost_router.CostRouterError, match="fallback_reason"):
        cost_router.decide(
            "demo-project", "premium_step",
            task_type="layout", tool="external-gen", operation="premium-op",
            params_sha256="d" * 64,
            premium=True,
        )


def test_premium_without_approval_is_rejected(env: Path) -> None:
    with pytest.raises(cost_router.CostRouterError, match="Freigabe"):
        cost_router.decide(
            "demo-project", "premium_step",
            task_type="layout", tool="external-gen", operation="premium-op",
            params_sha256="d" * 64,
            premium=True, fallback_reason="Lokal keine Referenztreue moeglich",
        )


def test_approve_rejects_empty_by(env: Path) -> None:
    with pytest.raises(cost_router.CostRouterError, match="by"):
        cost_router.approve("demo-project", "some_step", by="  ")


def test_approve_rejects_unknown_project(env: Path) -> None:
    with pytest.raises(project_init.ProjectInitError):
        cost_router.approve("no-such-project", "some_step", by="hannibal")


def test_cache_hit_reuses_matching_derived_asset(
    env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _p: {"duration": 1.0, "container": "mp4", "video_codec": "h264"},
    )
    source = env / "source.mp4"
    source.write_bytes(b"source bytes")
    source_record = asset_record.register_asset(source)
    output = env / "output.mp4"
    output.write_bytes(b"derived bytes")
    derived = asset_record.register_derived(
        output, parents=[source_record["asset_id"]], role="MASTER",
        tool="ffmpeg", operation="trim", params_sha256="e" * 64,
    )

    result = cost_router.decide(
        "demo-project", "trim_step",
        task_type="video_cut", tool="ffmpeg", operation="trim",
        params_sha256="e" * 64,
    )

    assert result["decision"]["cost_class"] == "cached_asset"
    assert result["decision"]["approval_required"] is False
    assert result["cached_asset"]["asset_id"] == derived["asset_id"]


def test_decide_appends_an_append_only_cost_log_line(env: Path) -> None:
    cost_router.decide(
        "demo-project", "step-one",
        task_type="layout", tool="layout_render", operation="render_png",
        params_sha256="f" * 64,
    )
    cost_router.decide(
        "demo-project", "step-two",
        task_type="qc_visual", tool="media_validation", operation="check",
        params_sha256="1" * 64,
    )

    log_path = project_init.PROJECTS_ROOT / "demo-project" / "cost-log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    entries = [json.loads(line) for line in lines]
    assert entries[0]["step"] == "step-one"
    assert entries[1]["step"] == "step-two"


def test_decide_rejects_unknown_task_type(env: Path) -> None:
    with pytest.raises(cost_router.CostRouterError, match="Aufgabentyp"):
        cost_router.decide(
            "demo-project", "mystery_step",
            task_type="not_a_real_task_type", tool="x", operation="y",
            params_sha256="0" * 64,
        )
