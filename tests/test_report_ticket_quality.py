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
    assert c["candidate_signal_id"] is None
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
    assert "SCHEMA_GAP" not in text and "EURUSD n/a (ASIAN_LONDON)" in text
    assert "evaluated: 15:16 MMT / 08:46 UTC (2026-10-13)" in text and "blocked: SUSPENDED_L3_REPAINT" in text
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
    assert text.splitlines()[0] == "LARGE-SMC WATCH -- INFORMATIONAL -- REPORT ONLY -- NOT A BROKER ORDER"


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
