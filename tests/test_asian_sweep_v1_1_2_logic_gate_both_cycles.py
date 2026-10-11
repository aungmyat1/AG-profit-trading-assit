"""AGP-C3-ASW-RATIFY: Logic Gate L1-L6 for ST_ASIAN_SWEEP_5R_V1@1.1.2 on ASIAN_LONDON and LONDON_NEWYORK.

Hermetic: recorded EURUSD M15 fixture only (no network, no MT5). The candidate contract is replayed
offline via build_fx_ticket(strategy_path=...); the runtime keeps loading v1.1.1. Every Phase B
divergence row recorded for v1.1.1 is mapped to the check that pins its v1.1.2 resolution.
Spread values are test inputs, not recorded data. LOGIC_VERIFIED never implies EDGE_VERIFIED."""
from __future__ import annotations

import csv
import datetime as dt
import functools
import importlib.util
import json
import os
from pathlib import Path

import pytest

from strategy_engine import load_strategy
from strategy_engine.session import Candle
from v1_tickets import fx
from v1_tickets.authority import load_registry
from v1_tickets.fx import STRATEGY_PATH, build_fx_ticket, session_windows_utc
from v1_tickets.logic_gate import (
    FAIL,
    NOT_APPLICABLE,
    NOT_EVALUABLE,
    PASS,
    WARN,
    blocking_failures,
    l1_determinism,
    l2_rule_conformance,
    l3_geometry,
    l4_data_session,
    l5_cost,
    l6_freshness,
)
from v1_tickets.manual_ticket import build_manual_ticket, load_owner_config

UTC = dt.timezone.utc
CANDIDATE = "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "manual_ticket" / "EURUSD_M15_recorded.csv"
CANDLES = [Candle(dt.datetime.fromisoformat(r["timestamp_utc"]).replace(tzinfo=UTC), float(r["open"]),
                  float(r["high"]), float(r["low"]), float(r["close"])) for r in csv.DictReader(FIXTURE.open())]
DAYS = ("2026-06-15", "2026-06-16", "2026-06-17", "2026-06-23", "2026-07-17")
CYCLES = {"ASIAN_LONDON": ("Asian", 24), "LONDON_NEWYORK": ("London", 20)}
TIGHT, WIDE = 0.00002, 0.00008
DECLARED_FAIL_CLOSED = {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss", "R.target_leg2",
                        "R.max_spread", "R.max_spread_fraction", "R.target_order"}
# Expected candidate L2 FAIL ids per (cycle, day) at the tight spread; None = no ticket levels (NO_SETUP).
EXPECTED_L2_FAILS = {
    ("ASIAN_LONDON", "2026-06-15"): None,
    ("ASIAN_LONDON", "2026-06-16"): {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss"},
    ("ASIAN_LONDON", "2026-06-17"): {"R.entry_level", "R.target_order"},
    ("ASIAN_LONDON", "2026-06-23"): set(),
    ("ASIAN_LONDON", "2026-07-17"): {"R.entry_level", "R.stop_loss", "R.target_leg2", "R.max_spread_fraction",
                                     "R.target_order"},
    ("LONDON_NEWYORK", "2026-06-15"): set(),
    ("LONDON_NEWYORK", "2026-06-16"): {"R.regime_branch", "R.entry_trigger", "R.entry_level", "R.stop_loss"},
    ("LONDON_NEWYORK", "2026-06-17"): {"R.entry_level", "R.max_spread_fraction", "R.target_order"},
    ("LONDON_NEWYORK", "2026-06-23"): {"R.entry_level", "R.max_spread_fraction", "R.target_order"},
    ("LONDON_NEWYORK", "2026-07-17"): {"R.max_spread_fraction", "R.target_order"},
}


@pytest.fixture(autouse=True)
def _no_repo_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def windows(cycle: str, day: str, *, drop_ref: int = 0):
    d = dt.date.fromisoformat(day)
    w = session_windows_utc(d)[cycle]
    now = w["trade"][1]
    session = [c for c in CANDLES if w["ref"][0] <= c.time < w["ref"][1]][drop_ref:]
    post = [c for c in CANDLES if w["trade"][0] <= c.time < w["trade"][1] and c.time + dt.timedelta(minutes=15) <= now]
    return d, w, now, session, post


def gates(cycle: str, day: str, path: str = CANDIDATE, spread: float = TIGHT):
    strategy = load_strategy(path)
    ref_name, bars = CYCLES[cycle]
    d, w, now, session, post = windows(cycle, day)

    def build():
        return build_fx_ticket("EURUSD", cycle, d, session, bars, post, data_source="FIXTURE",
                               evaluated_at=now, data_close=now, spread=spread, strategy_path=path)
    t = build()
    if t.get("direction") is None:
        return t, None
    return t, {
        "L1": l1_determinism(build, session + post, now),
        "L2": l2_rule_conformance(strategy, t, session, bars, post, digits=5, spread=spread),
        "L3": l3_geometry(t, post, digits=5, declared_rr=5.0),
        "L4": l4_data_session(t, ref_window=w["ref"], trade_window=w["trade"], reference_name=ref_name,
                              session=session, expected_bar_count=bars, post=post, data_close=now, now=now),
        "L5": l5_cost(spread, t.get("risk_distance"), commission_r=None, warn_r=None),
        "L6": l6_freshness(t.get("valid_until") or "set", {"x": 1}, {"y": 1}),
    }


def failing(gate):
    return {c["id"] for c in gate["checks"] if c["verdict"] in (FAIL, NOT_EVALUABLE)}


def check(gate, cid):
    return next(c for c in gate["checks"] if c["id"] == cid)


@pytest.mark.parametrize("cycle,day", sorted(EXPECTED_L2_FAILS))
def test_l1_to_l6_per_fixture_fail_only_on_declared_rules(cycle, day):
    t, g = gates(cycle, day)
    expected = EXPECTED_L2_FAILS[(cycle, day)]
    if expected is None:
        assert (g, t["decision"], t["reason_code"]) == (None, "NO_TRADE", "NO_SETUP_BY_WINDOW_END")
        return
    assert g["L1"]["status"] == PASS and g["L4"]["status"] == PASS            # determinism, data/session windows
    assert failing(g["L2"]) == expected and expected <= DECLARED_FAIL_CLOSED  # no undeclared divergence
    assert not any(c["verdict"] == NOT_EVALUABLE for c in g["L2"]["checks"])
    assert g["L3"]["status"] == (PASS if not expected else g["L3"]["status"])
    assert g["L5"]["status"] in (PASS, WARN) and g["L6"]["status"] == PASS    # advisory, never blocking
    assert t["decision"] != "READY"                                           # D6: READY stays OFF


@pytest.mark.parametrize("cycle,day,direction,entry,sl", [
    ("ASIAN_LONDON", "2026-06-23", "SHORT", 1.143, 1.14351),
    ("LONDON_NEWYORK", "2026-06-15", "SHORT", 1.16148, 1.16191),
])
def test_conforming_sweep_passes_l1_to_l4_in_each_cycle(cycle, day, direction, entry, sl):
    t, g = gates(cycle, day)
    assert (t["setup"], t["direction"], t["entry"], t["stop_loss"]) == ("SWEEP", direction, entry, sl)
    assert blocking_failures(g) == [], {k: failing(v) for k, v in g.items()}
    assert g["L6"]["status"] == PASS


def test_l1_determinism_is_byte_identical_across_rebuilds():
    for cycle in CYCLES:
        for day in DAYS:
            a, _ = gates(cycle, day)
            b, _ = gates(cycle, day)
            assert a == b


# Phase B divergence row (v1.1.1) -> (cycle, day, spread, check id, verdict) pinning its v1.1.2 resolution.
DIVERGENCES = {
    "B-REGIME": ("LONDON_NEWYORK", "2026-06-16", TIGHT, "R.regime_branch", FAIL),      # TREND fails closed
    "B-ENTRY": ("ASIAN_LONDON", "2026-06-17", TIGHT, "R.entry_level", FAIL),           # body edge = open
    "B-STOP": ("LONDON_NEWYORK", "2026-06-15", TIGHT, "R.stop_loss", PASS),            # wick extreme
    "B-TGT-ORDER": ("LONDON_NEWYORK", "2026-07-17", TIGHT, "R.target_order", FAIL),
    "B-MINRANGE": ("ASIAN_LONDON", "2026-07-17", TIGHT, "R.stop_loss", FAIL),          # zero risk distance
    "B-SPREAD": ("ASIAN_LONDON", "2026-06-23", WIDE, "R.max_spread_fraction", FAIL),
    "B-EXPIRY": ("LONDON_NEWYORK", "2026-06-15", TIGHT, "R.signal_expiry", PASS),
    "B-TIMEINV": ("LONDON_NEWYORK", "2026-06-15", TIGHT, "R.time_invalidation", PASS),
    "B-STRUCT": ("LONDON_NEWYORK", "2026-06-15", TIGHT, "R.structural_invalidation", NOT_APPLICABLE),
}


@pytest.mark.parametrize("row", sorted(DIVERGENCES))
def test_each_v1_1_1_divergence_is_resolved_in_v1_1_2(row):
    cycle, day, spread, cid, verdict = DIVERGENCES[row]
    _, g = gates(cycle, day, spread=spread)
    assert check(g["L2"], cid)["verdict"] == verdict


@pytest.mark.parametrize("cycle", sorted(CYCLES))
def test_removed_v1_1_1_rules_are_absent_in_candidate_and_still_fail_in_frozen(cycle):
    # B-EMA / B-RANGECHK / B-STRUCT: v1.1.1 keeps its NOT_EVALUABLE rows; v1.1.2 no longer declares them.
    day = "2026-06-15" if cycle == "LONDON_NEWYORK" else "2026-06-23"
    _, cand = gates(cycle, day)
    _, frozen = gates(cycle, day, STRATEGY_PATH)
    removed = {"R.trend_bias_filter", "R.range_session_check"}
    assert not removed & {c["id"] for c in cand["L2"]["checks"]}
    assert removed | {"R.structural_invalidation", "R.stop_loss"} <= failing(frozen["L2"])


def test_range_rejection_branch_fails_closed():
    # No recorded day yields Entry 3; feed the conforming ticket relabelled as the RANGE branch.
    t, _ = gates("LONDON_NEWYORK", "2026-06-15")
    _, _, _, session, post = windows("LONDON_NEWYORK", "2026-06-15")
    g = l2_rule_conformance(load_strategy(CANDIDATE), {**t, "setup": "RANGE"}, session, 20, post, digits=5,
                            spread=TIGHT)
    c = check(g, "R.regime_branch")
    assert (c["verdict"], c["note"]) == (FAIL, "ENTRY_LEVEL_NOT_MARKET_AT_SIGNAL")


@pytest.mark.parametrize("cycle", sorted(CYCLES))
def test_incomplete_reference_and_missing_spread_are_explicit_non_ready_outcomes(cycle):
    ref_name, bars = CYCLES[cycle]
    d, _, now, session, post = windows(cycle, "2026-06-15", drop_ref=1)
    short = build_fx_ticket("EURUSD", cycle, d, session, bars, post, data_source="FIXTURE", evaluated_at=now,
                            data_close=now, spread=TIGHT, strategy_path=CANDIDATE)
    assert short["decision"] == "DATA_ERROR"                                   # INSUFFICIENT_DATA, never NO_TRADE
    d, _, now, session, post = windows(cycle, "2026-06-23")
    no_spread = build_fx_ticket("EURUSD", cycle, d, session, bars, post, data_source="FIXTURE", evaluated_at=now,
                                data_close=now, spread=None, strategy_path=CANDIDATE)
    assert no_spread["decision"] != "READY"


@pytest.mark.parametrize("cycle", sorted(CYCLES))
@pytest.mark.parametrize("day", DAYS)
def test_every_owner_ticket_path_carries_edge_verified_false(monkeypatch, cycle, day):
    # Offline replay only (test-local patch): the manual ticket reads fx.STRATEGY_PATH and fx.build_fx_ticket.
    monkeypatch.setattr(fx, "STRATEGY_PATH", CANDIDATE)
    monkeypatch.setattr(fx, "build_fx_ticket", functools.partial(build_fx_ticket, strategy_path=CANDIDATE))
    _, bars = CYCLES[cycle]
    d, _, now, session, post = windows(cycle, day)
    t = build_manual_ticket("EURUSD", cycle, d, session, bars, post, now=now, data_close=now, spread=TIGHT,
                            owner=load_owner_config(), data_source="FIXTURE")
    assert t["strategy_version"] == "1.1.2"
    assert t["invariants"]["edge_verified"] is False and t["invariants"]["orders_sent_by_system"] == 0
    assert t["state"] != "TICKET_READY" and t["owner_accept_allowed"] is False


def test_registry_keeps_runtime_on_v1_1_1_and_candidate_unadmitted():
    entry = load_registry()["ST_ASIAN_SWEEP_5R_V1"]
    cand = entry["candidate_versions"]["1.1.2"]
    assert entry["config_source"] == STRATEGY_PATH and fx.STRATEGY_PATH == STRATEGY_PATH
    assert cand["status"] == "CANDIDATE_PENDING_OWNER_CONFIRM"
    assert cand["edge_verified"] is False and cand["ticket_ready"] == "PAUSED_PENDING_OWNER_CONFIRM"
    assert (entry["demo_authorized"], entry["live_authorized"]) == (False, False)


# ------------------------------------------------------------- AGP-C3-ASW-RATIFY v2: LOGIC_VERIFICATION report


def test_verification_module_import_and_exception_preserve_explicit_evidence_root(tmp_path, monkeypatch):
    root = tmp_path / "explicit-evidence"
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(root))
    script = Path(__file__).resolve().parents[1] / "scripts/asw_v112_logic_verification.py"
    spec = importlib.util.spec_from_file_location("asw_v112_logic_verification_isolation", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert os.environ["AG_EVIDENCE_ROOT"] == str(root)

    tampered = tmp_path / "GBPUSD_M15_recorded.csv"
    tampered.write_text("tampered", encoding="utf-8")
    monkeypatch.setitem(mod.SYMBOLS["GBPUSD"], "fixture", str(tampered))
    with pytest.raises(RuntimeError, match="PROVENANCE_MISMATCH"):
        mod.verify_provenance("GBPUSD")
    assert os.environ["AG_EVIDENCE_ROOT"] == str(root)

@pytest.fixture(scope="module")
def report():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "asw_v112_logic_verification", Path(__file__).resolve().parents[1] / "scripts/asw_v112_logic_verification.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_report("2026-10-09T00:00:00Z")


def test_report_l1_identity_binds_candidate_and_frozen_contract(report):
    l1 = report["checks"]["L1_identity_and_contract"]
    assert all(l1["evidence"].values())
    assert {sym: g["L1"] for sym, g in report["gates_by_symbol"].items()} == {"EURUSD": PASS, "GBPUSD": PASS}


def test_report_l3_prefix_future_mutation_streaming_parity_per_symbol(report):
    l3 = report["checks"]["L3_temporal_causality"]
    assert all(g["L3"] == PASS for g in report["gates_by_symbol"].values())
    for sym, ev in l3["by_symbol"].items():
        assert ev["future_mutations"] > 0, sym
        assert (ev["prefix_mismatches"], ev["pre_emission_signals"], ev["streaming_batch_mismatches"],
                ev["future_mutation_mismatches"]) == (0, 0, 0, 0), sym
    # Scope: RANGE behaviour untested on recorded data (0 RANGE days in fixture).
    for sym, p in report["per_symbol"].items():
        assert "RANGE" not in p["l3_by_first_emitted_setup"], sym


def test_report_l4_recorded_zero_stop_and_tp_order_failures_reproduce_and_are_blocked(report):
    l4 = report["checks"]["L4_price_geometry"]
    rec = l4["recorded_failures"]
    assert {r["kind"] for r in rec} == {"ZERO_STOP", "TP_ORDER"} and {r["direction"] for r in rec} == {"LONG", "SHORT"}
    assert all(r["reproduces_in_engine"] and r["blocked_by_candidate"] and r["fail_closed_rule"] for r in rec)
    syn = l4["synthetic"]
    assert syn["raw_zero_stop"] > 0 and min(syn["raw_tp_inversion"].values()) > 0   # failure class reproduces
    assert (syn["admitted_zero_stop"], syn["admitted_tp_inversion"], syn["undeclared_l2_failures"]) == (0, 0, 0)
    assert syn["admitted_by_gates"] > 0
    assert all(g["L4"] == PASS for g in report["gates_by_symbol"].values())


def test_report_l5_reads_the_single_d2_carrier_and_absent_costs_warn_never_zero(report):
    root = Path(__file__).resolve().parents[1]
    l5 = report["checks"]["L5_risk_and_friction"]
    assert l5["d2_source"] == "config/owner_ticket.yaml"                       # OD1009-D2, one carrier only
    assert not (root / "config/v1_tickets/asw_v112_candidate_ticket_policy.yaml").exists()
    assert (l5["risk_pct"], l5["cost_warn_R"], l5["cost_block_R"]) == (0.5, 0.10, 0.25)
    assert l5["verdict"] == WARN and l5["block_reasons"] == []
    reasons = " ".join(l5["warn_reasons"])
    assert "COMMISSION_NOT_AVAILABLE" in reasons and "SPREAD_NOT_RECORDED" in reasons
    assert "USDJPY" in reasons and "XAUUSD" in reasons and "PENDING_AGP-C2-SYMMAP" in reasons
    assert "AUDUSD" not in reasons


def test_report_scopes_instrument_and_branch_coverage_truthfully(report):
    l2 = report["checks"]["L2_specification_engine_equivalence"]["evidence"]
    assert l2["GBPUSD"]["undeclared_cases"] == [] and l2["GBPUSD"]["conforming_not_evidenced"] == ["LONDON_NEWYORK"]
    cov = report["coverage"]
    assert cov["instruments"]["EURUSD"] == "LOGIC_VERIFIED"
    assert cov["instruments"]["GBPUSD"] == \
        "PARTIAL: 10 recorded days; conforming ticket NOT_EVIDENCED in LONDON_NEWYORK"
    assert (cov["instruments"]["USDJPY"], cov["instruments"]["XAUUSD"]) == ("PENDING_AGP-C2-SYMMAP",) * 2
    assert "AUDUSD" not in cov["instruments"]
    assert cov["branches"]["RANGE_REJECTION"].startswith("UNIT_ONLY")
    assert {c["case_id"].split(":")[1] for c in report["cases"]} == {"EURUSD", "GBPUSD"}


def test_report_day_types_come_from_the_harness_and_unseen_types_are_not_evidenced(report):
    for sym, dtypes in report["coverage"]["day_types"].items():
        counts = report["day_types"][sym]["counts"]
        for t in ("long-sweep", "short-sweep", "TREND", "no-setup"):
            assert dtypes[t] == (f"EVIDENCED ({counts[t]})" if counts[t] else "NOT_EVIDENCED")
        assert sum(counts.values()) == report["per_symbol"][sym]["cases"]


def test_report_eurusd_results_byte_identical_to_the_108_report(report):
    root = Path(__file__).resolve().parents[1]
    old = json.loads((root / "docs/status/AGP_C3_ASW_V112_LOGIC_VERIFICATION_2026-10-09.json").read_text())
    dump = lambda x: json.dumps(x, sort_keys=True, default=str)  # noqa: E731
    new = json.loads(dump(report))
    assert dump([c for c in new["cases"] if c["case_id"].startswith("recorded:EURUSD:")]) == dump(old["cases"])
    for key in ("recorded_failures", "synthetic"):
        assert dump(new["checks"]["L4_price_geometry"][key]) == dump(old["checks"]["L4_price_geometry"][key])
    assert dump(new["checks"]["L3_temporal_causality"]["by_symbol"]["EURUSD"]) == \
        dump(old["checks"]["L3_temporal_causality"]["evidence"])


def test_gbpusd_fixture_is_used_only_when_its_sha256_matches_the_provenance_note(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "asw_v112_logic_verification_prov", Path(__file__).resolve().parents[1] / "scripts/asw_v112_logic_verification.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.verify_provenance("GBPUSD")["fixture_sha256"] == \
        "f0b15f864a8bea72ad287427109106996f431047e2b283ad0777e804133b0cfe"
    root = Path(__file__).resolve().parents[1]
    tampered = tmp_path / "GBPUSD_M15_recorded.csv"
    tampered.write_bytes((root / mod.SYMBOLS["GBPUSD"]["fixture"]).read_bytes() + b"\n")
    monkeypatch.setitem(mod.SYMBOLS["GBPUSD"], "fixture", str(tampered))
    with pytest.raises(RuntimeError, match="PROVENANCE_MISMATCH"):
        mod.verify_provenance("GBPUSD")


def test_report_per_symbol_gates_and_verdicts_without_edge(report):
    # Original L2 rule: a window without a conforming ticket is NOT_EVIDENCED, never PASS; no aggregate verdict.
    assert report["gates_by_symbol"] == {
        "EURUSD": {"L1": PASS, "L2": PASS, "L3": PASS, "L4": PASS, "L5": WARN, "L6": PASS},
        "GBPUSD": {"L1": PASS, "L2": "NOT_EVIDENCED", "L3": PASS, "L4": PASS, "L5": WARN, "L6": PASS},
    }
    assert report["verdicts"] == {"EURUSD": "LOGIC_VERIFIED", "GBPUSD": "PARTIAL"}
    assert "verdict" not in report
    assert report["edge_verified"] is False and report["economic_status"] == "NOT_EVALUATED"
    assert all(c["edge_verified"] is False and c["owner_ticket_state"] != "TICKET_READY" for c in report["cases"])


# --- CCW-P1-REPLAY-01: 60-day routing and per-session matrix rules --------------------------------

_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, rel: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_d60_routing_points_at_60d_files_with_matching_provenance():
    import hashlib
    import re
    mod = _load_script("asw_v112_logic_verification_d60", "scripts/asw_v112_logic_verification.py")
    for sym, spec in mod.D60_SYMBOLS.items():
        assert spec["fixture"].endswith(f"{sym}_M15_recorded_spread_60d.csv") and spec["l4_failures"] is None
        note = (_ROOT / spec["provenance"]).read_text(encoding="utf-8")
        want = re.search(r"^- sha256: `([0-9a-f]{64})`", note, re.M).group(1)
        assert hashlib.sha256((_ROOT / spec["fixture"]).read_bytes()).hexdigest() == want


def test_d60_session_row_reports_insufficient_without_positive_examples():
    drv = _load_script("asw_v112_60d_replay", "scripts/asw_v112_60d_replay.py")
    case = {"case_id": "recorded:X:ASIAN_LONDON:2026-08-03", "direction": None, "day_type": "no-setup",
            "ticket_gate_status": None, "ticket_gate_blocking_failures": None, "l2_fail_ids": [],
            "l2_undeclared": [], "owner_ticket_L6": None,
            "geometry": {"has_levels": False, "positive_stop": True, "target_order": True},
            "causality": {"prefix_mismatches": 0, "pre_emission_signals": 0, "streaming_hash_parity": True,
                          "future_mutations": 0, "future_mutation_mismatches": 0}}
    row = drv.session_row("X", "ASIAN_LONDON", [case], {"L1": "PASS", "L4": "PASS", "L5": "WARN"})
    assert row["valid_entries"] == 0 and row["rejections_by_reason"] == {"NO_SIGNAL:no-setup": 1}
    assert row["gates"] == {"L1": "PASS", "L2": "INSUFFICIENT", "L3": "INSUFFICIENT", "L4": "INSUFFICIENT",
                            "L5": "INSUFFICIENT", "L6": "INSUFFICIENT"}
    assert "PASS" not in {row["gates"][k] for k in ("L2", "L3", "L4", "L5", "L6")}
