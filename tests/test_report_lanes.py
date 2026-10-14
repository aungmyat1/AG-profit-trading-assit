"""AGP-C18-R2 PR B: observational (REPORT_ONLY) lanes for ASW, LSMC and CCFD.

Every family produces candidate / status records; unverified scopes evaluate read-only and can never
become WATCH_READY; missing data and invalid geometry fail closed; nothing reaches an order API; the
identity-bound strategy files are untouched. Synthetic only: no MT5, broker, network or Telegram.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import sys
from pathlib import Path

import pytest
from test_actionability_and_canonical_ticket import (
    SIGNED_POLICY,
    _build_asian_london_sweep,
)

from reporting import asw_lane, ccfd_lane, lsmc_lane
from reporting.common import (
    REPORT_LANE_SUBDIR,
    ReportLaneViolation,
    non_executable,
    observational_canonical,
)
from v1_tickets.daily_evaluator import fixture_candle_provider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
DAY = NOW.date()


def provider():
    ref, n, post = _build_asian_london_sweep(NOW, age_minutes=5)
    return fixture_candle_provider(ref, n, post, spread=0.0001, current_price=1.1636,
                                   data_close=post[-1].time + dt.timedelta(minutes=15))


def lane_rows(root, family):
    rows = []
    for path in (Path(root) / REPORT_LANE_SUBDIR).glob(f"*_{family}.jsonl"):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


# ------------------------------------------------------------------------------------- common

def test_non_executable_converts_every_ready_decision():
    for decision in ("READY", "TICKET_READY", "WATCH_READY"):
        out = non_executable({"decision": decision})
        assert out["decision"] == "SHADOW_INFO_ONLY" and out["suppressed_decision"] == decision
    assert non_executable({"decision": "NO_TRADE"})["decision"] == "NO_TRADE"


def test_observational_canonical_rejects_non_observational_class():
    raw = {"strategy_id": "ST_ASIAN_SWEEP_5R_V1", "strategy_version": "1.1.2", "symbol": "USDJPY",
           "cycle": "ASIAN_LONDON", "decision": "NO_TRADE", "session_date": DAY.isoformat()}
    with pytest.raises(ReportLaneViolation):
        observational_canonical(raw, now=NOW, report_class="READY_TICKET", policy=SIGNED_POLICY)


# ---------------------------------------------------------------------------------------- ASW

def test_asw_s1_is_left_to_the_canonical_path():
    assert asw_lane.evaluate_scope("GBPUSD", "ASIAN_LONDON", now=NOW, day=DAY, candle_provider=provider(),
                                   policy=SIGNED_POLICY) is None


def test_asw_eurusd_asian_london_uses_v113_on_the_lane_only():
    """OD1014-FAST D3/D9: evaluated with the v1.1.3 identity, stamped from its own registry entry; the registry still
    records the v1.1.2 scope as SUSPENDED (never presented as verified)."""
    from v1_tickets.scope_status import resolve_ticket_scope
    c = asw_lane.evaluate_scope("EURUSD", "ASIAN_LONDON", now=NOW, day=DAY, candle_provider=provider(),
                                policy=SIGNED_POLICY)
    assert c["strategy_version"] == "1.1.3" and c["verification_status"] == "LOGIC_VERIFIED"
    assert c["scope_route"] == "REPORT_ONLY" and c["decision"] != "WATCH_READY"
    assert c["execution_authorization"] is False and "SUSPENDED_L3_REPAINT" not in c["reason_codes"]
    registry = resolve_ticket_scope("ST_ASIAN_SWEEP_5R_V1", "1.1.2", "EURUSD", "ASIAN_LONDON", "LONG")
    assert registry["scope_verification_status"] == "SUSPENDED"


def test_asw_unverified_scope_reports_a_priced_non_executable_candidate():
    c = asw_lane.evaluate_scope("USDJPY", "ASIAN_LONDON", now=NOW, day=DAY, candle_provider=provider(),
                                policy=SIGNED_POLICY)
    assert c["report_class"] == "CANDIDATE" and c["decision"] != "WATCH_READY"
    assert c["prices"]["entry_reference_raw"] is not None and c["prices"]["sl_raw"] is not None
    assert c["scope_verification_status"] == "UNVERIFIED" and c["scope_route"] == "REPORT_ONLY"
    assert c["lane"] == "REPORT_ONLY_EVALUATION" and c["execution_authorization"] is False
    assert c["strategy_version"] == "1.1.2"


@pytest.mark.parametrize("prov,reason", [(lambda *a: None, "NO_CANDLE_DATA"),
                                         (lambda *a: (_ for _ in ()).throw(OSError("feed down")), "OSError")])
def test_asw_missing_data_is_a_data_error(prov, reason):
    c = asw_lane.evaluate_scope("XAUUSD", "ASIAN_LONDON", now=NOW, day=DAY, candle_provider=prov,
                                policy=SIGNED_POLICY)
    assert c["report_class"] == "DATA_ERROR" and reason in c["reason_codes"]


def test_asw_lane_archives_seven_scopes_outside_the_ticket_store(tmp_path):
    out = asw_lane.run_asw_lane(now=NOW, day=DAY, cycles=["ASIAN_LONDON"], candle_provider=provider(),
                                archive_root=str(tmp_path), policy=SIGNED_POLICY)
    assert [c["instrument"] for c in out] == ["EURUSD", "USDJPY", "XAUUSD"]       # S1 skipped
    assert len(lane_rows(tmp_path, "session_fx_gold")) == 3
    assert not (tmp_path / "ticket_store").exists()


# --------------------------------------------------------------------------------------- LSMC

def event(to_state, **payload):
    return {"transition_id": "t1", "symbol": "EURUSD", "from_state": "IDLE", "to_state": to_state,
            "alert_level": "WATCH", "reference_id": "ref-1", "evaluated_at": NOW.isoformat(),
            "trading_date": DAY.isoformat(), "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
            "payload": payload}


OPP = {"direction": "LONG", "entry_reference": 1.1600, "stop_c10": 1.1580, "target_c11": 1.1650,
       "choch_time": NOW.isoformat(), "stop_reason": None, "target_reason": None}


def test_lsmc_near_poi_is_watch():
    c = lsmc_lane.from_event(event("NEAR_POI", poi={"direction": "LONG"}), now=NOW, policy=SIGNED_POLICY)
    assert c["report_class"] == "WATCH" and c["scope_verification_status"] == "UNVERIFIED"


def test_lsmc_complete_opportunity_is_a_priced_candidate(monkeypatch):
    monkeypatch.setattr(lsmc_lane, "opportunity_rejection", lambda opp, price: None)
    c = lsmc_lane.from_event(event("OPPORTUNITY", opportunity=OPP), now=NOW, price=1.1602, policy=SIGNED_POLICY)
    assert c["report_class"] == "CANDIDATE" and c["decision"] != "WATCH_READY"
    assert (c["prices"]["entry_reference_raw"], c["prices"]["sl_raw"]) == (1.16, 1.158)


def test_lsmc_missing_c10_is_blocked_with_the_evidence_gap_and_no_invented_stop():
    opp = {**OPP, "stop_c10": None, "stop_reason": "C10_PIP_SIZE_NOT_EVIDENCED"}
    c = lsmc_lane.from_event(event("OPPORTUNITY", opportunity=opp), now=NOW, price=1.1602, policy=SIGNED_POLICY)
    assert c["report_class"] == "BLOCKED"
    assert {"REJECT_NO_STOP", "C10_PIP_SIZE_NOT_EVIDENCED"} <= set(c["reason_codes"])
    assert c["prices"]["sl_raw"] is None and c["prices"]["entry_reference_raw"] is None


def test_lsmc_expired_is_no_opportunity(tmp_path):
    out = lsmc_lane.observe_events([event("EXPIRED")], now=NOW, price=None, archive_root=str(tmp_path),
                                   policy=SIGNED_POLICY)
    assert out[0]["report_class"] == "NO_OPPORTUNITY" and len(lane_rows(tmp_path, "large_smc")) == 1


# --------------------------------------------------------------------------------------- CCFD

def ccfd_row(decision, **extra):
    return {"strategy_id": "ST_CRYPTO_CFD_SWEEP_RETEST_V1", "strategy_version": "1.0.0", "symbol": "BTCUSD",
            "cycle": "WEEKDAY", "decision": decision, "evaluated_at": NOW.isoformat(),
            "session_date": DAY.isoformat(), "reason_codes": extra.pop("reason_codes", []), **extra}


def test_ccfd_priced_ready_is_a_non_executable_candidate():
    c = ccfd_lane.observe_row(ccfd_row("READY", direction="SHORT", entry=62000.0, stop_loss=62400.0,
                                       tp1=61600.0, tp2=60000.0), now=NOW, policy=SIGNED_POLICY)
    assert c["report_class"] == "CANDIDATE" and c["decision"] != "WATCH_READY"
    # D8 re-recorded the identity, but the registry records no window: never LOGIC_VERIFIED per ticket
    assert (c["scope_verification_status"], c["scope_reason"]) == ("UNVERIFIED", "WINDOW_NOT_IN_SCOPE")


def test_ccfd_direction_outside_the_recorded_branches_is_unverified():
    c = ccfd_lane.observe_row(ccfd_row("READY", direction="LONG", entry=62000.0, stop_loss=61600.0,
                                       tp1=62400.0), now=NOW, policy=SIGNED_POLICY)
    assert (c["scope_verification_status"], c["scope_reason"]) == ("UNVERIFIED", "DIRECTION_NOT_IN_SCOPE")


@pytest.mark.parametrize("decision,cls", [("BLOCKED", "BLOCKED"), ("NO_TRADE", "NO_OPPORTUNITY"),
                                          ("DATA_ERROR", "DATA_ERROR")])
def test_ccfd_row_decisions_are_preserved(decision, cls):
    c = ccfd_lane.observe_row(ccfd_row(decision, reason_codes=["LOGIC_STATUS_NOT_VERIFIED"]), now=NOW,
                              policy=SIGNED_POLICY)
    assert c["report_class"] == cls


def test_ccfd_lane_never_omits_an_instrument(tmp_path):
    out = ccfd_lane.run_ccfd_lane(NOW, feed=None, archive_root=str(tmp_path), policy=SIGNED_POLICY)
    assert sorted(c["instrument"] for c in out) == ["BTCUSD", "ETHUSD"]
    assert all(c["report_class"] in {"BLOCKED", "DATA_ERROR", "OUT_OF_SESSION"} for c in out)
    assert len(lane_rows(tmp_path, "crypto_cfd")) == 2


# ----------------------------------------------------------------------------------- boundaries

FORBIDDEN_MODULES = ("execution", "demo_execution", "mt5", "MetaTrader5", "assistant", "trade_management")


def test_reporting_package_has_no_order_capable_imports_or_calls():
    for path in (ROOT / "src" / "reporting").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any(n.split(".")[0] in FORBIDDEN_MODULES for n in names), (path.name, names)
        for word in ("order_send", "order_check", "management_gateway", "DEMO_ORDER", "user_confirmed"):
            assert word not in text, (path.name, word)


def test_identity_bound_strategy_files_are_unchanged():
    from v1_tickets.authority import logic_identity
    from v1_tickets.lsmc_logic_gate import engine_sha256
    assert logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2")["digest"] == \
        "d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5"
    assert logic_identity("ST_CRYPTO_CFD_SWEEP_RETEST_V1", "1.0.0")["digest"] == \
        "7a0946e41b2e1e79ea5ee8c47df1eb3e99fe94181f29cd36f30eb6ce797dc2a2"
    assert engine_sha256() == "88dd9f1fb970f7811b437cb3b4c7341e0d1f84320238890eab3381eb0f51b689"


def test_runner_lane_wrapper_isolates_failures_and_ccfd_feed_is_passthrough():
    import live_candles_smoke as lcs
    assert lcs.report_lane_lines("X", lambda: (_ for _ in ()).throw(RuntimeError("boom")))[0].startswith(
        "REPORT_LANE X FAILED RuntimeError")
    assert lcs.report_lane_lines("Y", lambda: [{"report_class": "WATCH"}]) == [
        "REPORT_LANE Y observations=1 classes=WATCH"]
    feed = lcs.CcfdFeed(lambda b, tf, n: [b, tf, n], lambda b: (1.0, 2.0, NOW))
    assert feed.fetch("BTCUSD", "M5", 3) == ["BTCUSD", "M5", 3] and feed.quote("BTCUSD") == (1.0, 2.0, NOW)
    assert lcs._bid_ask(lambda b: (1.0, 1.1), "EURUSD-VIP") == (1.0, 1.1)
    assert lcs._bid_ask(lambda b: (_ for _ in ()).throw(OSError()), "EURUSD-VIP") == (None, None)
    assert lcs._bid_ask(None, "EURUSD-VIP") == (None, None)
