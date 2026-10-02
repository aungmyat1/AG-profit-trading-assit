"""AG Scanner Checklist V1.1 -- unit + offline integration tests (no network, no MT5).

Covers the mission's required cases A-G and the section-16 test requirements:
phase sequencing, fail-closed behavior, shared/typed status model, reason-code
stability, data-failure short circuit, context/location/trigger, expired signal,
TREND incomplete timing, risk ambiguity, proposal eligibility, execution_authorized
always False, proposal schema, undefined news policy, undefined spread policy,
strategy-specific RR, and backward-compatible Scanner V1 output.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from session_scanner import checklist as v1_ck
from session_scanner import checklist_v1_1 as ck11
from session_scanner.checklist_v1_1 import (ChecklistResult, DirectionPermission, PHASE_KEYS, PhaseOutcome,
                                            PhaseStatus, ReasonCode, StructureState, attach_checklist_v1_1,
                                            evaluate_instrument_checklist)
from session_scanner.proposal import build_ticket
from session_scanner.quality import FRESH, VALID, Bar, assess_quote
from session_scanner.registry import load_specs, resolve_spec, verify_live
from session_scanner.scanner import load_scanner_config
from session_scanner.strategy_adapter import (ADAPTER_NO_TRADE, ADAPTER_SIGNAL, AsianSweepAdapter,
                                              resolve_proposal_scope)

UTC = timezone.utc
PKG = Path(__file__).resolve().parents[1] / "src" / "session_scanner"
TFS = ("D1", "H1", "M15", "M5")
DAY = date(2026, 10, 2)  # Friday


@pytest.fixture(scope="module")
def cfg():
    return load_scanner_config()


# ------------------------------------------------------------------ shared status model

def test_status_and_result_vocabularies_are_typed_and_shared():
    assert {p.value for p in PhaseStatus} == {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE",
                                              "INCOMPLETE_CONTRACT"}
    assert {r.value for r in ChecklistResult} == {"READY_FOR_PROPOSAL", "NO_TRADE", "BLOCKED",
                                                  "INSUFFICIENT_DATA", "OUT_OF_SESSION"}
    assert {s.value for s in StructureState} == {"BULLISH", "BEARISH", "RANGE", "MIXED", "INSUFFICIENT"}
    assert {d.value for d in DirectionPermission} == {"LONG_ALLOWED", "SHORT_ALLOWED", "BOTH_ALLOWED",
                                                      "NO_DIRECTION"}
    # Phase statuses are the SAME strings Scaner V1 JSON consumers already know.
    assert PhaseStatus.PASS == "PASS" and PhaseStatus.FAIL == "FAIL"
    out = PhaseOutcome("data", PhaseStatus.FAIL, (ReasonCode.DATA_STALE,), {"k": 1}).as_dict()
    assert out == {"status": "FAIL", "reason_codes": ["DATA_STALE"], "evidence": {"k": 1}}
    assert json.dumps(out)  # serializes to plain JSON strings, not enum reprs


def test_reason_code_taxonomy_is_stable_and_complete():
    required = ["DATA_STALE", "DATA_GAPPED", "DATA_INVALID", "SOURCE_MISMATCH", "TIME_AUTHORITY_INVALID",
                "OUT_OF_SESSION", "HTF_DIRECTION_CONFLICT", "NEWS_POLICY_NOT_DEFINED",
                "LOCATION_NOT_REACHED", "STRATEGY_CONTRACT_INCOMPLETE",
                "NO_TRIGGER", "SIGNAL_ENTRY_WINDOW_PASSED", "ENTRY_TIMING_NOT_DEFINED_FOR_SETUP",
                "RISK_POLICY_AMBIGUOUS", "INVALID_STOP_DISTANCE", "RR_POLICY_FAILED",
                "SPREAD_POLICY_UNDEFINED", "SPREAD_TOO_WIDE", "PROPOSAL_NOT_AUTHORIZED",
                "EXECUTION_NOT_AUTHORIZED"]
    codes = {c.name: c.value for c in ReasonCode}
    for name in required:
        assert name in codes and codes[name] == name  # stable machine values, no free-form prose


# ------------------------------------------------------------------ builders (facts mirror scanner.py's bundle)

def _ta():
    from session_scanner.timebase import derive_time_authority
    return derive_time_authority({"utc_time": "2026-10-02T07:31:02Z",
                                  "trade_server_last_known_time": "2026-10-02T10:31:00"})


def _quality_ok(last_closed_m15="2026-10-02T07:15:00+00:00"):
    return {tf: {"status": VALID, "retry_performed": False, "last_closed_bar_utc": last_closed_m15,
                 "expected_last_closed_bar_utc": last_closed_m15} for tf in TFS}


def _session(active_cycle="ASIAN_LONDON"):
    return {"current_session": "LONDON", "active_cycle": active_cycle,
            "active_cycle_window_utc": ["2026-10-02T07:00:00+00:00", "2026-10-02T11:00:00+00:00"]
            if active_cycle else None}


def _scan(item, **kw):
    return {"time": {"time_gate": kw.get("time_gate", "PASS")},
            "data_quality_gate": kw.get("aggregate", "PASS"),
            "actual_source": kw.get("actual_source", "TERMINAL_MCP"),
            "data_source_degraded": kw.get("degraded", False),
            "session": kw.get("session", _session()),
            "instruments": [item]}


def _market_state(box, events, h1_state="BULLISH", gaps=()):
    return {"H1": {"structure": {"status": "VALID", "state": h1_state, "authority": "market_structure.smc_adapter",
                                 "swing_high": {"price": 1.105, "time_utc": "2026-10-02T04:00:00+00:00",
                                                "kind": "SWING_HIGH"},
                                 "swing_low": {"price": 1.095, "time_utc": "2026-10-02T02:00:00+00:00",
                                               "kind": "SWING_LOW"}}},
            "M15": {"reference_box": box, "breakout_state": {"label": "DESCRIPTIVE", "state": "INSIDE_BOX"}},
            "liquidity_events": events,
            "liquidity_contract_gaps": list(gaps)}


def _engine(res, sig, entry):
    return {"status": res.get("status"), "reason": res.get("reason"),
            "regime": (sig or {}).get("regime"), "setup": (sig or {}).get("setup"),
            "direction": (sig or {}).get("direction"),
            "signal_timestamp_utc": (sig or {}).get("signal_timestamp_utc"),
            "signal_entry_open": entry[0], "signal_entry_reason": entry[1]}


BOX = {"high": 1.1012, "low": 1.0998, "mid": 1.1005}
SWEEP_EVENT = {"event": "ASIAN_HIGH_SWEEP", "time_utc": "2026-10-02T07:15:00+00:00", "level": 1.1012,
               "wick": 1.1020, "close": 1.1005}


def _signal(**kw):
    base = {"status": "SIGNAL", "regime": "RANGE", "setup": "SWEEP", "direction": "SHORT",
            "reason_code": "UPPER_SWEEP_STRICT_PENETRATION", "entry": 1.1008, "stop_loss": 1.1020,
            "risk_distance": 0.0012, "box_high": 1.1012, "box_low": 1.0998, "box_mid": 1.1005,
            "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1",
            "signal_timestamp_utc": "2026-10-02T07:15:00+00:00",
            "signal_id": "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:EURUSD:2026-10-02"}
    base.update(kw)
    return base


def _facts(*, sig=_signal(), scope=None, spread=None, adapter_status=ADAPTER_SIGNAL,
           last_closed="2026-10-02T07:15:00+00:00", scan_allowed=True, d1=None, account=None):
    return {
        "scan_allowed": scan_allowed, "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.1",
        "strategy_timeframe": "M15", "adapter_status": adapter_status,
        "adapter_reason": (sig or {}).get("reason_code") or "NO_QUALIFIED_SWEEP_IN_WINDOW",
        "reference_bars": 24, "expected_reference_bars": 24,
        "signal": sig,
        "scope": scope if scope is not None else {"authorized": True, "reason": "PILOT_SCOPE",
                                                  "risk_per_trade_pct": 0.5,
                                                  "pilot_id": "AG_POST_ASIAN_LONDON_PILOT_V1_0_1"},
        "spread": spread if spread is not None else {"status": v1_ck.PASS, "reason": "WITHIN_CONTRACT_MAX",
                                                     "spread_pips": 1.2, "max_spread_allowed_pips": 2.0},
        "last_closed_m15_utc": last_closed,
        "d1_structure": d1 if d1 is not None else {"status": "INSUFFICIENT_STRUCTURE_HISTORY",
                                                   "state": "UNDEFINED"},
        "contract_targets": {"total_target_r": 5.0,
                             "legs": [{"leg_id": 1, "volume_pct": 0.75, "target_type": "OPPOSITE_SESSION_BOUNDARY",
                                       "fixed_r_multiple": None},
                                      {"leg_id": 2, "volume_pct": 0.25, "target_type": "FIXED_R_MULTIPLE",
                                       "fixed_r_multiple": 5.0}],
                             "time_invalidation": "15:00 GMT (New York Open Pre-market)",
                             "structural_invalidation": "M15 Candle Close fully outside the sweep wick"},
        "account": account if account is not None else {"equity": 10000.0, "currency": "USD"},
    }


def _item(symbol="EURUSD", *, broker=None, sig=_signal(), entry=(True, None), events=(SWEEP_EVENT,),
          h1_state="BULLISH", market_box=BOX, proposal=None, position_size=None, gate="PASS",
          adapter_status=ADAPTER_SIGNAL):
    res = {"status": adapter_status, "reason": (sig or {}).get("reason_code") or adapter_status}
    item = {"canonical_symbol": symbol, "broker_symbol": broker or f"{symbol}-VIP", "source": "TERMINAL_MCP",
            "data_quality": _quality_ok(), "data_quality_gate": gate,
            "quote": {"bid": 1.10050, "ask": 1.10062, "status": FRESH},
            "market_state": _market_state(market_box, list(events), h1_state),
            "engine": _engine(res, sig, entry),
            "position_size": position_size,
            "checklist": {"DATA": "PASS"}, "result": "READY", "reason": "UPPER_SWEEP_STRICT_PENETRATION"}
    if proposal is not None:
        item["proposal"] = proposal
    return item


def _v1_ticket(cfg, sig_fields=None):
    """A real V1 ticket built from the real engine signal fixture, as scanner.py builds it."""
    sigd = _signal(**(sig_fields or {}))
    adapter = AsianSweepAdapter(cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["contract"],
                                cfg["strategy_adapters"]["ST_ASIAN_SWEEP_5R_V1"]["proposal_scope"])
    rec = verify_live(resolve_spec(load_specs(cfg), "EURUSD"),
                      {"symbol": "EURUSD-VIP", "digits": 5, "point": 0.00001, "trade_mode_name": "full",
                       "contract_size": 100000.0, "currency_profit": "USD", "volume_min": 0.01,
                       "volume_step": 0.01})
    scope = resolve_proposal_scope(adapter.strategy, "ASIAN_LONDON", "EURUSD", adapter.pilots)
    now = datetime(2026, 10, 2, 7, 31, tzinfo=UTC)
    sig_obj = _engine_signal_object(sigd)
    return build_ticket(signal=sig_obj, strategy=adapter.strategy, record=rec,
                        quote=assess_quote("EURUSD-VIP",
                                           {"time_ms": "2026-10-02T10:30:57.000", "bid": 1.10050, "ask": 1.10062},
                                           _ta(), now, rec.point, rec.pip_size, 120),
                        scope=scope, account={"equity": 10000.0, "currency": "USD"},
                        session="ASIAN_LONDON", now_utc=now, market_context={}, data_freshness={})


def _engine_signal_object(sigd):
    from types import SimpleNamespace
    ts = sigd.get("signal_timestamp_utc")
    return SimpleNamespace(
        signal_id=sigd["signal_id"], strategy_id=sigd["strategy_id"],
        strategy_version=sigd["strategy_version"], symbol="EURUSD", pair_id="ASIAN_LONDON",
        reference_session="Asian", session_date=DAY, box_high=sigd["box_high"], box_low=sigd["box_low"],
        box_mid=sigd["box_mid"], regime=sigd["regime"], setup=sigd["setup"], status=sigd["status"],
        reason_code=sigd["reason_code"], direction=sigd.get("direction"), entry=sigd.get("entry"),
        stop_loss=sigd.get("stop_loss"), risk_distance=sigd.get("risk_distance"),
        signal_timestamp=datetime.fromisoformat(ts) if ts else None)


def _ready_item(cfg):
    ticket = _v1_ticket(cfg)
    return _item(proposal=ticket, position_size=None)


# ------------------------------------------------------------------ case A -- phase 0 data failure

def test_a_aggregate_gate_failure_short_circuits():
    item = _ready_item_cfg_free()
    scan = _scan(item, aggregate="FAIL")
    before = copy.deepcopy(item)
    block = evaluate_instrument_checklist(scan, item, _facts())
    assert item == before  # additive contract: evaluation itself never mutates V1's item
    assert block["phases"]["data"]["status"] == "FAIL"
    assert ReasonCode.DATA_INVALID.value in block["phases"]["data"]["reason_codes"]
    assert block["phases"]["data"]["evidence"]["aggregate_data_quality_gate"] == "FAIL"
    for name in PHASE_KEYS[1:]:
        assert block["phases"][name]["status"] == "NOT_APPLICABLE"
        assert block["phases"][name]["evidence"]["blocked_by_phase"] == "data"
    # The trigger is explicitly NOT authoritative on invalid data, even with a valid signal.
    assert block["phases"]["trigger"]["evidence"]["authoritative"] is False
    assert block["setup_valid"] is False and block["proposal_eligible"] is False
    assert block["result"] == "INSUFFICIENT_DATA" and "proposal" not in block


def _ready_item_cfg_free():
    return _item(proposal={"ticket_id": "SCAN:x", "proposal_status": "PROPOSED_INFORMATIONAL_NOT_EXECUTABLE",
                           "execution_authorized": False}, position_size=None)


def test_a_time_authority_failure_uses_canonical_time_gate_key_only():
    item = _ready_item_cfg_free()
    scan = _scan(item, time_gate="FAIL")
    block = evaluate_instrument_checklist(scan, item, _facts())
    assert block["phases"]["data"]["reason_codes"] == [ReasonCode.TIME_AUTHORITY_INVALID.value]
    assert block["result"] == "INSUFFICIENT_DATA"
    # A diagnostic ``gate`` key beside the canonical ``time_gate`` is never consulted.
    scan2 = _scan(item)
    scan2["time"]["gate"] = "FAIL"  # legacy/diagnostic alias that must not turn PASS into FAIL
    assert evaluate_instrument_checklist(scan2, item, _facts())["phases"]["data"]["status"] == "PASS"


def test_a_stale_and_gapped_series_map_to_data_reason_codes():
    item = _item(gate="FAIL")
    item["data_quality"]["M15"] = dict(item["data_quality"]["M15"], status="STALE")
    item["data_quality"]["H1"] = dict(item["data_quality"]["H1"], status="GAPPED")
    block = evaluate_instrument_checklist(_scan(item, aggregate="FAIL"), item, _facts())
    codes = block["phases"]["data"]["reason_codes"]
    assert ReasonCode.DATA_STALE.value in codes and ReasonCode.DATA_GAPPED.value in codes
    assert block["result"] == "INSUFFICIENT_DATA"


def test_a_registry_failed_instrument_fails_phase0_closed():
    item = {"canonical_symbol": "GBPUSD", "broker_symbol": "GBPUSD-VIP", "source": "TERMINAL_MCP",
            "result": "INSUFFICIENT_DATA", "reason": "FAIL_CLOSED: digits 4 != expected 5"}
    scan = _scan(item, aggregate="FAIL")
    block = evaluate_instrument_checklist(scan, item, None)
    assert block["phases"]["data"]["status"] == "FAIL"
    assert ReasonCode.DATA_INVALID.value in block["phases"]["data"]["reason_codes"]
    assert all(block["phases"][k]["status"] == "NOT_APPLICABLE" for k in PHASE_KEYS[1:])
    assert block["result"] == "INSUFFICIENT_DATA" and block["execution_authorized"] is False


# ------------------------------------------------------------------ case B -- expired signal

def test_b_expired_signal_is_fail_closed_no_trade():
    sig = _signal()
    entry = (False, "SIGNAL_ENTRY_WINDOW_PASSED")  # one closed bar later
    item = _item(sig=sig, entry=entry, adapter_status=ADAPTER_SIGNAL)
    block = evaluate_instrument_checklist(_scan(item), item,
                                          _facts(sig=sig, last_closed="2026-10-02T07:30:00+00:00"))
    trg = block["phases"]["trigger"]
    assert trg["status"] == "FAIL" and trg["reason_codes"] == ["SIGNAL_ENTRY_WINDOW_PASSED"]
    assert trg["evidence"]["signal_bar_closed"] is True and trg["evidence"]["signal_current"] is False
    assert block["setup_valid"] is False and block["proposal_eligible"] is False
    assert block["result"] == "NO_TRADE" and block["reason_codes"] == ["SIGNAL_ENTRY_WINDOW_PASSED"]
    assert "proposal" not in block


# ------------------------------------------------------------------ case C -- TREND setup with undefined entry timing

def test_c_trend_signal_without_defined_timing_is_incomplete_contract():
    sig = _signal(regime="TREND", setup="TREND", direction="LONG", reason_code="BOX_DIRECTION_V1",
                  signal_timestamp_utc=None)
    entry = (False, "ENTRY_TIMING_NOT_DEFINED_FOR_SETUP")
    box = {"high": 1.1030, "low": 1.0990, "mid": 1.1010, "complete": True}
    item = _item(sig=sig, entry=entry, market_box=box, events=())
    block = evaluate_instrument_checklist(_scan(item), item, _facts(sig=sig))
    trg = block["phases"]["trigger"]
    assert trg["status"] == "INCOMPLETE_CONTRACT"
    assert trg["reason_codes"] == ["ENTRY_TIMING_NOT_DEFINED_FOR_SETUP"]
    assert block["result"] == "BLOCKED" and "proposal" not in block
    assert block["execution_authorized"] is False


# ------------------------------------------------------------------ case D -- valid setup, ambiguous risk (USDJPY)

def test_d_valid_setup_with_ambiguous_risk_policy_is_blocked_not_no_trade():
    ambiguous_scope = {"authorized": False, "reason": "RISK_POLICY_AMBIGUOUS:SYMBOL_OUTSIDE_PILOT_UNIVERSE",
                       "risk_per_trade_pct": None, "pilot_id": "AG_POST_ASIAN_LONDON_PILOT_V1_0_1"}
    sig = _signal()
    item = _item("USDJPY", sig=sig, position_size="NOT_CALCULATED")
    item["result"], item["reason"] = "STRATEGY_NOT_AUTHORIZED", "RISK_POLICY_AMBIGUOUS"  # V1 verdict preserved
    block = evaluate_instrument_checklist(_scan(item), item, _facts(sig=sig, scope=ambiguous_scope))
    for name in ("data", "context", "location", "trigger"):
        assert block["phases"][name]["status"] == "PASS", name
    assert block["setup_valid"] is True                       # market observation preserved
    risk = block["phases"]["risk"]
    assert risk["status"] == "BLOCKED" and risk["reason_codes"] == ["RISK_POLICY_AMBIGUOUS"]
    assert risk["evidence"]["position_size"] == "NOT_CALCULATED"
    assert risk["evidence"]["risk_authority"]["generic_fallback_pct_used"] is False
    assert block["phases"]["proposal_eligibility"]["status"] == "NOT_APPLICABLE"
    assert block["proposal_eligible"] is False and block["result"] == "BLOCKED"
    assert block["reason_codes"] == ["RISK_POLICY_AMBIGUOUS"]
    assert block["execution_authorized"] is False and "proposal" not in block


# ------------------------------------------------------------------ case E -- fully proposal eligible (EURUSD)

def test_e_ready_for_proposal_with_full_ticket_contract(cfg):
    item = _ready_item(cfg)
    block = evaluate_instrument_checklist(_scan(item), item, _facts())
    assert [block["phases"][k]["status"] for k in PHASE_KEYS] == ["PASS"] * 6
    assert block["setup_valid"] is True and block["proposal_eligible"] is True
    assert block["result"] == "READY_FOR_PROPOSAL" and block["execution_authorized"] is False

    prop = block["proposal"]
    required = ["ticket_id", "timestamp_utc", "canonical_symbol", "broker_symbol", "strategy_id",
                "strategy_version", "session", "direction", "entry_type", "entry_price", "stop_loss",
                "take_profit_1", "take_profit_2", "risk_pct", "risk_amount", "position_size", "rr_tp1",
                "rr_tp2", "invalidation", "context_evidence", "location_evidence", "trigger_evidence",
                "data_source", "data_freshness", "checklist_status", "proposal_status",
                "execution_authorized"]
    for key in required:
        assert key in prop, key
    assert prop["proposal_status"] == "READY_FOR_PROPOSAL"
    assert prop["execution_authorized"] is False
    assert prop["risk_pct"] == 0.5 and prop["position_size"] == 0.41  # 50 / (0.0012 * 100000)
    assert prop["context_evidence"]["direction_permission"] in {d.value for d in DirectionPermission}
    assert prop["context_evidence"]["news"]["policy"] == "NEWS_POLICY_NOT_DEFINED"
    assert prop["location_evidence"]["poi"]["type"] == "REFERENCE_SESSION_BOUNDARY"
    assert set(prop["checklist_status"].keys()) == set(PHASE_KEYS)
    assert json.dumps(prop)

    # Scanner V1's own artifact is preserved verbatim (additive compatibility).
    assert item["proposal"]["proposal_status"] == "PROPOSED_INFORMATIONAL_NOT_EXECUTABLE"
    assert item["result"] == "READY"


# ------------------------------------------------------------------ case F -- D1/H1 conflict observational

@pytest.mark.parametrize("d1,h1,align,perm,codes", [
    ("BULLISH", "BULLISH", "ALIGNED_BULLISH", "LONG_ALLOWED", ()),
    ("BEARISH", "BEARISH", "ALIGNED_BEARISH", "SHORT_ALLOWED", ()),
    ("RANGE", "RANGE", "ALIGNED_RANGE", "BOTH_ALLOWED", ()),
    ("BULLISH", "BEARISH", "CONFLICT", "NO_DIRECTION", ("HTF_DIRECTION_CONFLICT",)),
    ("MIXED", "BULLISH", "UNRESOLVED", "NO_DIRECTION", ()),
    ("INSUFFICIENT", "BEARISH", "UNRESOLVED", "NO_DIRECTION", ()),
])
def test_f_h1_context_permission_mapping(d1, h1, align, perm, codes):
    a, p, c = ck11._alignment_and_permission(StructureState(d1), StructureState(h1))
    assert a == align and p == DirectionPermission(perm)
    assert [x.value for x in c] == list(codes)


def test_f_context_conflict_does_not_veto_a_valid_strategy_signal(cfg):
    """Existing strategy contract defines NO HTF-direction filter: a D1/H1 conflict stays
    observational and the frozen engine remains the direction authority."""
    item = _ready_item(cfg)
    bullish = {"status": "VALID", "state": "BULLISH"}
    facts = _facts(d1=bullish)  # H1 in _item defaults to BEARISH? no: BULLISH -> flip to conflict
    item["market_state"]["H1"]["structure"]["state"] = "BEARISH"
    block = evaluate_instrument_checklist(_scan(item), item, facts)
    ctx = block["phases"]["context"]
    assert ctx["status"] == "PASS"
    assert ctx["evidence"]["alignment"] == "CONFLICT"
    assert ctx["evidence"]["direction_permission"] == "NO_DIRECTION"
    assert ReasonCode.HTF_DIRECTION_CONFLICT.value in ctx["reason_codes"]
    assert block["result"] == "READY_FOR_PROPOSAL"  # no invented HTF veto
    assert block["proposal"]["direction"] == "SHORT"


def test_f_direction_permission_never_means_entry(cfg):
    item = _ready_item(cfg)  # D1=BULLISH (facts), H1=BULLISH (item) -> LONG_ALLOWED label
    block = evaluate_instrument_checklist(_scan(item), item,
                                          _facts(d1={"status": "VALID", "state": "BULLISH"}))
    ctx = block["phases"]["context"]
    assert ctx["evidence"]["direction_permission"] == "LONG_ALLOWED"
    assert ctx["evidence"]["structure_states"] == {"D1": "BULLISH", "H1": "BULLISH"}
    assert block["proposal"]["direction"] == "SHORT"  # permission is not an entry


# ------------------------------------------------------------------ case G -- undefined spread policy is observational

def test_g_undefined_spread_policy_never_becomes_an_invented_threshold(cfg):
    item = _ready_item(cfg)
    observed_only = {"status": "OBSERVED_ONLY", "reason": "SPREAD_OBSERVED", "spread_points": 87}
    block = evaluate_instrument_checklist(_scan(item), item, _facts(spread=observed_only))
    ph5 = block["phases"]["proposal_eligibility"]
    assert ph5["status"] == "PASS"  # no MAX limit was invented from the observation
    assert ReasonCode.SPREAD_POLICY_UNDEFINED.value in ph5["reason_codes"]
    assert block["result"] == "READY_FOR_PROPOSAL"


def test_spread_too_wide_per_contract_fails():
    wide = {"status": "FAIL", "reason": "SPREAD_EXCEEDS_CONTRACT_MAX", "spread_pips": 4.5,
            "max_spread_allowed_pips": 2.0}
    item = _ready_item_cfg_free()
    block = evaluate_instrument_checklist(_scan(item), item, _facts(spread=wide))
    assert block["phases"]["proposal_eligibility"]["status"] == "FAIL"
    assert block["phases"]["proposal_eligibility"]["reason_codes"] == ["SPREAD_TOO_WIDE"]
    assert block["result"] == "NO_TRADE" and "proposal" not in block


# ------------------------------------------------------------------ sequential gates, not a score

def test_fail_closed_sequencing_later_phases_cannot_compensate():
    """Mandatory earlier phase FAIL makes proposal eligibility impossible even when every
    later input is valid (signal current, scope authorized, spread fine)."""
    item = _ready_item_cfg_free()
    item["data_quality"]["M15"]["status"] = "STALE"
    item["data_quality_gate"] = "FAIL"
    block = evaluate_instrument_checklist(_scan(item, aggregate="FAIL"), item, _facts())
    assert block["result"] == "INSUFFICIENT_DATA"
    assert block["proposal_eligible"] is False and "proposal" not in block


def test_out_of_session_blocks_before_strategy_phases():
    item = _item()
    scan = _scan(item, session=_session(active_cycle=None))
    block = evaluate_instrument_checklist(scan, item, _facts())
    assert block["phases"]["context"]["status"] == "FAIL"
    assert block["phases"]["context"]["reason_codes"] == ["OUT_OF_SESSION"]
    assert all(block["phases"][k]["status"] == "NOT_APPLICABLE" for k in PHASE_KEYS[2:])
    assert block["result"] == "OUT_OF_SESSION" and block["setup_valid"] is False


def test_location_not_reached_gate_and_no_trigger_gate():
    sig_none = None
    entry = (False, None)
    item = _item(sig=sig_none, entry=entry, events=(), adapter_status=ADAPTER_NO_TRADE)
    block = evaluate_instrument_checklist(_scan(item), item, _facts(sig=sig_none,
                                                                   adapter_status=ADAPTER_NO_TRADE))
    assert block["phases"]["location"]["status"] == "FAIL"
    assert block["phases"]["location"]["reason_codes"] == ["LOCATION_NOT_REACHED"]
    assert block["phases"]["trigger"]["status"] == "NOT_APPLICABLE"
    assert block["result"] == "NO_TRADE"

    item2 = _item(sig=sig_none, entry=entry, events=(SWEEP_EVENT,), adapter_status=ADAPTER_NO_TRADE)
    item2["engine"]["status"] = ADAPTER_NO_TRADE
    item2["engine"]["reason"] = "NO_QUALIFIED_SWEEP_IN_WINDOW"
    block2 = evaluate_instrument_checklist(_scan(item2), item2, _facts(sig=sig_none,
                                                                      adapter_status=ADAPTER_NO_TRADE))
    assert block2["phases"]["location"]["status"] == "PASS"  # POI engaged, engine declined
    assert block2["phases"]["trigger"]["status"] == "FAIL"
    assert block2["phases"]["trigger"]["reason_codes"] == ["NO_TRIGGER"]
    assert block2["result"] == "NO_TRADE" and block2["setup_valid"] is False


def test_invalid_stop_distance_blocks():
    sig = _signal(risk_distance=0.0, stop_loss=1.1008)
    item = _item(sig=sig)
    block = evaluate_instrument_checklist(_scan(item), item, _facts(sig=sig))
    assert block["phases"]["risk"]["status"] == "FAIL"
    assert block["phases"]["risk"]["reason_codes"] == ["INVALID_STOP_DISTANCE"]
    assert block["result"] == "BLOCKED" and block["proposal_eligible"] is False


def test_strategy_specific_rr_without_generic_minimum(cfg):
    block = evaluate_instrument_checklist(_scan(_ready_item(cfg)), _ready_item(cfg), _facts())
    risk = block["phases"]["risk"]["evidence"]
    assert risk["contract_targets"]["total_target_r"] == 5.0
    assert risk["contract_targets"]["min_rr_policy_defined"] is False
    assert "RR_POLICY_FAILED" not in block["phases"]["risk"]["reason_codes"]  # none defined, none imposed


def test_symbol_outside_strategy_contract_is_blocked_not_rewritten():
    sig = _signal()
    entry = (False, None)
    item = _item(sig=None, entry=entry, events=(), adapter_status="SYMBOL_NOT_IN_CONTRACT")
    item["market_state"] = _market_state(None, [], "BULLISH")
    block = evaluate_instrument_checklist(
        _scan(item), item,
        _facts(sig=sig, adapter_status="SYMBOL_NOT_IN_CONTRACT", scope=None))
    # No POI from the contract -> location cannot pass; the block stays fail-closed either way.
    assert block["result"] in ("NO_TRADE", "BLOCKED")
    assert block["proposal_eligible"] is False and block["execution_authorized"] is False
    assert "proposal" not in block


# ------------------------------------------------------------------ news policy observational

def test_news_policy_is_observational_and_never_blocking(cfg):
    item = _ready_item(cfg)
    block = evaluate_instrument_checklist(_scan(item), item, _facts())
    news = block["phases"]["context"]["evidence"]["news"]
    assert news["policy"] == "NEWS_POLICY_NOT_DEFINED" and news["blocking"] is False
    assert "minutes_to_event" not in news and "blackout_window" not in news
    assert ReasonCode.NEWS_POLICY_NOT_DEFINED.value in block["phases"]["context"]["reason_codes"]
    assert block["result"] == "READY_FOR_PROPOSAL"  # never silently blocked


# ------------------------------------------------------------------ invariants across every path

@pytest.mark.parametrize("scenario", range(8))
def test_execution_authorized_is_false_on_every_path(scenario, cfg):
    builders = [
        lambda: (_item(), _facts()),
        lambda: (_ready_item(cfg), _facts()),
        lambda: (_item(sig=_signal(regime="TREND", signal_timestamp_utc=None), entry=(False, "X")),
                 _facts(sig=_signal(regime="TREND", signal_timestamp_utc=None))),
        lambda: (_item(gate="FAIL"), _facts()),
        lambda: (_item(entry=(False, "SIGNAL_ENTRY_WINDOW_PASSED")),
                 _facts(last_closed="2026-10-02T07:30:00+00:00")),
        lambda: (_item(position_size="NOT_CALCULATED"),
                 _facts(scope={"authorized": False, "reason": "RISK_POLICY_AMBIGUOUS:X",
                               "risk_per_trade_pct": None, "pilot_id": "p"})),
        lambda: (_item(sig=None, entry=(False, None), events=(), adapter_status=ADAPTER_NO_TRADE),
                 _facts(sig=None, adapter_status=ADAPTER_NO_TRADE)),
        lambda: (_item(), _facts(spread={"status": "FAIL", "reason": "SPREAD_EXCEEDS_CONTRACT_MAX"})),
    ]
    item, facts = builders[scenario]()
    scan = _scan(item, aggregate=item.get("data_quality_gate", "PASS"))
    block = evaluate_instrument_checklist(scan, item, facts)
    assert block["execution_authorized"] is False
    assert block.get("proposal", {}).get("execution_authorized", False) is False
    assert {block["phases"][k]["status"] for k in PHASE_KEYS} <= {p.value for p in PhaseStatus}
    for name in PHASE_KEYS:
        assert set(block["phases"][name]["reason_codes"]) <= {c.value for c in ReasonCode}
    assert block["result"] in {r.value for r in ChecklistResult}
    json.dumps(block)


# ------------------------------------------------------------------ scan attachment + backward compatibility

def test_attach_is_additive_and_scan_level_summary(cfg):
    ready = _ready_item(cfg)
    pending = _item("USDJPY", entry=(False, "SIGNAL_ENTRY_WINDOW_PASSED"))
    facts = _facts(last_closed="2026-10-02T07:30:00+00:00")
    scan = _scan(ready)
    scan["instruments"].append(pending)
    before = copy.deepcopy(scan["instruments"])
    out = attach_checklist_v1_1(scan, {"EURUSD": _facts(), "USDJPY": facts})
    eur, jpy = out["instruments"]
    for orig, mutated in zip(before, out["instruments"]):
        for key in orig:  # every pre-existing key preserved verbatim
            assert mutated[key] == orig[key]
    assert eur["checklist_v1_1"]["result"] == "READY_FOR_PROPOSAL"
    assert jpy["checklist_v1_1"]["result"] == "NO_TRADE"
    assert jpy["checklist_v1_1"]["reason_codes"] == ["SIGNAL_ENTRY_WINDOW_PASSED"]
    summary = out["checklist_v1_1"]
    assert summary["version"] == "AG_SCANNER_CHECKLIST_V1_1"
    assert summary["summary"]["READY_FOR_PROPOSAL"] == 1 and summary["summary"]["NO_TRADE"] == 1
    assert summary["execution_authorized"] is False
    json.dumps(out)


# ------------------------------------------------------------------ static safety audit (mission section 17)

_MUTATING = re.compile(r"trade_send_market_order|trade_send_pending_order|trade_modify_sl_tp|"
                       r"trade_delete_order|trade_close_single_position|trade_close_by_position|"
                       r"order_send|order_check|mt5_gateway|management_gateway|"
                       r"execution\.(executor|coordinator)")


def test_v1_1_layer_has_no_broker_mutation_path():
    files = [PKG / "checklist_v1_1.py", PKG / "scanner.py", PKG / "report.py"]
    files += [Path(__file__).resolve().parents[1] / "scripts" / "run_session_scan.py"]
    for path in files:
        assert not _MUTATING.search(path.read_text(encoding="utf-8")), path.name


# ------------------------------------------------------------------ offline integration through _run_source_scan

class _FakeSource:
    """Full read-only MarketDataSource double: server wall-clock bars with the V1 unit-test
    sweep fixture injected on 2026-10-02 so all four symbols produce an engine signal."""

    source_name = "TERMINAL_MCP"
    OFFSET_H = 3

    def __init__(self, now_utc: datetime):
        self.now_utc = now_utc
        self.now_server = now_utc.replace(tzinfo=None) + timedelta(hours=self.OFFSET_H)

    def time_information(self):
        return {"utc_time": self.now_utc.isoformat(),
                "trade_server_last_known_time": self.now_server.isoformat(timespec="seconds")}

    def symbol_info(self, broker_symbol):
        base = broker_symbol.replace("-VIP", "")
        digits, point, size = (3, 0.001, 100000.0) if base == "USDJPY" else ((2, 0.01, 100.0)
                                                                             if base == "XAUUSD" else (5, 0.00001, 100000.0))
        return {"symbol": broker_symbol, "digits": digits, "point": point, "trade_mode_name": "full",
                "contract_size": size, "currency_profit": "USD", "volume_min": 0.01, "volume_step": 0.01}

    def ticks(self, broker_symbol, frm, to):
        s = self._scale(broker_symbol)
        return [{"time_ms": (self.now_server - timedelta(seconds=5)).isoformat(timespec="milliseconds"),
                 "bid": round(1.10050 * s, 6), "ask": round(1.10062 * s, 6)}]

    def account_info(self):
        return {"equity": 10000.0, "balance": 10000.0, "currency": "USD", "type": "demo", "server": "T"}

    @staticmethod
    def _scale(bs):
        return {"USDJPY": 150.0 / 1.1005, "XAUUSD": 2000.0 / 1.1005}.get(bs.split("-")[0], 1.0)

    def bars(self, broker_symbol, timeframe, frm, to):
        step = timedelta(minutes={"M5": 5, "M15": 15, "H1": 60, "D1": 1440}[timeframe])
        t = self._floor(frm, step)
        scale = self._scale(broker_symbol)
        metal = broker_symbol.startswith("XAU")
        overrides = self._m15_fixture(scale) if timeframe == "M15" else {}
        out, i = [], 0
        while t <= self.now_server + timedelta(minutes=1):
            i += 1
            if t.weekday() < 5 and not (metal and timeframe != "D1" and self._in_break(t, step)):
                if timeframe == "D1":
                    o, h, l, c = 1.1000, 1.1012, 1.0998, 1.1005
                else:
                    o, c = (1.1000, 1.1010) if i % 2 == 0 else (1.1010, 1.1000)
                    h, l = 1.1012, 1.0998
                o, h, l, c = overrides.get(t, (o, h, l, c))
                out.append({"time": t.isoformat(timespec="seconds"), "open": o * scale, "high": h * scale,
                            "low": l * scale, "close": c * scale, "tick_volume": 100, "spread": 15})
            t += step
        return out

    @staticmethod
    def _floor(t, step):
        if step >= timedelta(hours=24):
            return t.replace(hour=0, minute=0, second=0, microsecond=0)
        m = int(step.total_seconds() // 60)
        minute = (t.hour * 60 + t.minute) - (t.hour * 60 + t.minute) % m
        return t.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minute)

    @staticmethod
    def _in_break(t, step):
        return t.time() >= datetime.strptime("00:00", "%H:%M").time() and \
            (t + step - timedelta(microseconds=1)).time() < datetime.strptime("01:00", "%H:%M").time()

    @staticmethod
    def _m15_fixture(scale):
        day = date(2026, 10, 2)

        def at(h, m=0):
            return datetime(day.year, day.month, day.day, h, m)

        fx = {}
        t = at(3, 0)  # 00:00-06:00 UTC Asian == 03:00-09:00 server
        i = 0
        while t < at(9, 0):
            fx[t] = ((1.1000, 1.1012, 1.0998, 1.1010) if i % 2 == 0 else (1.1010, 1.1012, 1.0998, 1.1000))
            i, t = i + 1, t + timedelta(minutes=15)
        for k in range(4):  # 06:00-06:45 UTC
            fx[at(9, 15 * k)] = (1.1005, 1.1008, 1.1002, 1.1005)
        fx[at(10, 0)] = (1.1005, 1.1009, 1.1001, 1.1008)   # 07:00 UTC
        fx[at(10, 15)] = (1.1008, 1.1020, 1.1003, 1.1005)  # 07:15 UTC: strict sweep of box high
        fx[at(10, 30)] = (1.1005, 1.1006, 1.1004, 1.1005)  # forming bar
        return {k: v for k, v in fx.items()}


@pytest.fixture(scope="module")
def integrated_scan(cfg):
    from session_scanner import scanner as scanner_module
    now_utc = datetime(2026, 10, 2, 7, 31, 5, tzinfo=UTC)
    return scanner_module._run_source_scan(_FakeSource(now_utc), cfg, now_utc)


def test_integration_scan_passes_v1_gates_and_is_decorated(integrated_scan):
    out = integrated_scan
    assert out["time"]["time_gate"] == "PASS" and out["data_quality_gate"] == "PASS"
    assert all(i["data_quality_gate"] == "PASS" for i in out["instruments"])
    assert out["checklist_v1_1"]["version"] == "AG_SCANNER_CHECKLIST_V1_1"
    assert set(out["checklist_v1_1"]["results"]) == {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD"}
    json.dumps(out)


def test_integration_ready_symbols_and_v1_output_preserved(integrated_scan):
    items = {i["canonical_symbol"]: i for i in integrated_scan["instruments"]}
    for sym in ("EURUSD", "GBPUSD"):
        v11 = items[sym]["checklist_v1_1"]
        assert [v11["phases"][k]["status"] for k in PHASE_KEYS] == ["PASS"] * 6, sym
        assert v11["result"] == "READY_FOR_PROPOSAL" and v11["proposal_eligible"] is True
        assert v11["execution_authorized"] is False and v11["proposal"]["execution_authorized"] is False
        assert v11["proposal"]["proposal_status"] == "READY_FOR_PROPOSAL"
        assert v11["proposal"]["risk_pct"] == 0.5
        # Scanner V1's frozen output is still there, unchanged in role.
        assert items[sym]["result"] == "READY"
        assert items[sym]["proposal"]["proposal_status"] == "PROPOSED_INFORMATIONAL_NOT_EXECUTABLE"
        assert items[sym]["checklist"]["TRIGGER"] == "PASS"


def test_integration_risk_ambiguity_and_separation(integrated_scan):
    items = {i["canonical_symbol"]: i for i in integrated_scan["instruments"]}
    for sym in ("USDJPY", "XAUUSD"):
        v11 = items[sym]["checklist_v1_1"]
        assert v11["setup_valid"] is True, sym                    # analytical setup preserved
        assert v11["phases"]["risk"]["status"] == "BLOCKED"
        assert v11["phases"]["risk"]["reason_codes"] == ["RISK_POLICY_AMBIGUOUS"]
        assert v11["phases"]["risk"]["evidence"]["position_size"] == "NOT_CALCULATED"
        assert v11["result"] == "BLOCKED" and v11["proposal_eligible"] is False
        assert "proposal" not in v11
        assert items[sym]["result"] == "STRATEGY_NOT_AUTHORIZED"  # V1 vocabulary untouched
        assert items[sym]["reason"] == "RISK_POLICY_AMBIGUOUS"
        assert items[sym]["position_size"] == "NOT_CALCULATED"
    summary = integrated_scan["checklist_v1_1"]["summary"]
    assert summary["READY_FOR_PROPOSAL"] == 2 and summary["BLOCKED"] == 2
    assert integrated_scan["checklist_v1_1"]["execution_authorized"] is False
