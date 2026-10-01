"""Rendered Telegram message content (formatting only -- no rule changes)."""
from __future__ import annotations

from host_delivery import telegram_message as tg
from ticket_delivery.identity import logical_ticket_id
import datetime as dt

FX_READY = {  # shape of the 2026-10-01 07:16 UTC USDJPY READY ticket
    "label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER", "strategy_id": "ST_ASIAN_SWEEP_5R_V1",
    "strategy_version": "1.1.1", "symbol": "USDJPY", "cycle": "ASIAN_LONDON", "session_date": "2026-10-01",
    "data_source": "MT5_VT_MARKETS_DEMO", "decision": "READY", "direction": "LONG", "entry": 157.971,
    "stop_loss": 157.551, "risk_distance": 0.42, "time_invalidation_gmt": "15:00",
    "targets": [{"leg": 1, "volume_pct": 0.75, "type": "OPPOSITE_SESSION_BOUNDARY", "price": 158.181},
                {"leg": 2, "volume_pct": 0.25, "type": "FIXED_R_MULTIPLE_5", "price": 160.071}],
    "signal_close_utc": "2026-10-01T07:15:00+00:00", "spread_check": "PASS", "spread": 0.017,
    "spread_risk_fraction": 0.0405, "spread_max_risk_fraction": 0.15,
}


def test_fx_ticket_message_has_id_times_risk_r_spread_and_validity():
    lines = tg.format_ticket(FX_READY).splitlines()
    tid = logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="USDJPY",
                            cycle="ASIAN_LONDON", trading_date=dt.date(2026, 10, 1))
    assert lines[0] == "INFORMATIONAL TICKET -- NOT A BROKER ORDER"
    for expected in (
        f"ticket_id: {tid}",
        "window: ASIAN_LONDON trade session  time invalidation 15:00 GMT",
        "signal close: 13:45 MMT / 07:15 UTC (2026-10-01)",
        "expires_at: 14:00 MMT / 07:30 UTC (2026-10-01)",          # signal close + guards.STALE_AFTER
        "entry: 157.971  stop: 157.551  risk: 42.0 pips",
        "target leg 1 (OPPOSITE_SESSION_BOUNDARY, 75%): 158.181  = +0.50R",
        "target leg 2 (FIXED_R_MULTIPLE_5, 25%): 160.071  = +5.00R",
        "spread_check: PASS  spread 1.7 pips = 4.0% of risk (max 15%)",
        "VALID UNTIL 14:00 MMT / 07:30 UTC (2026-10-01) -- STALE after; re-check before acting.",
    ):
        assert expected in lines, expected


def test_short_ticket_r_is_positive_toward_target_and_missing_signal_close_is_explicit():
    t = {**FX_READY, "symbol": "EURUSD", "direction": "SHORT", "entry": 1.1310, "stop_loss": 1.1320,
         "risk_distance": 0.0010, "targets": [{"leg": 1, "type": "X", "price": 1.1290}],
         "signal_close_utc": None, "spread": None}
    msg = tg.format_ticket(t)
    assert "risk: 10.0 pips" in msg and "target leg 1 (X): 1.129  = +2.00R" in msg
    assert "expires_at: n/a" in msg and "VALID UNTIL: n/a (signal close not recorded)" in msg
    assert "spread_check: PASS\n" in msg                                 # no spread value -> no invented %


def test_crypto_ticket_uses_price_units_and_tp_r_multiples():
    t = {"label": "INFORMATIONAL TICKET -- NOT A BROKER ORDER", "strategy_id": "ST_LIQUIDITY_SWEEP_RETEST_V1",
         "strategy_version": "1.0.0", "symbol": "BTCUSD", "cycle": "DAILY", "observation_date": "2026-10-01",
         "decision": "READY", "direction": "LONG", "entry": 60000.0, "stop_loss": 59800.0, "tp1": 60400.0,
         "tp2": 61000.0, "window": "WEEKDAY", "ticket_status": "SHADOW", "data_source": "MT5"}
    msg = tg.format_ticket(t)
    assert "window: WEEKDAY  status: SHADOW" in msg and "risk: 200 (price units)" in msg
    assert "tp1: 60400.0  = +2.00R" in msg and "tp2: 61000.0  = +5.00R" in msg
    assert "ticket_id: n/a" not in msg


def _lsmc_event():
    return {"symbol": "EURUSD", "to_state": "OPPORTUNITY", "alert_level": "OPPORTUNITY",
            "strategy_id": "ST_LARGE_SMC_V1", "strategy_version": "1.1.0", "reference_id": "opp-1",
            "payload": {"bias": "LONG",
                        "poi": {"kind": "FVG", "direction": "LONG", "low": 1.1300, "high": 1.1310},
                        "opportunity": {"direction": "LONG", "sweep_extreme": 1.1295, "target_c11": 1.1360,
                                        "stop_c10": 1.1292, "entry_reference": 1.1318,
                                        "expires_at": "2026-10-01T16:00:00+00:00"}}}


def test_lsmc_alert_message_has_direction_poi_invalidation_target_price_distance_chain_expiry():
    lines = tg.format_alert(_lsmc_event(), price=1.1330).splitlines()
    assert lines[0] == "LARGE-SMC ALERT -- INFORMATIONAL -- NOT A BROKER ORDER"
    for expected in (
        "EURUSD OPPORTUNITY (OPPORTUNITY)  direction: LONG",
        "timeframes: D1 context -> H1 bias + POI -> M5 sweep/CHoCH",
        "POI zone (FVG): 1.13 - 1.131",
        "invalidation: M5 close below 1.1295",
        "liquidity target: 1.136",
        "current price: 1.133",
        "distance to POI: 20.0 pips",
        "expires_at: 22:30 MMT / 16:00 UTC (2026-10-01)",
    ):
        assert expected in lines, expected


def test_lsmc_alert_inside_zone_and_without_price_or_target():
    e = _lsmc_event()
    e["payload"]["opportunity"]["target_c11"], e["payload"]["opportunity"]["target_reason"] = None, "REJECT_NO_TARGET"
    assert "distance to POI: inside zone" in tg.format_alert(e, price=1.1305)
    msg = tg.format_alert(e)
    assert "current price" not in msg and "liquidity target: none (REJECT_NO_TARGET)" in msg
