"""OD1014 opportunity lanes (REPORT_ONLY): CCFD unverified != blocked, LSMC SHORT spread from the read-only
tick, display-only sizing preview / cost-in-R, OPPORTUNITY headers. Synthetic only: no MT5, broker,
network or Telegram.
"""
from __future__ import annotations

import ast
import datetime as dt
import math
import sys
from pathlib import Path

import pytest
from test_actionability_and_canonical_ticket import SIGNED_POLICY

from reporting import ccfd_lane, lsmc_lane
from reporting.common import ReportLaneViolation, observational_canonical
from reporting.sizing_preview import sizing_lines, sizing_preview
from telegram_delivery.adapter import render_report
from v1_tickets.scope_status import REPORT_ONLY_HEADER, report_header

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
DAY = NOW.date()
OWNER = {"risk_pct": 0.5, "risk_status": "SET"}


def ccfd_row(decision, **extra):
    return {"strategy_id": "ST_CRYPTO_CFD_SWEEP_RETEST_V1", "strategy_version": "1.0.0", "symbol": "BTCUSD",
            "cycle": "WEEKDAY", "decision": decision, "evaluated_at": NOW.isoformat(),
            "session_date": DAY.isoformat(), "reason_codes": extra.pop("reason_codes", []), **extra}


PLAN = dict(direction="SHORT", entry=62000.0, stop_loss=62400.0, tp1=61600.0, tp2=60000.0, commission_R=0)


# ------------------------------------------------------------------------------------ A1 CCFD

def test_ccfd_sole_unverified_reason_with_priced_plan_is_candidate():
    c = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED"], **PLAN),
                              now=NOW, policy=SIGNED_POLICY)
    assert c["report_class"] == "CANDIDATE" and c["scope_route"] == "REPORT_ONLY"
    assert c["decision"] not in ("READY", "WATCH_READY", "TICKET_READY")
    assert not (c["execution_authorization"] or c["demo_authorized"] or c["live_authorized"])
    # status of the 1.0.0 identity itself (registry), never borrowed from another version
    assert c["strategy_version"] == "1.0.0" and c["verification_status"] == "STALE_IDENTITY"
    assert c["opportunity_basis"] == "OD1014_UNVERIFIED_NOT_BLOCKED"


@pytest.mark.parametrize("other", ["SPREAD_TOO_WIDE", "QUOTE_STALE_OR_MISSING", "VOLUME_BELOW_MIN",
                                   "SIGNAL_STALE", "SPREAD_POLICY_UNDEFINED", "COST_TOO_HIGH"])
def test_ccfd_unverified_plus_any_other_reason_stays_blocked(other):
    c = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED", other], **PLAN),
                              now=NOW, policy=SIGNED_POLICY)
    assert c["report_class"] == "BLOCKED" and "verification_status" not in c


@pytest.mark.parametrize("missing", ["direction", "entry", "stop_loss", "tp1", "tp2"])
def test_ccfd_unverified_with_incomplete_plan_stays_blocked(missing):
    plan = {**PLAN, missing: None}
    c = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED"], **plan),
                              now=NOW, policy=SIGNED_POLICY)
    assert c["report_class"] == "BLOCKED"


def test_manual_ticket_gating_is_untouched():
    text = (ROOT / "src" / "v1_tickets" / "manual_ticket.py").read_text(encoding="utf-8")
    assert 'reasons.append("LOGIC_STATUS_NOT_VERIFIED")' in text and 'raise RuntimeError("READY with blocking reasons")' in text


def test_candidate_is_never_routed_outside_report_only():
    raw = ccfd_row("SHADOW_INFO_ONLY", **PLAN)
    with pytest.raises(ReportLaneViolation):
        observational_canonical(raw, now=NOW, report_class="READY_TICKET", policy=SIGNED_POLICY)
    c = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED"], **PLAN),
                              now=NOW, policy=SIGNED_POLICY)
    c["scope_route"] = "EXECUTABLE"
    with pytest.raises(ValueError):
        render_report(c)


# ------------------------------------------------------------------------------------ A2 LSMC

def _m5(n=40):
    from strategy_engine.session import Candle
    start = NOW - dt.timedelta(minutes=5 * n)
    return [Candle(time=start + dt.timedelta(minutes=5 * i), open=1.16, high=1.1605, low=1.1595, close=1.16)
            for i in range(n)]


def test_c10_short_evaluates_with_bid_ask_and_fails_closed_without():
    from large_smc_core.c10_stop_policy import C10StopPolicyViolation, compute_c10_stop
    stop = compute_c10_stop("SHORT", 1.1620, 1.16000, 1.16008, _m5(), pip_size=0.0001)
    assert stop.stop_price > 1.1620
    with pytest.raises(C10StopPolicyViolation) as exc:
        compute_c10_stop("SHORT", 1.1620, None, None, _m5(), pip_size=0.0001)
    assert exc.value.reason_code == "MISSING_SPREAD"


def test_runner_passes_fresh_tick_and_drops_stale_or_missing():
    import live_candles_smoke as lcs
    fresh = lambda b: (1.1600, 1.1601, NOW - dt.timedelta(minutes=1))           # noqa: E731
    stale = lambda b: (1.1600, 1.1601, NOW - dt.timedelta(minutes=lcs.STALE_MIN + 1))  # noqa: E731
    future = lambda b: (1.1600, 1.1601, NOW + dt.timedelta(minutes=1))           # noqa: E731
    assert lcs._bid_ask(fresh, "EURUSD-VIP", NOW) == (1.16, 1.1601)
    assert lcs._bid_ask(stale, "EURUSD-VIP", NOW) == (None, None)
    assert lcs._bid_ask(future, "EURUSD-VIP", NOW) == (None, None)
    assert lcs._bid_ask(lambda b: None, "EURUSD-VIP", NOW) == (None, None)


def test_watch_once_forwards_tick_to_snapshot_and_lane(monkeypatch, tmp_path):
    import live_candles_smoke as lcs
    seen = {}

    class Snap:
        state, reason_codes = "OPPORTUNITY", ()

    def fake_eval(symbol, d1, h1, m5, now, bid=None, ask=None):
        seen["snapshot"] = (bid, ask)
        return Snap()

    class Tracker:
        def poll(self, snap):
            return [type("E", (), {"to_state": "OPPORTUNITY", "alert_level": "CONFIRMATION"})()]

    def fake_observe(events, **kw):
        seen["lane"] = (kw.get("bid"), kw.get("ask"))
        return []

    monkeypatch.setattr(lcs, "evaluate_snapshot", fake_eval)
    monkeypatch.setattr("reporting.lsmc_lane.observe_events", fake_observe)
    monkeypatch.setattr(lcs, "classify", lambda *a: "OK")
    quote = lambda b: (1.1600, 1.1601, NOW - dt.timedelta(minutes=1))  # noqa: E731
    lcs._watch_once(Tracker(), "EURUSD", {"D1": [], "H1": [], "M5": _m5()}, NOW, False, journal=str(tmp_path),
                    display_broker_symbol="EURUSD-VIP", quote=quote)
    assert seen == {"snapshot": (1.16, 1.1601), "lane": (1.16, 1.1601)}


def _lsmc_event(to_state="OPPORTUNITY", **payload):
    return {"transition_id": "t1", "symbol": "EURUSD", "from_state": "NEAR_POI", "to_state": to_state,
            "alert_level": "CONFIRMATION", "reference_id": "ref-1", "evaluated_at": NOW.isoformat(),
            "trading_date": DAY.isoformat(), "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
            "payload": payload}


def test_lsmc_short_missing_quote_stays_blocked_missing_spread(tmp_path):
    opp = {"direction": "SHORT", "entry_reference": 1.1600, "stop_c10": None, "stop_reason": "MISSING_SPREAD",
           "target_c11": 1.1550, "target_reason": None, "choch_time": NOW.isoformat()}
    out = lsmc_lane.observe_events([_lsmc_event(opportunity=opp)], now=NOW, price=1.1598,
                                   archive_root=str(tmp_path), policy=SIGNED_POLICY, bid=None, ask=None)
    assert out[0]["report_class"] == "BLOCKED" and "MISSING_SPREAD" in out[0]["reason_codes"]
    assert out[0]["prices"]["sl_raw"] is None


def test_lsmc_short_candidate_carries_tick_and_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(lsmc_lane, "opportunity_rejection", lambda opp, price: None)
    opp = {"direction": "SHORT", "entry_reference": 1.1600, "stop_c10": 1.1625, "stop_reason": None,
           "target_c11": 1.1550, "target_reason": None, "choch_time": NOW.isoformat()}
    out = lsmc_lane.observe_events([_lsmc_event(opportunity=opp)], now=NOW, price=1.1598,
                                   archive_root=str(tmp_path), policy=SIGNED_POLICY, bid=1.1597, ask=1.1598)
    c = out[0]
    assert c["report_class"] == "CANDIDATE" and c["verification_status"] == "UNVERIFIED"
    assert c["sizing_inputs"]["bid"] == 1.1597 and c["sizing_inputs"]["pip_size"] == 0.0001


# ---------------------------------------------------------------------------------- A3 sizing

META = {"tick_size": 0.00001, "tick_value": 1.0, "contract_size": 100000, "volume_min": 0.01,
        "volume_max": 100.0, "volume_step": 0.01, "digits": 5}


def _cand(**inputs):
    base = {"symbol_meta": META, "pip_size": 0.0001, "bid": 1.1597, "ask": 1.1598, "commission_R": 0,
            "balance": 10000.0}
    base.update(inputs)
    return {"instrument": "EURUSD", "report_class": "CANDIDATE",
            "prices": {"entry_reference_raw": 1.1600, "sl_raw": 1.1625}, "sizing_inputs": base}


def test_sizing_preview_with_all_inputs_uses_the_sizing_authority():
    p = sizing_preview(_cand(), OWNER)
    assert p["risk_pct"] == 0.5 and p["lot"] == pytest.approx(0.2)        # 50 / (0.0025 * 1e5)
    assert p["cost_in_R"] == pytest.approx(0.0001 / 0.0025)


@pytest.mark.parametrize("inputs,reason", [
    ({"symbol_meta": None}, "SYMBOL_METADATA_MISSING"),
    ({"symbol_meta": {**META, "volume_step": 0}}, "SYMBOL_METADATA_MISSING"),
    ({"symbol_meta": {**META, "metadata_source": "SYNTHETIC_RESEARCH"}}, "SYMBOL_METADATA_MISSING"),
    ({"pip_size": None}, "PIP_EVIDENCE_MISSING"),
    ({"bid": None}, "QUOTE_MISSING"),
    ({"ask": float("nan")}, "QUOTE_MISSING"),
    ({"ask": 1.1597}, "SPREAD_INVALID"),
    ({"bid": 1.1599, "ask": 1.1598}, "SPREAD_INVALID"),
    ({"symbol_meta": {**META, "tick_value": 0.0}}, "CONVERSION_UNAVAILABLE"),
])
def test_each_missing_input_omits_both_values_with_reason(inputs, reason):
    p = sizing_preview(_cand(**inputs), OWNER)
    assert p["lot"] is None and p["cost_in_R"] is None and p["lot_reason"] == reason
    text = "\n".join(sizing_lines(_cand(**inputs), OWNER))
    assert f"sizing: n/a ({reason})" in text and "nan" not in text.lower()


@pytest.mark.parametrize("inputs,owner,reason", [
    ({"balance": None}, OWNER, "BALANCE_UNAVAILABLE"),
    ({"balance": 0}, OWNER, "BALANCE_UNAVAILABLE"),
    ({}, {"risk_pct": None, "risk_status": "RISK_CONFIG_MISSING"}, "RISK_CONFIG_MISSING"),
    ({"balance": 1.0}, OWNER, "VOLUME_BELOW_MIN"),
])
def test_lot_omitted_cost_still_shown(inputs, owner, reason):
    p = sizing_preview(_cand(**inputs), owner)
    assert p["lot"] is None and p["lot_reason"] == reason and p["cost_in_R"] > 0
    assert f"sizing: n/a ({reason})" in sizing_lines(_cand(**inputs), owner)


def test_unknown_commission_omits_cost_never_zero():
    p = sizing_preview(_cand(commission_R=None), OWNER)
    assert p["cost_in_R"] is None and p["cost_reason"] == "COMMISSION_UNKNOWN" and p["lot"] > 0
    assert sizing_preview({"prices": {}}, OWNER)["lot_reason"] == "SIZING_INPUTS_MISSING"


def test_preview_never_renders_zero_or_nan():
    for inputs in ({}, {"balance": None}, {"bid": None}, {"commission_R": None}):
        for line in sizing_lines(_cand(**inputs), OWNER):
            assert "nan" not in line.lower() and ": 0 " not in line and not line.endswith(": 0")
            for token in line.replace("(", " ").split():
                try:
                    assert not math.isclose(float(token.rstrip("R")), 0.0)
                except ValueError:
                    pass


# ---------------------------------------------------------------------------------- A4 headers

def test_header_strings():
    assert report_header("CANDIDATE", verification_status="STALE_IDENTITY") == \
        "OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE (verification: STALE_IDENTITY)"
    assert report_header("CANDIDATE", large_smc=True, verification_status="UNVERIFIED") == \
        "LARGE-SMC OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE (verification: UNVERIFIED)"
    assert report_header("CANDIDATE") .endswith("(verification: UNVERIFIED)")
    for cls in ("BLOCKED", "WATCH"):
        assert report_header(cls, verification_status="LOGIC_VERIFIED") == REPORT_ONLY_HEADER


def test_rendered_ccfd_candidate_and_blocked_headers():
    c = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED"], **PLAN),
                              now=NOW, policy=SIGNED_POLICY)
    text = render_report(c)
    assert text.splitlines()[0] == "OPPORTUNITY -- REPORT ONLY -- NON-ACTIONABLE (verification: STALE_IDENTITY)"
    assert "sizing: n/a (" in text and text.isascii()
    b = ccfd_lane.observe_row(ccfd_row("BLOCKED", reason_codes=["LOGIC_STATUS_NOT_VERIFIED", "SPREAD_TOO_WIDE"],
                                       **PLAN), now=NOW, policy=SIGNED_POLICY)
    assert render_report(b).splitlines()[0] == REPORT_ONLY_HEADER and "sizing" not in render_report(b)


# ---------------------------------------------------------------------------------- A5 / static

def test_crypto_spread_block_key_already_configured():
    from v1_tickets.crypto_cfd_policy import load_ticket_policy
    policy = load_ticket_policy()
    assert policy["spread_block_pct"] == 20.0 and "SPREAD_POLICY_UNDEFINED" not in policy["open_authorities"]


def test_no_order_calls_added_and_runner_still_guarded():
    for rel in ("src/reporting/sizing_preview.py", "src/reporting/ccfd_lane.py", "src/reporting/lsmc_lane.py",
                "src/telegram_delivery/adapter.py", "scripts/host/live_candles_smoke.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        calls = {getattr(n.func, "attr", getattr(n.func, "id", None)) for n in ast.walk(tree)
                 if isinstance(n, ast.Call)}
        assert not calls & {"order_send", "order_check"}, rel
    runner = (ROOT / "scripts" / "host" / "live_candles_smoke.py").read_text(encoding="utf-8")
    assert "mt5 = install_mt5_guard(mt5, run_id)" in runner and "from mt5.readonly_guard import install" in runner
