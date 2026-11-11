from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from tools import higgsfield_batch_ads, higgsfield_video


def test_generate_ad_plan_creates_expected_angles_and_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0})
    models = ["seedance_2_0_mini", "kling3_0"]
    plan = higgsfield_batch_ads.generate_ad_plan(
        product="Licbarska Dealflow",
        num_ads=4,
        models=models,
    )

    assert len(plan) == 4
    assert plan[0].index == 1
    assert plan[0].model == "seedance_2_0_mini"
    assert plan[0].estimated_credits == 5.0
    assert plan[1].model == "kling3_0"
    assert plan[2].model == "seedance_2_0_mini"
    assert "Licbarska Dealflow" in plan[0].prompt


def test_budget_gate_blocks_excessive_credit_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0})
    models = ["seedance_2_0_mini"]
    with pytest.raises(RuntimeError, match="Budget Gate Blocked"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=5,  # 5 * 5.0 = 25.0 credits
            models=models,
            max_credits=10.0,  # below 25.0 -> should trigger Gate
            confirm=False,
        )


def test_dry_run_does_not_require_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 3.0})
    models = ["seedance_2_0_mini"]
    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Real Estate",
        campaign="test_campaign",
        num_ads=2,
        models=models,
        max_credits=10.0,
        confirm=False,
    )

    assert res["num_ads"] == 2
    assert res["confirm_flag_set"] is False
    assert len(res["items"]) == 2
    assert res["total_estimated_credits"] == 6.0


def test_confirm_blocks_when_balance_credits_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0})
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": None, "raw": "email - free plan"})
    mock_create = MagicMock()
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    with pytest.raises(RuntimeError, match="Guthaben|unbekannt|unzureichend"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=1,
            models=["seedance_2_0_mini"],
            max_credits=20.0,
            confirm=True,
        )
    assert mock_create.call_count == 0


def test_confirm_blocks_when_balance_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0})
    # Required: 2 ads * 5.0 = 10.0 credits; available: 4.0 credits
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 4.0, "raw": "email - 4 credits"})
    mock_create = MagicMock()
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    with pytest.raises(RuntimeError, match="Guthaben|unzureichend"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=2,
            models=["seedance_2_0_mini"],
            max_credits=20.0,
            confirm=True,
        )
    assert mock_create.call_count == 0


def test_confirm_succeeds_when_balance_sufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0})
    # Required: 2 ads * 5.0 = 10.0 credits; available: 50.0 credits
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "email - 50 credits"})
    mock_create = MagicMock(return_value={"success": True, "job_id": "job_123", "output": str(tmp_path / "mock.mp4")})
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Real Estate",
        campaign="test_campaign",
        num_ads=2,
        models=["seedance_2_0_mini"],
        max_credits=20.0,
        confirm=True,
    )
    assert mock_create.call_count == 2
    assert res["confirm_flag_set"] is True


def test_fail_closed_without_known_price_on_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wrapper returns no credits / error
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {})
    models = ["seedance_2_0_mini"]
    with pytest.raises(RuntimeError, match="fail-closed|unbekannt"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=1,
            models=models,
            max_credits=10.0,
            confirm=True,
        )


def test_production_run_calls_create_video_and_persists_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 4.0})
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "email - 50 credits"})

    mock_create = MagicMock(return_value={
        "success": True,
        "job_id": "job_abc_123",
        "output": str(tmp_path / "mock.mp4"),
    })
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Consult",
        campaign="b2b_sprint",
        num_ads=2,
        models=["seedance_2_0_mini"],
        max_credits=20.0,
        confirm=True,
    )

    assert mock_create.call_count == 2
    first_call_kwargs = mock_create.call_args_list[0].kwargs
    assert first_call_kwargs["model"] == "seedance_2_0_mini"
    assert "prompt" in first_call_kwargs
    assert "output_path" in first_call_kwargs

    # Check that manifest.json was persisted with updated item status
    manifest_file = Path(res["target_directory"]) / "manifest.json"
    assert manifest_file.is_file()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest_data["items"]) == 2
    for it in manifest_data["items"]:
        assert it["status"] == "ok"
        assert it["job_id"] == "job_abc_123"
        assert it["local_path"] is not None
        assert it.get("error") is None


def test_production_run_updates_manifest_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 4.0})
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "email - 50 credits"})

    mock_create = MagicMock(return_value={
        "success": False,
        "error": "Rate limit exceeded on provider",
        "job": {"id": "job_fail_999"},
    })
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Consult",
        campaign="b2b_sprint",
        num_ads=1,
        models=["seedance_2_0_mini"],
        max_credits=20.0,
        confirm=True,
    )

    manifest_file = Path(res["target_directory"]) / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["items"][0]["status"] == "fehler"
    assert "Rate limit" in manifest_data["items"][0]["error"]
    assert manifest_data["items"][0]["job_id"] == "job_fail_999"


@pytest.mark.parametrize("invalid_campaign", ["../x", "/abs", "a/b", "", "a" * 65])
def test_campaign_validation_rejects_path_traversal_and_invalid_names(invalid_campaign: str) -> None:
    with pytest.raises((ValueError, RuntimeError), match="Kampagne|Kampagnenname|Zielpfad"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign=invalid_campaign,
            num_ads=1,
            models=["seedance_2_0_mini"],
            max_credits=10.0,
            confirm=False,
        )


def test_production_run_partial_failure_sets_failed_count_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 4.0})
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "email - 50 credits"})

    call_count = 0

    def mock_create_video(**kw: object) -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count in (1, 3):
            raise RuntimeError("Provider connection timeout")
        return {"success": True, "job_id": "job_ok_2", "output": str(tmp_path / "mock2.mp4")}

    monkeypatch.setattr(higgsfield_video, "create_video", mock_create_video)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Consult",
        campaign="b2b_sprint",
        num_ads=2,
        models=["seedance_2_0_mini"],
        max_credits=20.0,
        confirm=True,
    )

    assert res["failed_count"] == 1
    captured = capsys.readouterr()
    assert "[TEILWEISE FEHLGESCHLAGEN] 1 von 2" in captured.out
    assert "[SUCCESS]" not in captured.out

    # CLI exitcode should be 2 on partial failure
    monkeypatch.setattr(
        "sys.argv",
        [
            "higgsfield_batch_ads.py",
            "--product", "Licbarska Consult",
            "--campaign", "b2b_sprint_cli",
            "--num-ads", "2",
            "--confirm",
        ],
    )
    exit_code = higgsfield_batch_ads.main()
    assert exit_code == 2


@pytest.mark.parametrize(
    "invalid_max_credits",
    [float("nan"), float("inf"), float("-inf"), -1.0, 0.0, 0, -1],
)
def test_run_batch_rejects_invalid_max_credits(invalid_max_credits: float) -> None:
    with pytest.raises(ValueError, match="--max-credits"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=1,
            models=["seedance_2_0_mini"],
            max_credits=invalid_max_credits,
            confirm=False,
        )


@pytest.mark.parametrize("invalid_cost", [float("nan"), float("inf"), -1.0])
def test_run_batch_blocks_when_estimate_cost_non_finite_or_negative(
    invalid_cost: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": invalid_cost}
    )
    # In confirm mode, fail-closed check should trigger because cost is invalid/unknown
    with pytest.raises(RuntimeError, match="Fail-closed|unbekannt"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=1,
            models=["seedance_2_0_mini"],
            max_credits=10.0,
            confirm=True,
        )


@pytest.mark.parametrize("invalid_balance", [float("nan"), float("inf"), -1.0])
def test_run_batch_blocks_when_balance_credits_non_finite_or_negative(
    invalid_balance: float, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(
        higgsfield_video, "estimate_cost", lambda model, prompt=None, **kw: {"credits": 5.0}
    )
    monkeypatch.setattr(
        higgsfield_video,
        "get_balance",
        lambda: {"credits": invalid_balance, "raw": f"email - {invalid_balance} credits"},
    )
    with pytest.raises(RuntimeError, match="Guthaben|unbekannt|unzureichend"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=1,
            models=["seedance_2_0_mini"],
            max_credits=20.0,
            confirm=True,
        )


def test_pre_execution_cost_check_aborts_when_second_estimate_exceeds_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "50 credits"})

    estimates = [
        {"credits": 5.0},  # plan ad 1
        {"credits": 5.0},  # plan ad 2
        {"credits": 5.0},  # pre-run ad 1 (spent: 5.0 <= 10.0)
        {"credits": 6.0},  # pre-run ad 2 (spent: 5.0 + 6.0 = 11.0 > 10.0 -> abort!)
    ]

    def mock_estimate(model: str, prompt: str | None = None, **kw: object) -> dict[str, float]:
        if estimates:
            return estimates.pop(0)
        return {"credits": 5.0}

    monkeypatch.setattr(higgsfield_video, "estimate_cost", mock_estimate)

    mock_create = MagicMock(return_value={"success": True, "job_id": "job_1", "output": str(tmp_path / "ad1.mp4")})
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Real Estate",
        campaign="budget_guard_test",
        num_ads=2,
        models=["seedance_2_0_mini"],
        max_credits=10.0,
        confirm=True,
    )

    # Only ad 1 was created, ad 2 was blocked
    assert mock_create.call_count == 1
    assert res["failed_count"] == 1

    manifest_file = Path(res["target_directory"]) / "manifest.json"
    assert manifest_file.is_file()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["items"][0]["status"] == "ok"
    assert manifest_data["items"][1]["status"] == "abgebrochen: Budget"

    # Also verify CLI exit code is non-zero
    monkeypatch.setattr(
        "sys.argv",
        [
            "higgsfield_batch_ads.py",
            "--product", "Licbarska Real Estate",
            "--campaign", "budget_guard_cli",
            "--num-ads", "2",
            "--max-credits", "10.0",
            "--confirm",
        ],
    )
    estimates.extend([
        {"credits": 5.0},
        {"credits": 5.0},
        {"credits": 5.0},
        {"credits": 6.0},
    ])
    exit_code = higgsfield_batch_ads.main()
    assert exit_code != 0


def test_pre_execution_cost_check_aborts_when_estimate_becomes_non_finite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(higgsfield_batch_ads, "EXPORT_ROOT", tmp_path)
    monkeypatch.setattr(higgsfield_video, "get_balance", lambda: {"credits": 50.0, "raw": "50 credits"})

    estimates = [
        {"credits": 5.0},  # plan ad 1
        {"credits": 5.0},  # plan ad 2
        {"credits": 5.0},  # pre-run ad 1
        {"credits": float("nan")},  # pre-run ad 2 non-finite -> abort
    ]

    def mock_estimate(model: str, prompt: str | None = None, **kw: object) -> dict[str, float]:
        if estimates:
            return estimates.pop(0)
        return {"credits": 5.0}

    monkeypatch.setattr(higgsfield_video, "estimate_cost", mock_estimate)

    mock_create = MagicMock(return_value={"success": True, "job_id": "job_1", "output": str(tmp_path / "ad1.mp4")})
    monkeypatch.setattr(higgsfield_video, "create_video", mock_create)

    res = higgsfield_batch_ads.run_batch(
        product="Licbarska Real Estate",
        campaign="budget_guard_nan",
        num_ads=2,
        models=["seedance_2_0_mini"],
        max_credits=20.0,
        confirm=True,
    )

    assert mock_create.call_count == 1
    assert res["failed_count"] == 1
    manifest_file = Path(res["target_directory"]) / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["items"][1]["status"] == "abgebrochen: Budget"





