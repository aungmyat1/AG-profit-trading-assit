"""AG V1 T5/T8: ST_LARGE_SMC_V1@1.1.0 watch. Positive and negative fixtures, truncation
invariance, no look-ahead, session-end expiry, stale -> suspend -> expire, restart and
duplicate-poll idempotence, market closed, symbol metadata fail-closed.

Synthetic fixtures only (tests/_lsmc_v110_fixtures.py); no market data."""
from __future__ import annotations

import datetime as dt
import glob
import os

import pytest

from _lsmc_v110_fixtures import NOW, UTC, d1_bars, h1_bars, m5_bars
from large_smc_watch import WatchTracker, evaluate_snapshot
from large_smc_watch import contract as C
from large_smc_watch.watch import next_day_boundary, session_end, trading_date

NEAR = dt.datetime(2026, 1, 6, 8, 35, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_host_evidence(tmp_path, monkeypatch):
    """Host captures on the machine running the tests (repo-root evidence) must never leak in."""
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "no_evidence"))


def snap(now=NOW, symbol="EURUSD", k=1.0, point=None, **m5kw):
    return evaluate_snapshot(symbol, d1_bars(k), h1_bars(k), m5_bars(k, **m5kw), now, point=point)


def _truncate(bars, minutes, now):
    return [b for b in bars if b.time + dt.timedelta(minutes=minutes) <= now]


# ------------------------------------------------------------------ contract

def test_contract_is_alerts_only_new_version():
    assert (C.STRATEGY_ID, C.STRATEGY_VERSION) == ("ST_LARGE_SMC_V1", "1.1.0")
    assert C.PROPOSAL_GENERATION_AUTHORIZED is False
    assert C.ECONOMIC_STATUS == "NOT_EVALUATED"
    assert (C.POI_MAX_AGE_TRADING_DAYS, C.SWEEP_TO_CHOCH_WINDOW_M5, C.NEAR_POI_BAND_ATR_MULT) == (5, 12, 0.5)
    assert C.TIE_TOLERANCE_POINTS == 5 and C.ATR_H1_PERIOD == 14
    assert C.ALERT_LEVEL == {"DEVELOPING": "INFO", "NEAR_POI": "WATCH", "OPPORTUNITY": "OPPORTUNITY",
                             "INVALIDATED": "INFO", "EXPIRED": "INFO"}


# ------------------------------------------------------------------ positive / negative fixtures

def test_positive_near_poi_then_opportunity():
    near = snap(NEAR)
    assert near.state == "NEAR_POI" and near.bias == "LONG"
    assert near.poi["kind"] == "FVG" and near.poi["distance"] <= near.poi["band"]
    opp = snap(NOW)
    assert opp.state == "OPPORTUNITY"
    o = opp.opportunity
    assert o["direction"] == "LONG" and o["economic_status"] == "NOT_EVALUATED"
    assert o["expires_at"] == "2026-01-06T11:00:00+00:00"          # london_am session end
    assert o["stop_c10"] is not None and o["stop_c10"] < o["sweep_extreme"]
    assert "D30_BADGE_ECONOMICS_NOT_EVALUATED" in opp.reason_codes


def test_negative_choch_outside_sweep_window_is_not_an_opportunity():
    late = snap(NOW + dt.timedelta(minutes=55), choch_delay=11)
    assert late.state != "OPPORTUNITY"


def test_negative_choch_without_displacement_is_not_an_opportunity():
    assert snap(NOW, weak_choch=True).state != "OPPORTUNITY"


def test_negative_no_data_or_unknown_symbol_fails_closed():
    assert snap(NOW, symbol="AUDUSD").state == "DATA_ERROR"
    early = evaluate_snapshot("EURUSD", d1_bars(), h1_bars()[:10], m5_bars(), NOW)
    assert early.state == "DATA_ERROR" and "INSUFFICIENT_HISTORY" in early.reason_codes


# ------------------------------------------------------------------ causality

@pytest.mark.parametrize("minutes", [0, 5, 10, 25, 50, 80])
def test_truncation_invariance(minutes):
    now = NEAR + dt.timedelta(minutes=minutes)
    full = evaluate_snapshot("EURUSD", d1_bars(), h1_bars(), m5_bars(), now)
    cut = evaluate_snapshot("EURUSD", _truncate(d1_bars(), 1440, now), _truncate(h1_bars(), 60, now),
                            _truncate(m5_bars(), 5, now), now)
    assert full == cut


def test_no_lookahead_future_choch_invisible_before_its_close():
    choch_open = dt.datetime(2026, 1, 6, 8, 50, tzinfo=UTC)   # CHoCH bar closes 08:55
    before = snap(choch_open + dt.timedelta(minutes=4))
    after = snap(choch_open + dt.timedelta(minutes=5))
    assert before.state != "OPPORTUNITY"
    assert after.state == "OPPORTUNITY"


def test_deterministic_repeat():
    assert snap(NOW) == snap(NOW)


# ------------------------------------------------------------------ lifecycle

def test_session_end_expiry():
    s = snap(dt.datetime(2026, 1, 6, 11, 5, tzinfo=UTC), total=65)
    assert s.state != "OPPORTUNITY"
    assert s.expired_opportunity_ids


def test_invalidation_by_close_beyond_sweep_extreme():
    s = snap(NOW, break_after=True)
    assert s.state != "OPPORTUNITY" and s.invalidated_opportunity_ids


def test_day_boundary_is_ny_1700_with_dst():
    assert trading_date(dt.datetime(2026, 1, 6, 21, 59, tzinfo=UTC)) == dt.date(2026, 1, 6)   # 16:59 EST
    assert trading_date(dt.datetime(2026, 1, 6, 22, 0, tzinfo=UTC)) == dt.date(2026, 1, 7)    # 17:00 EST
    assert trading_date(dt.datetime(2026, 7, 6, 20, 59, tzinfo=UTC)) == dt.date(2026, 7, 6)   # 16:59 EDT
    assert trading_date(dt.datetime(2026, 7, 6, 21, 0, tzinfo=UTC)) == dt.date(2026, 7, 7)    # 17:00 EDT
    assert next_day_boundary(dt.datetime(2026, 7, 6, 12, 0, tzinfo=UTC)) == dt.datetime(2026, 7, 6, 21, 0, tzinfo=UTC)


def test_session_end_outside_canonical_sessions_rolls_to_day_boundary():
    assert session_end(dt.datetime(2026, 1, 6, 16, 0, tzinfo=UTC)) == dt.datetime(2026, 1, 6, 22, 0, tzinfo=UTC)


def test_market_closed_fx_weekend_but_crypto_open():
    saturday = dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    assert snap(saturday).state == "MARKET_CLOSED"
    assert snap(saturday, symbol="BTCUSDT", k=60000.0).state != "MARKET_CLOSED"


# ------------------------------------------------------------------ instruments / metadata

def test_usdjpy_xauusd_require_caller_point_fixture_only():
    assert snap(NOW, symbol="USDJPY", k=140.0).reason_codes == ("SYMBOL_METADATA_MISSING",)
    jpy = snap(NOW, symbol="USDJPY", k=140.0, point=0.001)
    assert jpy.metadata_source == "CALLER_SUPPLIED" and jpy.state == "OPPORTUNITY"
    assert jpy.opportunity["stop_reason"] == "C10_PIP_SIZE_NOT_EVIDENCED"
    xau = snap(NOW, symbol="XAUUSD", k=2400.0, point=0.01)
    assert xau.metadata_source == "CALLER_SUPPLIED" and xau.state == "OPPORTUNITY"


@pytest.mark.parametrize("symbol,k", [("GBPUSD", 1.2), ("BTCUSDT", 60000.0), ("ETHUSDT", 3000.0)])
def test_repo_evidenced_symbols_run_on_the_same_rules(symbol, k):
    s = snap(NOW, symbol=symbol, k=k)
    assert s.metadata_source == "REPO_EVIDENCED" and s.state == "OPPORTUNITY"


# ------------------------------------------------------------------ tracker / journal (T8 hardening)

def _tracker(tmp_path):
    return WatchTracker(str(tmp_path / "state.json"), str(tmp_path / "archive"))


def _archived(tmp_path):
    return sorted(glob.glob(str(tmp_path / "archive" / "**" / "*.json"), recursive=True))


def test_tracker_emits_mapped_alerts_and_archives_only(tmp_path):
    tr = _tracker(tmp_path)
    ev1 = tr.poll(snap(NEAR))
    ev2 = tr.poll(snap(NOW))
    assert [(e.to_state, e.alert_level) for e in ev1] == [("NEAR_POI", "WATCH")]
    assert [(e.to_state, e.alert_level) for e in ev2] == [("OPPORTUNITY", "OPPORTUNITY")]
    assert all(e.delivery_mode == "ARCHIVE_ONLY" and e.proposal_generation_authorized is False for e in ev1 + ev2)
    files = _archived(tmp_path)
    assert len(files) == 2 and all("LSMC_WATCH" in f for f in files)


def test_duplicate_poll_and_restart_are_idempotent(tmp_path):
    tr = _tracker(tmp_path)
    tr.poll(snap(NEAR))
    tr.poll(snap(NOW))
    assert tr.poll(snap(NOW)) == []                       # duplicate poll
    restarted = _tracker(tmp_path)                        # process restart, same durable state
    assert restarted.poll(snap(NOW)) == []
    assert len(_archived(tmp_path)) == 2


def test_replay_after_crash_before_state_save_does_not_duplicate_archive(tmp_path):
    tr = _tracker(tmp_path)
    tr.poll(snap(NEAR))
    os.remove(tmp_path / "state.json")                    # crash lost the state save, archive survived
    tr2 = _tracker(tmp_path)
    tr2.poll(snap(NEAR))
    assert len(_archived(tmp_path)) == 1


def test_stale_suspends_then_expires(tmp_path):
    tr = _tracker(tmp_path)
    tr.poll(snap(NOW))                                    # OPPORTUNITY, expires 11:00
    stale = snap(dt.datetime(2026, 1, 6, 10, 0, tzinfo=UTC))
    assert stale.state == "STALE"
    assert tr.poll(stale) == []
    assert tr.store.get("EURUSD")["state"] == "SUSPENDED"
    later = snap(dt.datetime(2026, 1, 6, 11, 30, tzinfo=UTC))
    events = tr.poll(later)
    assert [(e.to_state, e.alert_level) for e in events] == [("EXPIRED", "INFO")]


def test_invalidated_alert(tmp_path):
    tr = _tracker(tmp_path)
    tr.poll(snap(NOW))
    events = tr.poll(snap(NOW + dt.timedelta(minutes=5), break_after=True))
    assert events and events[0].to_state == "INVALIDATED" and events[0].alert_level == "INFO"


def test_market_closed_emits_nothing(tmp_path):
    tr = _tracker(tmp_path)
    assert tr.poll(snap(dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC))) == []
    assert _archived(tmp_path) == []


def test_choch_exactly_at_window_edge_still_counts():
    edge = snap(dt.datetime(2026, 1, 6, 10, 20, tzinfo=UTC), choch_delay=10)   # sweep -> CHoCH = 12 bars
    assert edge.state == "OPPORTUNITY"
