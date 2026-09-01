from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_large_smc_is_separate_and_fail_closed():
    registry = yaml.safe_load((ROOT / "strategies/registry.yaml").read_text(encoding="utf-8"))
    large_smc = registry["strategies"]["ST_LARGE_SMC_V1"]
    session = registry["strategies"]["ST_ASIAN_SWEEP_5R_V1"]

    assert large_smc["registered"] is True
    assert large_smc["active"] is False
    assert large_smc["research"] is True
    assert large_smc["demo_authorized"] is False
    assert large_smc["live_authorized"] is False
    assert large_smc["engine"] == "NOT_IMPLEMENTED"
    assert large_smc["config_source"] != session["config_source"]


def test_large_smc_contract_cannot_authorize_proposals_or_execution():
    contract = yaml.safe_load((ROOT / "strategies/ST_LARGE_SMC_V1.yaml").read_text(encoding="utf-8"))

    assert contract["strategy_id"] == "ST_LARGE_SMC_V1"
    assert contract["status"] == "RESEARCH_DRAFT"
    assert contract["authority"]["proposal_generation_authorized"] is False
    assert contract["authority"]["demo_authorized"] is False
    assert contract["authority"]["live_authorized"] is False
    assert contract["execution"]["automatic_execution"] is False
    assert contract["execution"]["execution_adapter"] == "NOT_CONNECTED"
    assert contract["entry"]["trigger"] == "UNSIGNED"
