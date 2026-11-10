from __future__ import annotations

import pytest
from tools import higgsfield_batch_ads


def test_generate_ad_plan_creates_expected_angles_and_models() -> None:
    models = ["seedance_2_0_mini", "kling3_0"]
    plan = higgsfield_batch_ads.generate_ad_plan(
        product="Licbarska Dealflow",
        num_ads=4,
        models=models,
    )

    assert len(plan) == 4
    assert plan[0].index == 1
    assert plan[0].model == "seedance_2_0_mini"
    assert plan[1].model == "kling3_0"
    assert plan[2].model == "seedance_2_0_mini"
    assert "Licbarska Dealflow" in plan[0].prompt


def test_budget_gate_blocks_excessive_credit_cost() -> None:
    models = ["seedance_2_0_mini"]
    with pytest.raises(RuntimeError, match="Budget Gate Blocked"):
        higgsfield_batch_ads.run_batch(
            product="Licbarska Real Estate",
            campaign="test_campaign",
            num_ads=5,  # 5 * 3.0 = 15.0 credits
            models=models,
            max_credits=5.0,  # below 15.0 -> should trigger Gate
            confirm=False,
        )


def test_dry_run_does_not_require_confirm() -> None:
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
