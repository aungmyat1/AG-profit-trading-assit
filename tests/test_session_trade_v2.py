from datetime import date, datetime, timezone

from session_trade_v2 import Candle, build_ticket, evaluate

UTC = timezone.utc

def c(h, o, hi, lo, cl):
    return Candle(datetime(2026, 10, 1, h, 0, tzinfo=UTC), o, hi, lo, cl)

REF = [c(22, 1.1000, 1.1010, 1.0990, 1.1000), c(23, 1.1000, 1.1020, 1.0980, 1.1005)]


def test_a_sweep_long_has_priority_and_protects_extreme():
    d = evaluate("EURUSD", "ASIAN_LONDON", REF, [c(6, 1.0985, 1.0990, 1.0975, 1.0982)])
    assert d.status == "SIGNAL"
    assert d.setup == "A_SWEEP_REENTRY"
    assert d.direction == "LONG"
    assert d.entry_order_type == "MARKET"
    assert d.stop_loss < 1.0975
    assert round((d.target_5r - d.entry) / d.risk_distance, 8) == 5.0


def test_dual_side_sweep_fails_closed():
    d = evaluate("GBPUSD", "ASIAN_LONDON", REF, [c(6, 1.1000, 1.1030, 1.0970, 1.1000)])
    assert d.status == "NO_TRADE"
    assert d.reason_code == "AMBIGUOUS_DUAL_SIDE_SWEEP"


def test_b_range_rejection_uses_boundary_limit_and_quarter_range_stop():
    d = evaluate("USDJPY", "LONDON_NEWYORK", REF, [c(11, 1.0995, 1.1005, 1.0980, 1.1002)])
    assert d.setup == "B_RANGE_REJECTION"
    assert d.direction == "LONG"
    assert d.entry_order_type == "LIMIT"
    assert d.entry == 1.0980
    assert round(d.risk_distance, 6) == 0.001


def test_c_trend_expansion_uses_equilibrium_retrace():
    d = evaluate("XAUUSD", "LONDON_NEWYORK", REF, [c(11, 1.1030, 1.1040, 1.1025, 1.1035)])
    assert d.setup == "C_TREND_EXPANSION"
    assert d.direction == "LONG"
    assert d.entry_order_type == "LIMIT"
    assert d.entry == 1.1000
    assert "trail" in d.management.lower()


def test_ticket_is_explicitly_non_executable():
    t = build_ticket("EURUSD", "ASIAN_LONDON", date(2026, 10, 1), REF,
                     [c(6, 1.0985, 1.0990, 1.0975, 1.0982)])
    assert t["decision"] == "READY"
    assert t["demo_authorized"] is False
    assert t["live_authorized"] is False
    assert t["allow_order_send"] is False
    assert t["position_size"] == "NOT_CALCULATED_RESEARCH_SHADOW"


def test_supported_matrix():
    for symbol in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"):
        for cycle in ("ASIAN_LONDON", "LONDON_NEWYORK"):
            d = evaluate(symbol, cycle, REF, [c(6, 1.1000, 1.1010, 1.0990, 1.1000)])
            assert d.status == "NO_TRADE"
