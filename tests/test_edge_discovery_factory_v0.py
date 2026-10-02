"""Candidate Factory V0 tests (AG_EDGE_DISCOVERY_ACCELERATION_R1, Phase 13).

Deterministic synthetic fixtures only -- no broker, no live data, no fabricated
economic results for C001 (no BTCUSD/ETHUSD CFD dataset exists in-repo; replay tests
use clearly synthetic candles solely to prove exact contract mapping and fill math).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib

import pytest
import yaml

from market_structure.config import load_market_structure_config
from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.retest import ENTRY_TTL_M5_BARS
from strategy_engine.sweep_retest.targets import MIN_TP2_R_MULTIPLE

from crypto_cfd_contract import contract as c001_contract
from edge_discovery import EXECUTION_AUTHORIZED, PROPOSAL_AUTHORITY
from edge_discovery import friction, promotion
from edge_discovery.contractability import (
    AvailableDataset, CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN,
    DISCRETIONARY_CONDITION_PRESENT, ENTRY_CONTRACT_UNDEFINED,
    CREATED_AFTER_RESULTS, REQUIRED_DATA_UNAVAILABLE, evaluate_contractability)
from edge_discovery.dataset_ledger import (
    DatasetAccessDenied, DatasetAccessLedger, GOVERNANCE_APPROVAL_REQUIRED,
    HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL, ROLE_NOT_ALLOWED_FOR_CANDIDATE)
from edge_discovery.fast_screen import compute_metrics
from edge_discovery.models import (
    CandidateStatus, PromotionDecision, load_manifest, verify_freeze_record)
from edge_discovery.replay_c001 import (
    CandleDataset, InstrumentIsolationError, TradeRecord, replay_c001)

UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml"
FREEZE_PATH = ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json"

CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)

C001 = load_manifest(MANIFEST_PATH)


# ------------------------------------------------------------------ synthetic fixtures

def _prev_day_m5(base, hi, lo, day=6):
    t0 = dt.datetime(2026, 1, day, 0, 0, tzinfo=UTC)
    out = []
    for i in range(288):
        t = t0 + dt.timedelta(minutes=5 * i)
        out.append(Candle(time=t, open=base, high=hi if i == 100 else base,
                          low=lo if i == 150 else base, close=base, volume=1.0))
    return out


def _m5(idx, o, h, lo, c, day=7):
    return Candle(time=dt.datetime(2026, 1, day, 0, 5 * idx, tzinfo=UTC),
                  open=o, high=h, low=lo, close=c, volume=1.0)


def _h1_bearish():
    out, t = [], dt.datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(25):
        high = 90000.0 - i * 300.0
        for p in (high, high - 900.0):
            out.append(Candle(time=t, open=p, high=p + 5, low=p - 5, close=p, volume=1.0))
            t += dt.timedelta(hours=1)
    return tuple(out)


# BTCUSD SHORT: ref hi=85000 lo=82500 -> entry 84180, stop 85120, tp1 83750, tp2 82500.
BTC_SHORT_SEQUENCE = [
    _m5(0, 84400, 84450, 84350, 84400),
    _m5(1, 84300, 84350, 84180, 84200),
    _m5(2, 84250, 84500, 84220, 84480),
    _m5(3, 84480, 85120, 84300, 84360),   # sweep
    _m5(4, 84360, 84400, 84250, 84300),
    _m5(5, 84300, 84320, 84050, 84100),   # MSS
    _m5(6, 84100, 84200, 84020, 84060),   # retest -> entry 84180
]
TP1_BAR = _m5(7, 84060, 84120, 83700, 83800)    # touches TP1 83750, stop -> entry
TP2_BAR = _m5(8, 83800, 83900, 82400, 82600)    # touches TP2 82500
SL_BAR = _m5(7, 84060, 85130, 84000, 84900)     # touches stop 85120
BE_BAR = _m5(8, 83800, 84200, 83300, 84000)     # touches breakeven 84180 after TP1

RISK = 940.0
R_TP1 = (84180.0 - 83750.0) / RISK
R_TP2 = (84180.0 - 82500.0) / RISK


def _dataset(extra_bars, dataset_id="BTCUSD_SYNTH_DEV", symbol="BTCUSD",
             asset_class="CRYPTO_CFD", role="DEV"):
    m5 = tuple(_prev_day_m5(84000.0, 85000.0, 82500.0) + BTC_SHORT_SEQUENCE + extra_bars)
    return CandleDataset(dataset_id=dataset_id, symbol=symbol, asset_class=asset_class,
                         role=role, m5_candles=m5, provenance="synthetic test fixture",
                         h1_candles=_h1_bearish())


def _ledger(tmp_path):
    return DatasetAccessLedger(tmp_path / "ledger.jsonl")


def _trade(net=1.0, gross=None, cost=0.1, direction="SHORT", symbol="BTCUSD",
           hour=1, regime="BEARISH", ts="2026-01-07T00:30:00+00:00"):
    gross = net + cost if gross is None else gross
    return TradeRecord(
        candidate_id="CRYPTO_CFD_C001", dataset_id="SYNTH", strategy_id=C001.strategy_id,
        strategy_version=C001.strategy_version, symbol=symbol, direction=direction,
        sweep_time_utc=ts, mss_time_utc=ts, retest_time_utc=ts, entry_time_utc=ts,
        entry=100.0, stop=101.0, tp1=99.0, tp2=98.0, risk_distance=1.0,
        gross_r=gross, cost_r=cost, net_r=net, exit_time_utc=ts, exit_reason="TP2_HIT",
        friction_scenario="BASE", fill_model="REPLAY_FILL_MODEL_V1",
        h1_regime_at_entry=regime, entry_hour_utc=hour)


# ------------------------------------------------------------------ manifest immutability

def test_manifest_dataclass_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        C001.strategy_version = "9.9.9"  # type: ignore[misc]


def test_freeze_record_verifies_and_detects_mutation(tmp_path):
    assert verify_freeze_record(MANIFEST_PATH, FREEZE_PATH)["frozen"] is True
    tampered = tmp_path / "m.yaml"
    tampered.write_text(MANIFEST_PATH.read_text(encoding="utf-8")
                        .replace("stop_buffer_points: 0", "stop_buffer_points: 5"),
                        encoding="utf-8")
    assert verify_freeze_record(tampered, FREEZE_PATH)["frozen"] is False


def test_freeze_record_pins_contract_files_bit_exactly():
    record = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    import hashlib
    for rel, expected in record["contract_file_sha256"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected, rel
    assert record["edge_verified"] is False
    assert record["fast_screen_status"] == "NOT_EVALUATED"


# ------------------------------------------------------------------ C001 exact contract mapping

def test_c001_manifest_matches_frozen_contract_constants():
    p = C001.parameters
    assert C001.strategy_id == c001_contract.CONTRACT_ID
    assert C001.strategy_version == c001_contract.CONTRACT_VERSION
    assert C001.asset_class == c001_contract.ASSET_CLASS
    assert C001.symbols == c001_contract.INSTRUMENTS
    assert p["entry_ttl_m5_bars"] == ENTRY_TTL_M5_BARS == 3
    assert p["min_tp2_r_multiple"] == MIN_TP2_R_MULTIPLE == 1.5
    assert p["stop_buffer_points"] == c001_contract.STOP_BUFFER_POINTS == 0
    assert p["reference_expected_m5_bars"] == c001_contract.REFERENCE_EXPECTED_M5_BARS
    assert p["retest_tolerance_price"] == c001_contract.RETEST_TOLERANCE_PRICE == 0.0
    assert p["swing_length"] == load_market_structure_config().swing_length == 5
    assert C001.parameters_frozen and C001.created_before_results
    assert C001.parent_candidate is None


def test_stop_buffer_documented_as_preregistered_hypothesis_not_tick_justification():
    doc = yaml.safe_load((ROOT / "strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml")
                         .read_text(encoding="utf-8"))
    sl = doc["stop_loss_contract"]
    assert sl["stop_buffer_policy"] == "STOP_BUFFER_POLICY_V1 = ZERO_PRICE_BUFFER"
    assert sl["stop_buffer_epistemic_status"] == "PREREGISTERED_RESEARCH_HYPOTHESIS"
    rationale = sl["stop_buffer_rationale"]
    assert "INSUFFICIENT" in rationale and "NOT a claim of economic correctness" in rationale


# ------------------------------------------------------------------ status separation

def test_fast_screen_pass_is_not_edge_verified():
    assert CandidateStatus.FAST_SCREEN_PASS != CandidateStatus.EDGE_VERIFIED
    metrics = compute_metrics([_trade(net=1.0) for _ in range(20)]
                              + [_trade(net=-0.5) for _ in range(15)])
    screen, decision = promotion.decide("CRYPTO_CFD_C001", metrics, ["SYNTH"], "BASE")
    assert screen.status == "FAST_SCREEN_PASS"
    assert screen.edge_verified is False
    assert decision.next_status == CandidateStatus.FROZEN_FOR_VERIFICATION
    assert decision.full_verification_status == "FULL_VERIFICATION_PENDING"
    assert decision.edge_verified is False


def test_promotion_can_never_emit_edge_verified():
    with pytest.raises(ValueError):
        PromotionDecision("X", "FAST_SCREEN_PASS", (), CandidateStatus.EDGE_VERIFIED,
                          "FULL_VERIFICATION_PENDING")
    with pytest.raises(ValueError):
        PromotionDecision("X", "FAST_SCREEN_PASS", (),
                          CandidateStatus.FROZEN_FOR_VERIFICATION,
                          "FULL_VERIFICATION_PENDING", edge_verified=True)


# ------------------------------------------------------------------ promotion semantics

def test_fast_screen_fail_negative_net_and_friction_destroys_edge():
    metrics = compute_metrics([_trade(net=-0.05, gross=0.05, cost=0.10)
                               for _ in range(40)])
    screen, decision = promotion.decide("C", metrics, ["SYNTH"], "BASE")
    assert screen.status == "FAST_SCREEN_FAIL"
    assert promotion.NEGATIVE_NET_EXPECTANCY in screen.reason_codes
    assert promotion.FRICTION_DESTROYS_EDGE in screen.reason_codes
    assert decision.next_status == CandidateStatus.FAST_SCREEN_FAIL


def test_fast_screen_fail_profit_factor_le_1():
    metrics = compute_metrics([_trade(net=-1.0, gross=-0.9) for _ in range(35)])
    screen, _ = promotion.decide("C", metrics, ["SYNTH"], "BASE")
    assert screen.status == "FAST_SCREEN_FAIL"
    assert promotion.NET_PROFIT_FACTOR_LE_1 in screen.reason_codes
    assert promotion.NEGATIVE_GROSS_EXPECTANCY in screen.reason_codes


def test_fast_screen_inconclusive_small_sample_is_not_pass():
    metrics = compute_metrics([_trade(net=2.0) for _ in range(promotion.MIN_SAMPLE_N - 1)])
    screen, decision = promotion.decide("C", metrics, ["SYNTH"], "BASE")
    assert screen.status == "FAST_SCREEN_INCONCLUSIVE"
    assert screen.reason_codes == (promotion.INSUFFICIENT_SAMPLE,)
    assert decision.next_status == CandidateStatus.FAST_SCREEN_INCONCLUSIVE


# ------------------------------------------------------------------ contractability gate

def _cfd_dev_datasets():
    return [AvailableDataset("BTC_DEV", "BTCUSD", "CRYPTO_CFD", "DEV", ("M5",)),
            AvailableDataset("ETH_DEV", "ETHUSD", "CRYPTO_CFD", "DEV", ("M5",))]


def test_c001_contract_checks_pass_but_data_check_fails_closed():
    result = evaluate_contractability(C001, available_datasets=[])
    assert result.status == "FAIL"                      # fail closed
    assert result.reason_codes == (REQUIRED_DATA_UNAVAILABLE,)
    failing = [k for k, v in result.checks.items() if v == "FAIL"]
    assert failing == ["required_data_available"]       # every logic check passes


def test_c001_contractable_once_cfd_dev_data_exists():
    result = evaluate_contractability(C001, available_datasets=_cfd_dev_datasets())
    assert result.status == "PASS" and result.reason_codes == ()


def test_missing_contract_field_and_vague_predicate_fail():
    broken = dataclasses.replace(C001, entry_contract="")
    r = evaluate_contractability(broken, _cfd_dev_datasets())
    assert ENTRY_CONTRACT_UNDEFINED in r.reason_codes
    vague = dataclasses.replace(C001, entry_contract="enter on strong CHoCH")
    r = evaluate_contractability(vague, _cfd_dev_datasets())
    assert DISCRETIONARY_CONDITION_PRESENT in r.reason_codes
    late = dataclasses.replace(C001, created_before_results=False)
    r = evaluate_contractability(late, _cfd_dev_datasets())
    assert CREATED_AFTER_RESULTS in r.reason_codes


def test_perp_dataset_never_satisfies_cfd_requirement():
    perp_only = [AvailableDataset("BTC_PERP", "BTCUSDT", "CRYPTO_USDT_PERP", "DEV"),
                 AvailableDataset("ETH_PERP", "ETHUSDT", "CRYPTO_USDT_PERP", "DEV")]
    r = evaluate_contractability(C001, available_datasets=perp_only)
    assert r.status == "FAIL" and REQUIRED_DATA_UNAVAILABLE in r.reason_codes
    assert any(CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN in note for note in r.notes)


# ------------------------------------------------------------------ dataset ledger / holdout hygiene

def test_dataset_role_enforcement(tmp_path):
    ledger = _ledger(tmp_path)
    ok = ledger.request_access(C001, "BTC_DEV", "DEV", "FAST_SCREEN", "METRICS_VISIBLE")
    assert ok.granted is True
    denied = ledger.request_access(C001, "BTC_HOLD", "HOLDOUT", "FAST_SCREEN",
                                   "METRICS_VISIBLE")
    assert denied.granted is False
    assert denied.denial_reason == ROLE_NOT_ALLOWED_FOR_CANDIDATE


def test_holdout_requires_governance_and_reuse_is_never_independent(tmp_path):
    ledger = _ledger(tmp_path)
    holdout_ok = dataclasses.replace(C001, dataset_roles_allowed=("DEV", "HOLDOUT"))
    no_approval = ledger.request_access(holdout_ok, "HOLD", "HOLDOUT", "OOS", "BLIND")
    assert not no_approval.granted
    assert no_approval.denial_reason == GOVERNANCE_APPROVAL_REQUIRED
    first = ledger.request_access(holdout_ok, "HOLD", "HOLDOUT", "OOS", "BLIND",
                                  governance_approval_id="GOV-1")
    assert first.granted and first.independence_claim == "INDEPENDENT_FIRST_ACCESS"
    reuse_same = ledger.request_access(holdout_ok, "HOLD", "HOLDOUT", "OOS", "BLIND",
                                       governance_approval_id="GOV-1")
    assert not reuse_same.granted
    assert reuse_same.denial_reason == HOLDOUT_REUSE_REQUIRES_NEW_GOVERNANCE_APPROVAL
    reuse_new = ledger.request_access(holdout_ok, "HOLD", "HOLDOUT", "OOS", "BLIND",
                                      governance_approval_id="GOV-2")
    assert reuse_new.granted
    assert reuse_new.independence_claim == "NOT_INDEPENDENT_REPEAT_ACCESS"
    assert reuse_new.repeat_access_count == 1


def test_ledger_is_append_only_jsonl_and_records_denials(tmp_path):
    ledger = _ledger(tmp_path)
    ledger.request_access(C001, "A", "DEV", "r1", "METRICS_VISIBLE")
    ledger.request_access(C001, "B", "FINAL_OOS", "r2", "BLIND")  # denied: role not allowed
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    records = ledger.records()
    assert [r.granted for r in records] == [True, False]
    assert records[1].result_visibility == "DENIED"


# ------------------------------------------------------------------ C001 replay adapter

def test_replay_c001_tp1_tp2_path_exact_contract_numbers(tmp_path):
    trades = replay_c001(C001, _dataset([TP1_BAR, TP2_BAR]), _ledger(tmp_path),
                         "BASE", structure_config=CFG)
    assert len(trades) == 1
    t = trades[0]
    assert (t.symbol, t.direction) == ("BTCUSD", "SHORT")
    assert t.entry == pytest.approx(84180.0)
    assert t.stop == pytest.approx(85120.0)      # sweep extreme + exactly zero buffer
    assert t.tp1 == pytest.approx(83750.0)
    assert t.tp2 == pytest.approx(82500.0)
    assert t.risk_distance == pytest.approx(RISK)
    assert t.gross_r == pytest.approx(0.5 * R_TP1 + 0.5 * R_TP2)
    assert t.cost_r == pytest.approx(17.02 / RISK)
    assert t.net_r == pytest.approx(t.gross_r - t.cost_r)
    assert t.exit_reason == "TP2_HIT"
    assert t.h1_regime_at_entry == "BEARISH"
    assert t.candidate_id == "CRYPTO_CFD_C001" and t.dataset_id == "BTCUSD_SYNTH_DEV"
    # full event lineage preserved:
    assert t.sweep_time_utc == "2026-01-07T00:15:00+00:00"
    assert t.mss_time_utc == "2026-01-07T00:25:00+00:00"
    assert t.retest_time_utc == t.entry_time_utc == "2026-01-07T00:30:00+00:00"


def test_replay_c001_stop_path_is_minus_one_gross(tmp_path):
    trades = replay_c001(C001, _dataset([SL_BAR]), _ledger(tmp_path),
                         "BASE", structure_config=CFG)
    assert len(trades) == 1
    assert trades[0].exit_reason == "STOPPED"
    assert trades[0].gross_r == pytest.approx(-1.0)
    assert trades[0].net_r == pytest.approx(-1.0 - 17.02 / RISK)


def test_replay_c001_breakeven_after_tp1(tmp_path):
    trades = replay_c001(C001, _dataset([TP1_BAR, BE_BAR]), _ledger(tmp_path),
                         "BASE", structure_config=CFG)
    assert len(trades) == 1
    assert trades[0].exit_reason == "BREAKEVEN_AFTER_TP1"
    assert trades[0].gross_r == pytest.approx(0.5 * R_TP1)


def test_replay_is_deterministic_and_stress_scenario_only_changes_cost(tmp_path):
    a = replay_c001(C001, _dataset([TP1_BAR, TP2_BAR]), _ledger(tmp_path / "a"),
                    "BASE", structure_config=CFG)
    b = replay_c001(C001, _dataset([TP1_BAR, TP2_BAR]), _ledger(tmp_path / "b"),
                    "BASE", structure_config=CFG)
    assert a == b
    stress = replay_c001(C001, _dataset([TP1_BAR, TP2_BAR]), _ledger(tmp_path / "c"),
                         "STRESS", structure_config=CFG)
    assert stress[0].gross_r == pytest.approx(a[0].gross_r)   # trade identical
    assert stress[0].cost_r == pytest.approx(2 * a[0].cost_r)  # only cost scales


def test_replay_exposes_no_strategy_parameter_mutation_surface():
    import inspect
    params = set(inspect.signature(replay_c001).parameters)
    assert params == {"manifest", "dataset", "ledger", "friction_scenario",
                      "access_reason", "structure_config", "governance_approval_id"}
    # No stop/ttl/target/session/indicator knobs exist on the adapter.
    assert not params & {"stop_buffer", "ttl", "tp1", "tp2", "session", "indicator",
                         "retest_window", "stop", "target"}


# ------------------------------------------------------------------ isolation / leakage

def test_no_silent_perp_substitution_in_replay(tmp_path):
    with pytest.raises(InstrumentIsolationError, match="CROSS_INSTRUMENT_SUBSTITUTION"):
        replay_c001(C001, _dataset([], dataset_id="PERP", symbol="BTCUSDT"),
                    _ledger(tmp_path), "BASE", structure_config=CFG)
    with pytest.raises(InstrumentIsolationError, match="ASSET_CLASS_MISMATCH"):
        replay_c001(C001, _dataset([], asset_class="CRYPTO_USDT_PERP"),
                    _ledger(tmp_path), "BASE", structure_config=CFG)
    with pytest.raises(InstrumentIsolationError):
        replay_c001(C001, _dataset([], dataset_id="ETHPERP", symbol="ETHUSDT"),
                    _ledger(tmp_path), "BASE", structure_config=CFG)


def test_replay_requires_granted_dataset_access(tmp_path):
    ledger = _ledger(tmp_path)
    with pytest.raises(DatasetAccessDenied):
        replay_c001(C001, _dataset([TP1_BAR, TP2_BAR], role="VALIDATION"), ledger,
                    "BASE", structure_config=CFG)   # VALIDATION not in roles_allowed
    assert ledger.records()[-1].granted is False    # denial is itself recorded


def test_no_fx_pip_session_or_execution_leakage_in_factory_source():
    pkg = ROOT / "src" / "edge_discovery"
    source = "\n".join(p.read_text(encoding="utf-8") for p in sorted(pkg.glob("*.py")))
    forbidden = ["pip_" + "size", "forex_sl_buffer", "ASIAN_" + "SESSION",
                 "session_" + "pairs", "execution_" + "windows",
                 "from mt5", "import mt5", "order_" + "send",
                 "management_" + "gateway", "execution." + "executor",
                 "crypto_" + "symbols", "BTC" + "USDT", "ETH" + "USDT",
                 "funding_" + "rate"]
    for token in forbidden:
        assert token not in source, f"forbidden identity {token!r} leaked into edge_discovery"
    assert EXECUTION_AUTHORIZED is False and PROPOSAL_AUTHORITY == "BLOCKED"


# ------------------------------------------------------------------ friction freeze

def test_friction_scenarios_are_frozen_and_labeled_as_scenarios():
    assert friction.FRICTION_MODEL_ID == "CRYPTO_CFD_SPREAD_SCENARIOS_V1"
    assert dict(friction.SCENARIOS) == {"BASE": 1.0, "STRESS": 2.0, "SEVERE": 4.0}
    assert friction.SCREEN_SCENARIO == "BASE"        # fixed before any result exists
    assert friction.HISTORICAL_BID_ASK_AVAILABLE is False
    with pytest.raises(TypeError):
        friction.SCENARIOS["BASE"] = 0.0             # type: ignore[index]  # immutable
    f = friction.friction_for("BTCUSD", "SEVERE")
    assert f.evidence_kind.startswith("OBSERVED_LIVE_SPREAD")   # never HISTORICAL truth
    assert f.spread_price == pytest.approx(4 * 17.02)
    assert friction.friction_for("ETHUSD", "BASE").spread_price == pytest.approx(2.50)
    assert friction.cost_r("BTCUSD", "BASE", 940.0) == pytest.approx(17.02 / 940.0)
    with pytest.raises(KeyError):
        friction.friction_for("XAUUSD", "BASE")      # no evidence -> refuse, not invent
    with pytest.raises(KeyError):
        friction.friction_for("BTCUSD", "CUSTOM")    # scenarios are closed


def test_manifest_cost_assumptions_match_frozen_friction_model():
    cost = C001.cost_assumptions
    assert cost["friction_model"] == friction.FRICTION_MODEL_ID
    assert cost["evidence_kind"] == friction.EVIDENCE_KIND
    assert cost["scenarios"] == dict(friction.SCENARIOS)
    assert cost["screen_scenario"] == friction.SCREEN_SCENARIO
    assert cost["historical_bid_ask_available"] is False


# ------------------------------------------------------------------ metrics block

def test_fast_screen_metrics_block():
    trades = ([_trade(net=1.0, hour=1) for _ in range(3)]
              + [_trade(net=-0.5, hour=13, direction="LONG", regime="BULLISH",
                        symbol="ETHUSD")] * 2)
    m = compute_metrics(trades)
    assert m["N"] == 5 and m["LONG_N"] == 2 and m["SHORT_N"] == 3
    assert m["NET_R"] == pytest.approx(2.0)
    assert m["WIN_RATE"] == pytest.approx(0.6)
    assert m["PROFIT_FACTOR_NET"] == pytest.approx(3.0 / 1.0)
    assert m["MAX_DRAWDOWN_R"] <= 0
    assert set(m["BY_SYMBOL"]) == {"BTCUSD", "ETHUSD"}
    assert set(m["TIME_BUCKET_DECOMPOSITION"]) == {"00-04", "12-16"}
    assert set(m["REGIME_DECOMPOSITION"]) == {"BEARISH", "BULLISH"}
    assert "H1" in m["REGIME_AUTHORITY"]
