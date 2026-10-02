from datetime import datetime, timezone
from pathlib import Path

import pytest

from session_scanner.message_models import MessageType
from session_scanner.message_router import route_message
from session_scanner.telegram_formatter import format_expiry, format_telegram

NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)


def route(**values):
    values.setdefault("timestamp_utc", "2026-10-01T14:00:00Z")
    return route_message(values, now_utc=NOW)


def test_ready_for_proposal_routes_to_ticket_but_never_execution():
    msg = route(result="READY_FOR_PROPOSAL", proposal_eligible=True, execution_authorized=True)
    assert msg.message_type is MessageType.INFORMATIONAL_TICKET
    assert msg.proposal_eligible is True and msg.execution_authorized is False


def test_ready_risk_ambiguous_is_informational_governance_block():
    msg = route(strategy_decision="READY", setup_valid=True, risk_status="RISK_POLICY_AMBIGUOUS",
                proposal_eligible=False)
    assert msg.message_type is MessageType.INFORMATIONAL_TICKET
    assert msg.governance_block == "RISK_POLICY_AMBIGUOUS"


@pytest.mark.parametrize("symbol,asset", [("XAUUSD", "METAL"), ("ETHUSDT", "CRYPTO")])
def test_large_smc_opportunities(symbol, asset):
    msg = route(canonical_symbol=symbol, asset_class=asset, strategy_id="ST_LARGE_SMC_V1",
                opportunity_detected=True, economic_status="NOT_EVALUATED", proposal_eligible=False)
    assert msg.message_type is MessageType.OPPORTUNITY_ALERT
    assert msg.asset_class == asset and msg.economic_status == "NOT_EVALUATED"
    assert "NOT_EVALUATED" in format_telegram(msg)


def test_no_trade_and_out_of_session_are_summaries():
    for result in ("NO_TRADE", "OUT_OF_SESSION"):
        assert route(result=result).message_type is MessageType.NO_TRADE_SUMMARY


@pytest.mark.parametrize("result", ["BLOCKED", "INSUFFICIENT_DATA", "DATA_INVALID"])
def test_blocked_results_are_alerts(result):
    assert route(result=result).message_type is MessageType.BLOCKED_ALERT


def test_system_event_is_separate_and_strips_trade_fields():
    msg = route(system_event="Telegram test PASS", direction="LONG", entry_price=1.2)
    text = format_telegram(msg)
    assert msg.message_type is MessageType.SYSTEM_STATUS
    assert text == "AG SYSTEM STATUS\n\nTelegram test PASS"
    assert "LONG" not in text and "1.2" not in text


def test_formatter_cannot_upgrade_false_eligibility():
    text = format_telegram(route(strategy_decision="READY", proposal_eligible=False))
    assert "Proposal Eligible:\nNO" in text
    assert "Execution Authorized:\nNO" in text
    assert "Proposal Eligible:\nYES" not in text


def test_expired_opportunity_is_not_rendered_current():
    msg = route(opportunity_detected=True, proposal_eligible=False,
                expires_at_utc="2026-10-01T13:59:59Z")
    text = format_telegram(msg)
    assert msg.expired is True
    assert "EXPIRED — NO LONGER CURRENT" in text
    assert "Expires:" not in text


def test_reason_codes_are_preserved():
    reasons = ["SIGNAL_ENTRY_WINDOW_PASSED", "PROPOSAL_NOT_AUTHORIZED"]
    msg = route(result="NO_TRADE", reason_codes=reasons)
    assert msg.reason_codes == tuple(reasons)
    assert ", ".join(reasons) in format_telegram(msg)


def test_usdjpy_informational_fixture():
    msg = route(canonical_symbol="USDJPY", direction="LONG", session="ASIAN_LONDON",
                strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="v1.1.1",
                strategy_decision="READY", entry_price=157.971, stop_loss=157.551,
                targets=({"price": 158.392, "reason": "OPPOSITE_SESSION_BOUNDARY"},
                         {"price": 160.074, "reason": "FIXED_R_MULTIPLE_5"}),
                setup_valid=True, risk_status="RISK_POLICY_AMBIGUOUS", proposal_eligible=False,
                data_source="MT5_VT_MARKETS_DEMO")
    text = format_telegram(msg)
    for expected in ("USDJPY LONG", "157.971", "157.551", "158.392",
                     "RISK_POLICY_AMBIGUOUS", "Setup Valid:\nYES", "NOT A BROKER ORDER"):
        assert expected in text


def test_xauusd_opportunity_fixture():
    text = format_telegram(route(canonical_symbol="XAUUSD", direction="LONG",
        strategy_id="ST_LARGE_SMC_V1", strategy_version="v1.1.0",
        opportunity_detected=True, economic_status="NOT_EVALUATED", context="H1 FVG LONG"))
    assert "AG LARGE-SMC OPPORTUNITY" in text and "H1 FVG LONG" in text


def test_eth_crypto_opportunity_fixture_and_timezone():
    msg = route(canonical_symbol="ETHUSDT", direction="SHORT", asset_class="CRYPTO",
        strategy_id="ST_LARGE_SMC_V1", strategy_version="v1.1.0", opportunity_detected=True,
        economic_status="NOT_EVALUATED", context="D1 Context\n→ H1 Bias + POI\n→ M5 Sweep / CHoCH",
        poi={"type": "OB_PIVOT", "zone": "2704.02 – 2718.87"}, entry_reference=2698.27,
        invalidation="M5 close above 2710.26", current_price=2698.27, distance_to_poi=5.75,
        expires_at_utc="2026-10-01T15:00:00Z")
    text = format_telegram(msg)
    for expected in ("ETHUSDT SHORT", "OB_PIVOT", "2698.27", "15:00 UTC", "21:30 MMT"):
        assert expected in text


def test_utc_mmt_format_does_not_mutate_datetime():
    dt = datetime(2026, 10, 1, 15, tzinfo=timezone.utc)
    assert format_expiry(dt) == "15:00 UTC\n21:30 MMT"
    assert dt == datetime(2026, 10, 1, 15, tzinfo=timezone.utc)


def test_checklist_v11_nested_proposal_is_consumed_additively():
    upstream = {"symbol": "USDJPY", "result": "READY_FOR_PROPOSAL", "setup_valid": True,
                "proposal_eligible": True, "execution_authorized": False,
                "proposal": {"direction": "LONG", "entry_price": 157.971,
                             "take_profit_1": 158.392, "take_profit_2": 160.074,
                             "position_size_note": "RISK_POLICY_AMBIGUOUS"}}
    msg = route_message(upstream, now_utc=NOW)
    assert (msg.canonical_symbol, msg.direction, msg.entry_price) == ("USDJPY", "LONG", 157.971)
    assert msg.targets == (158.392, 160.074)


def test_router_formatter_have_no_mutation_api_references():
    forbidden = ("trade_send_market_order", "trade_send_pending_order", "trade_modify_sl_tp",
                 "trade_delete_order", "trade_close_single_position", "trade_close_by_position",
                 "MetaTrader5", "order_send")
    root = Path(__file__).parents[1] / "src" / "session_scanner"
    content = "\n".join((root / name).read_text() for name in
                         ("message_models.py", "message_router.py", "telegram_formatter.py"))
    assert not any(name in content for name in forbidden)
