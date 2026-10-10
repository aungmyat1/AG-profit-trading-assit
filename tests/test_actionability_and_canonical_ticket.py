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
    NOT_AVAILABLE, build_canonical_ticket, render_canonical, render_structure_visual,
)
from v1_tickets.daily_evaluator import (  # noqa: E402
    FX_PAIRS, evaluate_fx_pair, fixture_candle_provider, run_daily_evaluation,
)
from v1_tickets.policy_loader import POLICY_ID, ActionabilityPolicy, POLICY_OK  # noqa: E402


# ---- fixture policies (DI; tests never rely on production-signed file) --------

SIGNED_POLICY = ActionabilityPolicy(
    status=POLICY_OK, policy_id=POLICY_ID, version=1, min_remaining_r=1.0,
    signed_by="test-fixture", signed_at="2026-10-07", source_path="<fixture>", reason=None,
)

MALFORMED_POLICY_DICT = {"policy_id": POLICY_ID, "version": 1, "min_remaining_r": "not-a-number"}

CONFLICT_POLICY_DICT = {"policy_id": "WRONG_ID", "version": 1, "min_remaining_r": 1.0,
                        "signed_by": "x", "signed_at": "2026-10-07"}

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

def test_fresh_actionable_signal_is_watch_ready(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # Current price slightly in favor, still has plenty of R to TP1.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.WATCH_READY
    assert canon["freshness"]["status"] == "PASS"
    assert canon["execution_authorization"] is False
    assert "WATCH_READY" in canon["structure_visual"] or "TP2" in canon["structure_visual"]
    text = render_canonical(canon)
    assert "WATCH_READY" in text
    assert "NOT AUTHORIZED" in text
    assert "Economic edge" in text
    assert canon["actionability"]["policy_status"] == "POLICY_OK"
    assert canon["actionability"]["min_remaining_r"] == 1.0


def test_stale_valid_signal_is_info_only_stale():
    now = dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=60)  # well past 30-min window
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["decision"] == A.INFO_ONLY_STALE
    assert canon["actionability"]["valid_at_trigger"] is True
    text = render_canonical(canon)
    assert "INFO_ONLY_STALE" in text
    assert "valid at trigger" in text


def test_insufficient_remaining_r(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5, entry=1.1634, sl=1.1614)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # Price already near TP1 (box high = 1.1650), leaving <1R remaining to TP1.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1648, policy=SIGNED_POLICY)
    assert canon["decision"] == A.INFO_ONLY_INSUFFICIENT_REMAINING_R
    assert canon["presentation"] == "INFO_ONLY"


def test_missing_policy_is_never_watch_ready(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    # No policy override provided; the repo default is unsigned -> POLICY_MISSING.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636,
                                   policy_root="/nonexistent")
    assert canon["decision"] == A.INFO_ONLY_POLICY_UNRESOLVED
    assert canon["actionability"]["policy_status"] in {"ACTIONABILITY_POLICY_MISSING",
                                                      "ACTIONABILITY_POLICY_INVALID",
                                                      "ACTIONABILITY_POLICY_CONFLICT"}
    assert canon["actionability"]["reason"] == "ACTIONABILITY_POLICY_MISSING" or \
        canon["actionability"]["reason"].startswith("ACTIONABILITY_POLICY_")


def test_malformed_policy_never_watch_ready(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636,
                                   policy_override_dict=MALFORMED_POLICY_DICT)
    assert canon["decision"] == A.INFO_ONLY_POLICY_UNRESOLVED
    assert canon["actionability"]["policy_status"] == "ACTIONABILITY_POLICY_INVALID"


def test_conflicting_policy_never_watch_ready(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636,
                                   policy_override_dict=CONFLICT_POLICY_DICT)
    assert canon["decision"] == A.INFO_ONLY_POLICY_UNRESOLVED
    assert canon["actionability"]["policy_status"] == "ACTIONABILITY_POLICY_CONFLICT"


def test_expired_opportunity_past_window_end(stub_symbol_verified):
    # Trade window ends at 11:00 GMT; evaluate at 15:30 GMT.
    now = dt.datetime(2026, 10, 7, 15, 30, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15),
        spread=0.0001,
    )
    win_end = dt.datetime(2026, 10, 7, 11, 0, tzinfo=UTC)
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636,
                                   window_end=win_end, policy=SIGNED_POLICY)
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
    """run_daily_evaluation must return one result per configured instrument-session."""
    now = dt.datetime(2026, 10, 7, 7, 30, tzinfo=UTC)
    # Passing policy=None with a nonexistent policy_root simulates unsigned repo default.
    results = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=True,
                                   policy_root=str(tmp_path))
    expected = len(FX_PAIRS) + len(v1_crypto.V1_CRYPTO_SYMBOLS)
    assert len(results) == expected
    pairs_seen = {(r.instrument, r.session) for r in results}
    for sym, cyc in FX_PAIRS:
        assert (sym, cyc) in pairs_seen
    for sym in v1_crypto.V1_CRYPTO_SYMBOLS:
        assert (sym, v1_crypto.CYCLE) in pairs_seen
    for r in results:
        assert os.path.exists(r.archive_path)
        allowed = {A.WATCH_READY, A.INFO_ONLY_STALE, A.INFO_ONLY_INSUFFICIENT_REMAINING_R,
                   A.INFO_ONLY_POLICY_UNRESOLVED, A.NO_TRADE, A.EXPIRED, A.MISSED, A.BLOCKED,
                   A.INSUFFICIENT_DATA, A.OUT_OF_SESSION}
        assert r.decision in allowed


def test_duplicate_delivery_restart_dedup(tmp_path):
    """Running twice must not change the logical ticket_id."""
    now = dt.datetime(2026, 10, 7, 7, 30, tzinfo=UTC)
    r1 = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=False,
                              policy_root=str(tmp_path))
    r2 = run_daily_evaluation(now=now, archive_root=str(tmp_path), include_crypto=False,
                              policy_root=str(tmp_path))
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
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    viz = canon["structure_visual"]
    assert "TP2" in viz
    assert "TP1" in viz
    assert "NOW" in viz or "ENTRY" in viz
    assert "POI" in viz
    assert "SL" in viz
    assert "estimated path" in viz
    assert "not a forecast" in viz


def test_logic_status_not_invented():
    """A strategy with logic_status: NOT_VERIFIED in the registry must surface that exactly."""
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["logic_status"] == "NOT_VERIFIED"
    assert canon["economic_status"] == "NOT_EVALUATED"
    assert canon["economic_edge"] == "NOT VERIFIED"


def test_long_without_h1_context_is_not_available():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    # Legacy V1 ticket provides regime -> d1_context is SOURCE_FACT, but no h1_context / POI.
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["context"]["h1_context"] == NOT_AVAILABLE
    assert canon["fact_provenance"]["h1_context"]["status"] == "NOT_AVAILABLE"
    assert canon["direction"] == "LONG"  # LONG setup, but we did not invent "H1 discount"


def test_short_without_h1_context_is_not_available():
    # Build a SHORT sweep by using a different session pair (box high sweep).  Use synthetic
    # post-session wick above box high and close back inside -> SHORT signal.
    now = dt.datetime(2026, 10, 7, 12, 20, tzinfo=UTC)  # during LONDON_NEWYORK window
    day = now.date()
    box_hi, box_lo = 1.1650, 1.1600
    ref_start = dt.datetime.combine(day, dt.time(6, 0), tzinfo=UTC)
    ref = []
    for i in range(20):  # LONDON ref is 06:00-11:00 -> 20 M15 bars
        t = ref_start + dt.timedelta(minutes=15*i)
        mid = (box_hi+box_lo)/2
        if i == 0:
            ref.append(_c(t.isoformat(), box_hi-0.0020, box_hi, box_lo, mid))
        else:
            ref.append(_c(t.isoformat(), mid, mid, mid, mid))
    post_start = dt.datetime.combine(day, dt.time(12, 0), tzinfo=UTC)
    sweep_time = now - dt.timedelta(minutes=5)
    sweep_time = sweep_time.replace(minute=(sweep_time.minute//15)*15, second=0, microsecond=0)
    post = []
    t = post_start
    while t < sweep_time:
        mid=(box_hi+box_lo)/2
        post.append(_c(t.isoformat(), mid, mid+0.0002, mid-0.0002, mid)); t += dt.timedelta(minutes=15)
    # SHORT sweep: wick above box_hi, closes back inside.
    post.append(_c(sweep_time.isoformat(), box_hi-0.0003, box_hi+0.0008, box_hi-0.0005, box_hi-0.0004))
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "LONDON_NEWYORK", day, ref, 20, post, data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1640, policy=SIGNED_POLICY)
    assert canon["direction"] == "SHORT"
    assert canon["context"]["h1_context"] == NOT_AVAILABLE
    assert canon["fact_provenance"]["h1_context"]["status"] == "NOT_AVAILABLE"
    # Must NOT contain the previously-invented "H1 premium" phrase.
    assert "premium" not in canon["context"]["h1_context"]
    text = render_canonical(canon)
    assert "H1 premium" not in text


def test_missing_poi_is_not_available():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["poi"] == NOT_AVAILABLE
    assert canon["fact_provenance"]["poi"]["status"] == "NOT_AVAILABLE"


def test_supplied_poi_and_context_preserved_exactly(stub_symbol_verified):
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    # Inject source-supplied context (e.g., from an upstream opportunity adapter).
    ticket["context"] = {
        "d1_context": "D1 bullish",
        "h1_context": "H1 discount",
        "structure": "SSL sweep → reclaim → displacement",
        "poi": "1.1620–1.1630",
    }
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["context"]["d1_context"] == "D1 bullish"
    assert canon["context"]["h1_context"] == "H1 discount"
    assert canon["context"]["structure"] == "SSL sweep → reclaim → displacement"
    assert canon["poi"] == "1.1620–1.1630"
    assert canon["fact_provenance"]["poi"]["status"] == "SOURCE_FACT"
    # Rendered text should show supplied POI exactly.
    text = render_canonical(canon)
    assert "1.1620–1.1630" in text


def test_execution_authorization_always_false():
    now = dt.datetime(2026, 10, 7, 7, 20, tzinfo=UTC)
    ref, n, post = _build_asian_london_sweep(now, age_minutes=5)
    ticket = v1_fx.build_fx_ticket(
        "EURUSD", "ASIAN_LONDON", now.date(), ref, n, post,
        data_source="TEST", evaluated_at=now,
        data_close=post[-1].time + dt.timedelta(minutes=15), spread=0.0001,
    )
    canon = build_canonical_ticket(ticket, now=now, current_price=1.1636, policy=SIGNED_POLICY)
    assert canon["execution_authorization"] is False
    assert canon["demo_authorized"] is False
    assert canon["live_authorized"] is False


if __name__ == "__main__":
    import pytest as _p
    sys.exit(_p.main([__file__, "-v"]))
