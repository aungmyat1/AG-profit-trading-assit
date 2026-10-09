from __future__ import annotations

import pytest

from v1_tickets.manual_ticket import render_market_structure, render_mobile


def ticket(direction="LONG"):
    levels = ({"entry": 1.085, "sl": 1.083, "tp1": 1.089, "tp2": 1.095}
              if direction == "LONG" else
              {"entry": 1.085, "sl": 1.087, "tp1": 1.081, "tp2": 1.075})
    return {
        "ticket_id": "T-1", "strategy": "TEST@1", "session": "ASIAN_LONDON",
        "state": "TICKET_READY", "primary_block_reason": None, "block_reasons": [], "warnings": [],
        "logic_gate": {"L5": {"status": "PASS", "checks": [
            {"id": "L5.commission_R", "value": None, "note": "COMMISSION NOT AVAILABLE"}
        ]}}, "logic_status": "LOGIC_VERIFIED", "economic_status": "NOT_EVALUATED",
        "edge_status": "NOT VERIFIED — logic only", "authority": "MANUAL — no automatic order",
        "symbol": "EURUSD", "direction": direction, "setup": "Sweep -> Reclaim -> Confirm",
        "regime": "RANGE", "box": {}, "signal_timestamp": "2026-10-07T07:15:00+00:00",
        "branch": "SWEEP", "order_type": "MARKET", "rr_tp1": 2.0, "rr_tp2": 5.0,
        "stop_distance": 0.002, "lot_size": 0.1, "risk": {"risk_pct": 0.5, "symbol_meta": {}},
        "risk_status": "PASS", "cost_in_R": 0.1, "cost_warn_R": 0.2,
        "valid_until": "2026-10-07T07:30:00+00:00",
        "stale_if": {"rule": "market moved beyond entry"},
        "invalid_if": {"sl_touched_before_fill": levels["sl"], "time_invalidation_utc": "2026-10-07T15:00:00+00:00"},
        **levels,
    }


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_market_structure_uses_ticket_levels_and_labels_scenario(direction):
    text = render_market_structure(ticket(direction))
    assert "MARKET STRUCTURE SCENARIO" in text
    assert "NOT A PRICE FORECAST" in text
    assert "BROKER ORDER: NONE" in text
    assert "EXECUTION AUTHORIZED = FALSE" in text
    for key in ("entry", "sl", "tp1", "tp2"):
        assert str(ticket(direction)[key]) in text


def test_market_structure_has_ascii_fallback_and_fails_closed():
    text = render_market_structure(ticket(), unicode_safe=False)
    assert "---------" in text and "—" not in text and "▲" not in text
    assert render_market_structure({"direction": "LONG"}).startswith("MARKET STRUCTURE UNAVAILABLE")
    bad = ticket()
    bad["tp1"], bad["tp2"] = bad["tp2"], bad["tp1"]
    assert "invalid level geometry" in render_market_structure(bad)


def test_owner_layout_selection_is_explicit():
    assert "MARKET STRUCTURE SCENARIO" not in render_mobile(ticket(), layout="COMPACT")
    assert "MARKET STRUCTURE SCENARIO" in render_mobile(ticket(), layout="EXPANDED")
    with pytest.raises(ValueError):
        render_mobile(ticket(), layout="UNKNOWN")
