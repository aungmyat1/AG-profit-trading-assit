from __future__ import annotations

import pytest

from session_scanner.checklist import spread_gate
from session_scanner.checklist_v1_1 import evaluate_instrument_checklist
from session_scanner.registry import InstrumentRegistryError, load_specs, verify_live
from session_scanner.scanner import load_scanner_config


@pytest.fixture
def cfg():
    return load_scanner_config()


def _metadata(symbol):
    return {"symbol": symbol, "digits": 2, "point": 0.01, "trade_mode_name": "full",
            "tick_size": 0.01, "tick_value": 0.01, "contract_size": 1.0,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}


@pytest.mark.parametrize("canonical", ["BTCUSD", "ETHUSD"])
def test_crypto_canonical_mapping_and_native_metadata(cfg, canonical):
    spec = load_specs({**cfg, "instruments": {canonical: cfg["instruments"][canonical]}},
                      include_crypto=True)[canonical]
    assert spec.broker_symbol == canonical
    assert spec.asset_class == "CRYPTO"
    record = verify_live(spec, _metadata(canonical))
    assert record.tick_size == 0.01 and record.contract_size == 1.0
    assert record.session_policy == "CRYPTO_24H_OBSERVATION"


def test_ambiguous_crypto_broker_alias_fails_closed(cfg):
    spec = load_specs({**cfg, "instruments": {"BTCUSD": cfg["instruments"]["BTCUSD"]}},
                      include_crypto=True)["BTCUSD"]
    with pytest.raises(InstrumentRegistryError):
        verify_live(spec, None)


def test_crypto_has_no_fx_pip_spread_or_risk_policy(cfg):
    assert spread_gate(None, "CRYPTO", None)["status"] == "FAIL"
    # spread_gate itself accepts the Quote protocol; crypto branch never consumes spread_pips.
    class Quote:
        bid, ask, spread_points, spread_price, spread_pips = 60000.0, 60000.5, 50, 0.5, 0.005
    result = spread_gate(Quote(), "CRYPTO", 1.0)
    assert result["reason"] == "SPREAD_POLICY_UNDEFINED"
    assert result["spread_price"] == 0.5 and result["spread_pct"] > 0
    assert result["spread_pips"] is None


def test_crypto_checklist_fails_closed_without_matching_cfd_contract():
    t = "2026-10-02T12:00:00+00:00"
    item = {"canonical_symbol": "BTCUSD", "broker_symbol": "BTCUSD", "asset_class": "CRYPTO",
            "data_quality_gate": "PASS", "result": "STRATEGY_CONTRACT_INCOMPLETE",
            "quote": {"status": "FRESH"},
            "data_quality": {tf: {"status": "VALID", "retry_performed": False,
                                   "last_closed_bar_utc": t} for tf in ("D1", "H1", "M15", "M5")},
            "market_state": {tf: {"status": "VALID", "structure": {"status": "VALID", "state": "BULLISH"}}
                             for tf in ("D1", "H1", "M15", "M5")}}
    facts = {"data_gate": "PASS", "contract_gap": "perpetual strategy does not cover CFD",
             "spread": {"status": "OBSERVED_ONLY", "spread_price": 0.5}}
    scan = {"data_quality_gate": "PASS", "time": {"time_gate": "PASS"}, "session": {"active_cycle": None}}
    result = evaluate_instrument_checklist(scan, item, facts)
    assert result["setup_valid"] is False
    assert result["proposal_eligible"] is False
    assert result["execution_authorized"] is False
    assert result["phases"]["context"]["evidence"]["fx_session_gate_applied"] is False
    assert "STRATEGY_CONTRACT_INCOMPLETE" in result["reason_codes"]
    assert result["phases"]["risk"]["evidence"]["position_size"] == "NOT_CALCULATED"


def test_crypto_data_phase_uses_final_retry_status():
    t = "2026-10-02T12:00:00+00:00"
    item = {"canonical_symbol": "ETHUSD", "broker_symbol": "ETHUSD", "asset_class": "CRYPTO",
            "data_quality_gate": "PASS", "quote": {"status": "FRESH"},
            "data_quality": {tf: {"status": "VALID", "retry_performed": tf == "M5",
                                   "first_read_status": "STALE" if tf == "M5" else "VALID",
                                   "second_read_status": "VALID" if tf == "M5" else None,
                                   "last_closed_bar_utc": t} for tf in ("D1", "H1", "M15", "M5")}}
    facts = {"data_gate": "PASS"}
    scan = {"data_quality_gate": "PASS", "time": {"time_gate": "PASS"}}
    result = evaluate_instrument_checklist(scan, item, facts)
    assert result["phases"]["data"]["status"] == "PASS"
    assert result["phases"]["data"]["evidence"]["history_retry"]["M5"] is True
