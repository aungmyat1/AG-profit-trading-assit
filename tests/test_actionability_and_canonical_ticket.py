"""Phase D/E/G/K tests: actionability, canonical ticket, structure visual, daily evaluator."""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import actionability as A  # noqa: E402
from v1_tickets import crypto as v1_crypto  # noqa: E402
from v1_tickets import fx as v1_fx  # noqa: E402
from v1_tickets.canonical_ticket import (  # noqa: E402
    build_canonical_ticket, render_canonical, render_structure_visual,
)
from v1_tickets.daily_evaluator import (  # noqa: E402
    FX_PAIRS, evaluate_fx_pair, fixture_candle_provider, run_daily_evaluation,
)

UTC = dt.timezone.utc


def _c(ts_iso: str, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(time=dt.datetime.fromisoformat(ts_iso).replace(tzinfo=UTC),
                  open=o, high=h, low=l, close=c, volume=0)


def _build_asian_london_sweep(now: dt.datetime, *, long: bool = True,
                              age_minutes: int = 5,
                              spread: float = 0.0001,
                              current_offset: float = 0.0002,
                              entry: float = 1.1634, sl: float = 1.1614):
    """Build a deterministic set of ref + post candles that produces a SWEEP signal for
    EURUSD on ASIAN_LONDON using the frozen ST_ASIAN_SWEEP_5R_V1 engine.

    We hand-craft a simple reference box and a post-session sweep candle.
    """
    day = now.date()
    # Build 24 M15 reference bars (00:00-06:00 UTC) forming a simple range box.
    box_hi, box_lo = 1.1650, 1.1600
    ref_start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=UTC)
    ref = []
    for i in range(24):
        t = ref_start + dt.timedelta(minutes=15 * i)
        # First bar sets high/low; subsequent bars stay inside.
        if i == 0:
            o, h, l, c = box_lo + 0.0020, box_hi, box_lo, box_lo + 0.0010
        elif i == 23:
            o, h, l, c = box_lo + 0.0020, box_lo + 0.0025, box_lo + 0.0010, box_lo + 0.0020
        else:
            mid = (box_hi + box_lo) / 2
            o = h = l = c = mid
        ref.append(_c(t.isoformat(), o, h, l, c))
    # Post-session candles starting at 07:00 UTC (trade window).
    post_start = dt.datetime.combine(day, dt.time(7, 0), tzinfo=UTC)
    post = []
    # Sweep bar at post_start + N bars such that signal_close = now - age_minutes.
    # The engine finds a sweep when a post bar wicks beyond the reference box and closes inside.
    sweep_time = now - dt.timedelta(minutes=age_minutes)
    # ensure sweep_time aligns to M15 boundary.
    sweep_time = sweep_time.replace(minute=(sweep_time.minute // 15) * 15, second=0, microsecond=0)
    # Bars between post_start and sweep_time: inside the range (no setup).
    t = post_start
    i = 0
    while t < sweep_time:
        mid = (box_hi + box_lo) / 2
        post.append(_c(t.isoformat(), mid, mid + 0.0002, mid - 0.0002, mid))
        t += dt.timedelta(minutes=15)
        i += 1
        if i > 40:
            break
    # Sweep candle wicks beyond the reference box and closes back inside.
    if long:
        sweep = _c(sweep_time.isoformat(),
                   o=box_lo + 0.0003, h=box_lo + 0.0005, l=box_lo - 0.0008, c=entry)
    else:
        sweep = _c(sweep_time.isoformat(),
                   o=box_hi - 0.0003, h=box_hi + 0.0008, l=box_hi - 0.0005, c=entry)
    post.append(sweep)
    # Ensure the data_close matches the last post bar's close time.
    return ref, 24, post


# ---------------------------------------------------------------- actionability unit tests

def test_fresh_actionable_signal_is_watch_ready():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # Current price slightly in favor, still has plenty of R to TP1.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636)
    assert canon["decision"] == A.WATCH_READY
    assert canon["freshness"]["status"] == "PASS"
    assert canon["execution_authorization"] is False
    assert "WATCH_READY" in canon["structure_visual"] or "TP2" in canon["structure_visual"]
    text = render_canonical(canon)
    assert "WATCH_READY" in text
    assert "NOT AUTHORIZED" in text
    assert "Economic edge" in text


def test_stale_valid_signal_is_info_only_stale():
    now = dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=60)  # well past 30-min window
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636)
    assert canon["decision"] == A.INFO_ONLY_STALE
    assert canon["actionability"]["valid_at_trigger"] is True
    text = render_canonical(canon)
    assert "INFO_ONLY_STALE" in text
    assert "valid at trigger" in text


def test_insufficient_remaining_r():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5, entry=1.1634, sl=1.1614)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # Price already near TP1 (box high = 1.1650), leaving <1R remaining to TP1.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1648)
    assert canon["decision"] == A.INFO_ONLY_INSUFFICIENT_REMAINING_R
    assert canon["presentation"] == "INFO_ONLY"


def test_expired_opportunity_past_window_end():
    # Trade window ends at 11:00 GMT; evaluate at 15:30 GMT.
    now = dt.datetime(2026, 10, 7, 15, 30, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    # Adjust candles to sit at correct dates — this is synthetic; we just test the gate
    # by building a ticket and overriding the window via canonical: just confirm
    # actionability EXPIRED when now >= window_end_utc of the canonical trade window.
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # Force window_end in the past
    win_end = dt.datetime(2026, 10, 7, 11, 0, tzinfo=UTC)
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, window_end=win_end)
    assert canon["decision"] == A.EXPIRED


def test_no_trade_when_engine_says_no_setup():
    # Before reference window closes -> REFERENCE_NOT_READY -> OUT_OF_SESSION is NOT no-trade.
    # Build an explicit DATA_ERROR/NO_TRADE by passing a NO_TRADE ticket reason.
    now = dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    day = now.date()
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    # Use an already-built ticket and mutate decision to NO_TRADE to isolate actionability.
    ticket = dict(v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", day, ref, n, post, data_source="TEST",
        evaluated_at=now, data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    ))
    ticket["decision"] = "NO_TRADE"
    ticket["reason_code"] = "NO_SETUP_BY_WINDOW_END"
    ticket["direction"] = None
    ticket.pop("entry", None)
    ticket.pop("stop_loss", None)
    ticket.pop("targets", None)
    win_end = dt.datetime.combine(day, dt.time(11, 0), tzinfo=UTC)
    canon = build_canonical_ticket(ticket, now=now, current_price=None, window_end=win_end)
    assert canon["decision"] == A.NO_TRADE


def test_missing_data_yields_insufficient_data_or_blocked():
    now = dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC)
    err = v1_fx.build_fx_error_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), evaluated_at=now, reason_code="NO_CANDLES",
        decision="DATA_ERROR",
    )
    canon = build_canonical_ticket(err, now=now)
    assert canon["decision"] == A.INSUFFICIENT_DATA


def test_unsupported_crypto_venue_identity_not_silently_mixed(tmp_path):
    """BTCUSD CFDs must stay distinct from BTCUSDT perps — the canonical ticket reports
    venue explicitly."""
    from v1_tickets.daily_evaluator import evaluate_crypto_symbol

    def _no_feed(symbol, *, now, cfg):
        return None  # no feed -> deterministic BLOCKED with venue=NONE

    res = evaluate_crypto_symbol("BTCUSDT", now=dt.datetime(2026, 10, 7, 6, 40, tzinfo=UTC),
                                 day=dt.date(2026, 10, 7), feed_provider=_no_feed,
                                 state_dir=str(tmp_path / "state"), archive_root=str(tmp_path),
                                 config_path=None)
    assert res.instrument == "BTCUSDT"
    assert res.venue == "NONE"
    assert "BTCUSDT" in res.ticket_id
    # Ensure the venue/identity string is in the archive payload
    assert res.canonical["instrument"] == "BTCUSDT"
    # BTCUSDT perp identity must never be confused with BTCUSD CFDs
    assert res.canonical["venue"] != "BTCUSD" and res.canonical["venue"] != "BTCUSD-CFD"


def test_no_silent_session_covers_all_pairs(tmp_path):
    """run_daily_evaluation must return one result per configured pair."""
    now = dt.datetime(2026, 10, 7, 7, 30, tzinfo=UTC)
    results = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=True)
    expected = len(FX_PAIRS) + len(v1_crypto.V1_CRYPTO_SYMBOLS)
    assert len(results) == expected
    pairs_seen = {(r.instrument, r.session) for r in results}
    for sym, cyc in FX_PAIRS:
        assert (sym, cyc) in pairs_seen
    for sym in v1_crypto.V1_CRYPTO_SYMBOLS:
        assert (sym, v1_crypto.CYCLE) in pairs_seen
    # Every result is archived
    for r in results:
        assert os.path.exists(r.archive_path)
        assert r.decision in {A.WATCH_READY, A.INFO_ONLY_STALE, A.INFO_ONLY_INSUFFICIENT_REMAINING_R,
                              A.NO_TRADE, A.EXPIRED, A.MISSED, A.BLOCKED, A.INSUFFICIENT_DATA,
                              A.OUT_OF_SESSION}


def test_duplicate_delivery_restart_dedup(tmp_path):
    """Running twice must not change the logical ticket_id for the same (strategy, version,
    symbol, cycle, day) — this is required for delivery dedup."""
    now = dt.datetime(2026, 10, 7, 7, 30, tzinfo=UTC)
    r1 = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=False)
    r2 = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=False)
    ids1 = sorted(r.ticket_id for r in r1)
    ids2 = sorted(r.ticket_id for r in r2)
    assert ids1 == ids2


def test_structure_visual_contains_required_levels():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636)
    viz = canon["structure_visual"]
    # All required elements present.
    assert "TP2" in viz
    assert "TP1" in viz
    assert "NOW" in viz or "ENTRY" in viz
    assert "POI" in viz
    assert "SL" in viz
    # Dotted path is not a certainty claim
    assert "estimated path" in viz
    assert "not a forecast" in viz


def test_execution_authority_never_true():
    """Every canonical ticket carries execution_authorization = False regardless of state."""
    now = dt.datetime(2026, 10, 7, 7, 30, tzinfo=UTC)
    results = run_daily_evaluation(now=now, archive_root=os.path.join(os.path.dirname(__file__), "_tmp"),
                                   include_crypto=False)
    for r in results:
        assert r.canonical["execution_authorization"] is False
        assert r.canonical["demo_authorized"] is False
        assert r.canonical["live_authorized"] is False


def test_logic_status_not_invented():
    """A strategy with logic_status: NOT_VERIFIED in the registry must surface that exactly."""
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636)
    # ST_ASIAN_SWEEP_5R_V1 is NOT_VERIFIED per registry.yaml (no matching logic_verified_identity)
    assert canon["logic_status"] == "NOT_VERIFIED"
    assert canon["economic_status"] == "NOT_EVALUATED"
    assert canon["economic_edge"] == "NOT VERIFIED"


if __name__ == "__main__":
    import pytest as _p
    sys.exit(_p.main([__file__, "-v"]))
