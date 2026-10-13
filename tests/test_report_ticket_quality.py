"""AGP-C18-TICKET-QUALITY-R1: regressions reproduced from the real 2026-10-13 Telegram messages.

12760 (USDJPY ASW LONG): ENTRY 158.182 SL 158.121 TP1 158.524 TP2 158.487 -> TP1 (5.607R) beyond TP2 (5.0R),
prohibited by the frozen v1.1.2 rule FAIL_CLOSED_IF_TP1_BEYOND_TP2, and already INFO_ONLY_STALE.
12750/12758 (EURUSD LSMC): a SHORT setup followed by an independent LONG setup.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest
from test_actionability_and_canonical_ticket import (
    SIGNED_POLICY,
    _build_asian_london_sweep,
)

from reporting import asw_lane, lsmc_lane
from telegram_delivery.adapter import (
    render_lsmc_crypto_summary,
    render_report,
    report_identity,
)
from v1_tickets.daily_evaluator import fixture_candle_provider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
import canonical_fx_delivery as cfd  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 13, 8, 46, tzinfo=UTC)


def candidate(direction, tp1, tp2):
    return {"report_class": "CANDIDATE", "direction": direction, "decision": "INFO_ONLY_SUPPRESSED",
            "reason_codes": [], "candidate_signal_id": "sig",
            "prices": {"entry_reference_raw": 158.182, "sl_raw": 158.121, "tp1_raw": tp1, "tp2_raw": tp2}}


def test_real_12760_inverted_targets_fail_closed_without_relabelling():
    c = asw_lane.enforce_target_order(candidate("LONG", 158.524, 158.487), asw_lane.STRATEGY_PATH)
    assert c["report_class"] == "BLOCKED"
    assert "TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2" in c["reason_codes"]
    assert (c["prices"]["tp1_raw"], c["prices"]["tp2_raw"]) == (158.524, 158.487)   # never swapped
    assert c["candidate_signal_id"] == "sig"                        # kept: one BLOCKED message per signal
    risk = 158.182 - 158.121
    assert round((158.524 - 158.182) / risk, 3) == 5.607 and round((158.487 - 158.182) / risk, 3) == 5.0


@pytest.mark.parametrize("direction,tp1,tp2,cls", [("LONG", 158.40, 158.487, "CANDIDATE"),
                                                   ("SHORT", 157.90, 157.95, "BLOCKED"),
                                                   ("SHORT", 157.95, 157.90, "CANDIDATE")])
def test_target_order_rule_both_directions(direction, tp1, tp2, cls):
    assert asw_lane.enforce_target_order(candidate(direction, tp1, tp2), asw_lane.STRATEGY_PATH)["report_class"] == cls


def test_contract_rule_is_read_from_the_frozen_contract():
    assert asw_lane.contract_target_order_rule(asw_lane.STRATEGY_PATH) == "FAIL_CLOSED_IF_TP1_BEYOND_TP2"


def test_stale_signal_is_a_blocked_diagnostic_not_a_candidate():
    ref, n, post = _build_asian_london_sweep(NOW, age_minutes=76)        # 07:30 signal evaluated at 08:46
    prov = fixture_candle_provider(ref, n, post, spread=0.0001, current_price=1.1636,
                                   data_close=post[-1].time + dt.timedelta(minutes=15))
    c = asw_lane.evaluate_scope("USDJPY", "ASIAN_LONDON", now=NOW, day=NOW.date(), candle_provider=prov,
                                policy=SIGNED_POLICY)
    assert c["report_class"] == "BLOCKED" and "INFO_ONLY_STALE" in c["reason_codes"]


def test_render_has_timestamps_and_no_schema_gap_for_absent_direction():
    blocked = {"scope_route": "REPORT_ONLY", "report_class": "BLOCKED", "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
               "strategy_version": "1.1.2", "instrument": "EURUSD", "session": "ASIAN_LONDON", "direction": None,
               "scope_verification_status": "SUSPENDED", "scope_reason": "L3", "created_at": NOW.isoformat(),
               "reason_codes": ["SUSPENDED_L3_REPAINT"], "trigger": {}}
    text = render_report(blocked)
    assert "SCHEMA_GAP" not in text and "EURUSD-VIP n/a (ASIAN_LONDON)" in text
    assert "evaluated: 15:16 MMT / 08:46 UTC (2026-10-13)" in text and "blocked by: SUSPENDED_L3_REPAINT -- scope suspended" in text
    assert text.isascii()


def lsmc_event(to_state, reference, direction, frm="IDLE"):
    return {"transition_id": f"t-{reference}-{to_state}", "symbol": "EURUSD", "from_state": frm, "to_state": to_state,
            "alert_level": "WATCH", "reference_id": reference, "evaluated_at": NOW.isoformat(),
            "trading_date": NOW.date().isoformat(), "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0",
            "payload": {"poi": {"direction": direction}, "bias": direction}}


def test_lsmc_watch_is_identified_per_setup_and_carries_the_transition():
    short_ref = "EURUSD:H1:FVG:SHORT:2026-10-12T09:00:00+00:00"
    long_ref = "EURUSD:H1:FVG:LONG:2026-10-13T01:00:00+00:00"
    a = lsmc_lane.from_event(lsmc_event("NEAR_POI", short_ref, "SHORT", "OPPORTUNITY"), now=NOW, policy=SIGNED_POLICY)
    b = lsmc_lane.from_event(lsmc_event("DEVELOPING", short_ref, "SHORT", "NEAR_POI"), now=NOW, policy=SIGNED_POLICY)
    c = lsmc_lane.from_event(lsmc_event("DEVELOPING", long_ref, "LONG", "NEAR_POI"), now=NOW, policy=SIGNED_POLICY)
    assert report_identity(a) == report_identity(b)                    # churn on one setup reports once
    assert report_identity(c) != report_identity(a)                    # independent setup reports anew
    assert (a["setup_id"], a["transition"]) == (short_ref, "OPPORTUNITY->NEAR_POI")
    text = render_report(c)
    assert f"ref: {long_ref}" in text and "transition: NEAR_POI->DEVELOPING" in text
    assert text.splitlines()[0] == "REPORT ONLY -- NON-ACTIONABLE"


def test_lsmc_summary_counts_only_rejection_states(tmp_path):
    from test_canonical_fx_delivery import sender
    send, _ = sender(tmp_path, enabled=False)
    for state, reasons in (("DEVELOPING", []), ("NEAR_POI", []), ("REJECTED", ["REJECT_NO_TARGET_X"]),
                           ("DATA_ERROR", ["INCOMPLETE_CANDLES"])):
        cfd.record_lsmc_crypto_evaluation(str(tmp_path), now=NOW, session=cfd.LSMC_CRYPTO_DAY, symbol="BTCUSD",
                                          state=state, reason_codes=reasons)
    summary = cfd.build_lsmc_crypto_summary(str(tmp_path), session_date=NOW.date(), session=cfd.LSMC_CRYPTO_DAY,
                                            window=(NOW.replace(hour=0, minute=0), NOW.replace(hour=23)), sender=send)
    assert "UNSPECIFIED" not in summary["rejection_counts"]
    assert summary["rejection_counts"] == {"INCOMPLETE_CANDLES": 1, "REJECT_NO_TARGET_X": 1}


def test_empty_window_summary_is_labelled_not_a_market_observation(tmp_path):
    from test_canonical_fx_delivery import sender
    send, _ = sender(tmp_path, enabled=False)
    summary = cfd.build_lsmc_crypto_summary(str(tmp_path), session_date=NOW.date(), session=cfd.LSMC_CRYPTO_DAY,
                                            window=(NOW.replace(hour=0), NOW.replace(hour=1)), sender=send)
    assert "not a market observation" in render_lsmc_crypto_summary(summary)


@pytest.mark.parametrize("canonical,broker", [("EURUSD", "EURUSD-VIP"), ("GBPUSD", "GBPUSD-VIP"),
                                              ("USDJPY", "USDJPY-VIP"), ("XAUUSD", "XAUUSD-VIP"),
                                              ("BTCUSD", "BTCUSD"), ("ETHUSD", "ETHUSD")])
def test_reports_show_the_mt5_broker_symbol_for_all_six_instruments(canonical, broker):
    c = {"scope_route": "REPORT_ONLY", "report_class": "WATCH", "strategy_id": "ST_LARGE_SMC_V1",
         "strategy_version": "1.1.0", "instrument": canonical, "direction": "LONG", "reason_code": "LSMC_NEAR_POI",
         "scope_verification_status": "UNVERIFIED", "scope_reason": "ENTRY_LOGIC_NOT_VERIFIED"}
    assert render_report(c).splitlines()[1].startswith(f"{broker} ")


def test_real_xauusd_blocked_report_puts_the_evidence_gap_first_and_badges_in_notes():
    """The 2026-10-13 XAUUSD message listed REJECT_NO_STOP,C10_PIP_SIZE_NOT_EVIDENCED,D30_BADGE_... as blockers."""
    event = lsmc_event("OPPORTUNITY", "XAUUSD:H1:OB:LONG:x", "LONG", "NEAR_POI")
    event["symbol"] = "XAUUSD"
    event["payload"].update(reason_codes=["D30_BADGE_ECONOMICS_NOT_EVALUATED"],
                            opportunity={"direction": "LONG", "entry_reference": 4100.0, "stop_c10": None,
                                         "stop_reason": "C10_PIP_SIZE_NOT_EVIDENCED", "target_c11": 4120.0})
    c = lsmc_lane.from_event(event, now=NOW, price=4105.2, policy=SIGNED_POLICY)
    assert c["reason_codes"] == ["C10_PIP_SIZE_NOT_EVIDENCED", "REJECT_NO_STOP"]
    assert c["notes"] == ["D30_BADGE_ECONOMICS_NOT_EVALUATED"]
    text = render_report(c)
    assert "blocked by: C10_PIP_SIZE_NOT_EVIDENCED -- no verified pip size" in text
    assert "also: REJECT_NO_STOP" in text and "note: D30_BADGE_ECONOMICS_NOT_EVALUATED" in text
    assert text.splitlines()[1].startswith("XAUUSD-VIP OPPORTUNITY (BLOCKED)")


def test_real_eurusd_londonny_short_inverted_and_suspended_is_blocked_once_per_signal():
    """2026-10-13 13:16 UTC: SHORT ENTRY 1.11952 SL 1.11968 TP1 1.11714 (14.9R) TP2 1.11872 (5R), scope SUSPENDED;
    the same signal was BLOCKED SPREAD_TOO_WIDE at 13:01 and then sent as a CANDIDATE."""
    base = {"report_class": "CANDIDATE", "direction": "SHORT", "decision": "INFO_ONLY_SUPPRESSED",
            "reason_codes": [], "scope_verification_status": "SUSPENDED", "ticket_id": "t",
            "candidate_signal_id": "ASW@1.1.2|EURUSD|LONDON_NEWYORK|SHORT|2026-10-13T12:45:00+00:00",
            "prices": {"entry_reference_raw": 1.11952, "sl_raw": 1.11968, "tp1_raw": 1.11714, "tp2_raw": 1.11872}}
    c = asw_lane.finalize_candidate(dict(base, prices=dict(base["prices"])))
    assert c["report_class"] == "BLOCKED" and c["reason_code"] == "TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2"
    valid = asw_lane.finalize_candidate(dict(base, prices={**base["prices"], "tp1_raw": 1.11900, "tp2_raw": 1.11872}))
    assert valid["report_class"] == "BLOCKED" and valid["reason_code"] == "SCOPE_SUSPENDED"
    earlier = dict(base, report_class="BLOCKED", reason_code="SPREAD_TOO_WIDE", reason_codes=["SPREAD_TOO_WIDE"])
    assert report_identity(earlier) == report_identity(c)                  # same signal -> one BLOCKED message
    assert "blocked by: SPREAD_TOO_WIDE -- live spread above 15%" in render_report(
        dict(earlier, scope_route="REPORT_ONLY", instrument="EURUSD", session="LONDON_NEWYORK"))


def test_session_summary_scope_lines_are_ascii_and_hide_evidence_paths():
    from telegram_delivery.adapter import scope_status_lines
    lines = scope_status_lines([
        {"symbol": "EURUSD", "verification_status": "SUSPENDED", "route": "REPORT_ONLY",
         "route_reason": "L3_REPAINT_UNRESOLVED_2026-07-31", "detail": "docs/status/AGP_C3_ASW_V112_R2_60D_2026-10-10.md"},
        {"symbol": "GBPUSD", "verification_status": "LOGIC_VERIFIED", "route": "REPORT_ONLY",
         "route_reason": "DEMO_AUTHORIZATION_ABSENT", "detail": "branch=RANGE_SWEEP"}])
    assert lines[0] == "REPORT ONLY -- NON-ACTIONABLE" and all(line.isascii() for line in lines)
    assert lines[2] == "- EURUSD: SUSPENDED | REPORT_ONLY (L3_REPAINT_UNRESOLVED_2026-07-31)"
    assert lines[3].endswith("[branch=RANGE_SWEEP]")
