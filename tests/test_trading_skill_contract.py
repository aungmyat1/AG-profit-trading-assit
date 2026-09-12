from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from trading_skills import MarketObservation, fingerprint_input


ROOT = Path(__file__).resolve().parents[1]


def _observation(classification: str = "BUY_SIDE_SWEEP") -> MarketObservation:
    inputs = {"symbol": "EURUSD", "timeframe": "M15", "close": 1.1}
    return MarketObservation(
        skill_id="liquidity",
        skill_version="1.0.0",
        symbol="EURUSD",
        timeframe="M15",
        observed_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        classification=classification,
        evidence={"level": 1.101},
        input_fingerprint=fingerprint_input(inputs),
    )


def test_observation_and_fingerprint_are_deterministic():
    assert _observation().to_dict() == _observation().to_dict()


@pytest.mark.parametrize(
    "classification",
    ["BUY", "SELL", "OPEN_POSITION", "EXECUTE", "PROMOTE", "AUTHORIZE"],
)
def test_observation_rejects_trade_and_authority_instructions(classification):
    with pytest.raises(ValueError):
        _observation(classification)


def test_registry_denies_strategy_lifecycle_risk_and_execution_authority():
    registry = yaml.safe_load(
        (ROOT / ".agents" / "skills" / "SKILL_REGISTRY.yaml").read_text()
    )
    authority = registry["authority"]
    assert authority["may_generate_market_observation"] is True
    assert all(value is False for key, value in authority.items() if key != "may_generate_market_observation")
    deterministic = {
        skill_id
        for skill_id, definition in registry["logical_families"].items()
        if definition.get("type") == "deterministic_trading_skill"
    }
    assert deterministic == {
        "market-bias",
        "market-structure",
        "supply-demand",
        "liquidity",
        "entry-confirmation",
        "multi-timeframe-market-context",
    }
