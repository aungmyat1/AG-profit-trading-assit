"""AG_FX_OPPORTUNITY_PLATFORM_V2 P2: MarketState + generalized runner, per symbol.

Fixtures are synthetic, deterministic and labelled REPLAY; no historical dataset
(and never the sealed OOS set) is read. Each symbol's bars are an affine image of the
EURUSD fixture at that instrument's own price level/pip scale, so the frozen strategy's
scale-invariant decision is identical across symbols while the prices are not.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from fx_opportunity import CYCLES, evaluate_fx_opportunity
from fx_opportunity.instruments import get_instrument
from fx_opportunity.market_state import MarketState, build_market_state, observe_market_state
from fx_opportunity.runner import RESEARCH_STRATEGY
from mt5.market_data import MarketDataError
from opportunity.candidate_store import CandidateStore
from opportunity.registry_binding import resolve_strategy_binding
from post_asian_pilot.pilot_config import load_pilot_config
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 9, 21)
M15 = dt.timedelta(minutes=15)
BINDING = resolve_strategy_binding("ST_ASIAN_SWEEP_5R_V1")
PILOTS = {cycle: load_pilot_config(path) for cycle, path in CYCLES.items()}
STRATEGY = load_strategy(PILOTS["POST_ASIAN"].strategy_source_path)

# (base price, price units per EURUSD unit) -- keeps each fixture in its own pip scale
LEVELS = {"EURUSD": (1.1000, 1.0), "GBPUSD": (1.3000, 1.0), "USDJPY": (150.00, 100.0)}
BOUND = ("EURUSD", "GBPUSD")


def at(h, m=0):
    return dt.datetime.combine(DAY, dt.time(h, m), tzinfo=UTC)


def px(symbol, p):
    base, scale = LEVELS[symbol]
    return round(base + (p - 1.1000) * scale, get_instrument(symbol).digits)


def c(symbol, t, o, h, l, cl):
    return Candle(time=t, open=px(symbol, o), high=px(symbol, h), low=px(symbol, l),
                  close=px(symbol, cl), volume=100.0)


def range_session(symbol, start, bars):
    out = []
    for i in range(bars):
        t = start + i * M15
        if i == 5:
            out.append(c(symbol, t, 1.1010, 1.1025, 1.1005, 1.1012))
        elif i == 11:
            out.append(c(symbol, t, 1.1010, 1.1015, 1.0995, 1.1008))
        elif i % 2 == 0:
            out.append(c(symbol, t, 1.1005, 1.1018, 1.1002, 1.1015))
        else:
            out.append(c(symbol, t, 1.1015, 1.1018, 1.1002, 1.1005))
    return out


def inside(symbol, t):
    return c(symbol, t, 1.1008, 1.1016, 1.1003, 1.1010)


def sweep(symbol, t):
    return c(symbol, t, 1.1004, 1.1009, 1.0988, 1.1001)


class Feed:
    def __init__(self, bars):
        self.bars = list(bars)
        self.calls = []

    def __call__(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        out = [b for b in self.bars if start <= b.time < end]
        if not out:
            raise MarketDataError("DATA_MISSING", "fixture has no bars")
        return out


def ready_bars(symbol):
    return range_session(symbol, at(0), 24) + [inside(symbol, at(7)), sweep(symbol, at(7, 15))]


def run(symbol, feed, now, *, cycle="POST_ASIAN", mode="REPLAY", store=None, **kw):
    return evaluate_fx_opportunity(
        cycle=cycle, symbol=symbol, trading_date=DAY, now=now, pilot=PILOTS[cycle], strategy=STRATEGY,
        binding=BINDING, fetch_candles=feed, market_data_mode=mode, source="fixture", store=store, **kw)


# --- generalized runner --------------------------------------------------------------


@pytest.mark.parametrize("symbol", BOUND)
def test_bound_symbols_reach_the_same_scale_invariant_decision(symbol):
    r = run(symbol, Feed(ready_bars(symbol)), at(7, 31))
    assert (r.decision.status, r.opportunity) == ("READY", "OPPORTUNITY")
    assert r.candidate.geometry.direction == "LONG"
    assert r.candidate.geometry.entry == px(symbol, 1.1001)
    assert r.strategy_role == RESEARCH_STRATEGY
    assert (r.proposal, r.trade_ticket) == ("NO_PROPOSAL_AUTHORITY", "NOT_CREATED")
    assert r.market_state.symbol == symbol
    assert r.provenance["reference_box"]["range_pips"] == 30.0


def test_usdjpy_pips_use_its_own_pip_size():
    state = observe(sym="USDJPY", now=at(7, 31))[0]
    # 0.30 JPY range == 30 pips; a universal 0.0001 pip would have produced 3000
    assert (state.reference_range, state.reference_range_pips) == (0.3, 30.0)


def test_candidate_identity_is_per_symbol_and_cycle():
    ids = {run(s, Feed(ready_bars(s)), at(7, 31)).candidate.candidate_id for s in BOUND}
    assert len(ids) == 2


# --- MarketState ---------------------------------------------------------------------


def observe(sym="EURUSD", now=None, bars=None, mode="REPLAY", **kw):
    pilot = PILOTS["POST_ASIAN"]
    return observe_market_state(
        instrument=get_instrument(sym), cycle="POST_ASIAN", trading_date=DAY, now=now,
        reference_session="asian", reference_window=(at(0), at(6)),
        execution_window=(at(int(pilot.execution_window_start_utc[:2])), at(int(pilot.execution_window_end_utc[:2]))),
        expected_reference_bars=24, fetch_candles=Feed(ready_bars(sym) if bars is None else bars),
        market_data_mode=mode, source="fixture", **kw)


@pytest.mark.parametrize("symbol", sorted(LEVELS))
def test_market_state_facts_and_determinism(symbol):
    a, reasons = observe(symbol, at(7, 31))
    b, _ = observe(symbol, at(7, 31))
    assert reasons == () and a == b and a.fingerprint == b.fingerprint
    assert a.reference_complete and a.reference_bar_count == 24
    assert (a.reference_high, a.reference_low) == (px(symbol, 1.1025), px(symbol, 1.0995))
    assert a.reference_low_taken is True and a.reference_high_taken is False
    assert a.last_closed_bar["close_utc"] == at(7, 30).isoformat()


@pytest.mark.parametrize("symbol", sorted(LEVELS))
def test_market_state_ignores_forming_and_future_bars(symbol):
    base = range_session(symbol, at(0), 24) + [inside(symbol, at(7)), inside(symbol, at(7, 15))]
    now = at(7, 31)  # the 07:30 bar is forming
    future_a = [sweep(symbol, at(7, 30)), inside(symbol, at(7, 45))]
    future_b = [c(symbol, at(7, 30), 1.2, 1.3, 1.0, 1.25), c(symbol, at(7, 45), 0.9, 0.95, 0.8, 0.85)]
    states = [observe(symbol, now, bars=base + f)[0] for f in (future_a, future_b, [])]
    assert states[0] == states[1] == states[2]
    runs = [run(symbol, Feed(base + f), now) for f in (future_a, future_b, [])] if symbol in BOUND else []
    for r in runs:
        r.provenance.pop("post_session_bars_dropped")
    assert all(r.summary() == runs[0].summary() for r in runs)


def test_build_market_state_rejects_a_forming_bar():
    with pytest.raises(ValueError):
        build_market_state(
            instrument=get_instrument("EURUSD"), cycle="POST_ASIAN", trading_date=DAY, now=at(7, 20),
            reference_session="asian", reference_window=(at(0), at(6)), execution_window=(at(7), at(11)),
            expected_reference_bars=24, reference_candles=range_session("EURUSD", at(0), 24),
            post_candles=[sweep("EURUSD", at(7, 15))], market_data_mode="REPLAY", source="fixture")


def test_historical_and_live_modes_are_distinguishable():
    hist, _ = observe(now=at(7, 31), mode="REPLAY")
    live, _ = observe(now=at(7, 31), mode="REAL")
    assert (hist.market_data_mode, live.market_data_mode) == ("REPLAY", "REAL")
    assert hist.fingerprint != live.fingerprint


def test_spread_recorded_only_when_observed():
    none, _ = observe("USDJPY", at(7, 31))
    seen, _ = observe("USDJPY", at(7, 31), spread_price=0.012, spread_source="mt5.symbol_info_tick")
    assert (none.spread_pips, none.spread_source) == (None, None)
    assert (seen.spread_pips, seen.spread_source) == (1.2, "mt5.symbol_info_tick")


def test_before_reference_close_nothing_is_fetched():
    feed = Feed(ready_bars("EURUSD"))
    state, reasons = observe_market_state(
        instrument=get_instrument("EURUSD"), cycle="POST_ASIAN", trading_date=DAY, now=at(5, 59),
        reference_session="asian", reference_window=(at(0), at(6)), execution_window=(at(7), at(11)),
        expected_reference_bars=24, fetch_candles=feed, market_data_mode="REPLAY", source="fixture")
    assert feed.calls == [] and state.reference_complete is False and reasons == ()


def test_fetch_failure_is_reported_not_raised():
    state, reasons = observe(now=at(7, 31), bars=[])
    assert state is None and reasons == ("DATA_MISSING",)


_AUTHORITY_WORDS = ("execute", "authoriz", "authority", "signal", "direction", "buy", "sell",
                    "order", "ticket", "proposal", "broker")


def test_market_state_carries_no_trading_authority():
    for f in dataclasses.fields(MarketState):
        assert not any(w in f.name.lower() for w in _AUTHORITY_WORDS), f.name
    state, _ = observe(now=at(7, 31))
    assert not any(w in k.lower() for k in state.to_dict() for w in _AUTHORITY_WORDS)


# --- provenance / persistence --------------------------------------------------------


def test_provenance_identifies_strategy_config_and_application():
    r = run("GBPUSD", Feed(ready_bars("GBPUSD")), at(7, 31), application_lineage="deadbeef")
    p = r.provenance
    for key in ("strategy_config_fingerprint", "pilot_config_fingerprint", "instrument_fingerprint",
                "market_state_fingerprint", "evaluation_fingerprint", "lineage_fingerprint"):
        assert len(p[key]) == 64, key
    assert (p["strategy_id"], p["strategy_version"], p["application_lineage"]) == (
        "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "deadbeef")
    # application lineage is provenance only: it never changes identity or fingerprints
    other = run("GBPUSD", Feed(ready_bars("GBPUSD")), at(7, 31), application_lineage="cafebabe")
    assert other.provenance["evaluation_fingerprint"] == p["evaluation_fingerprint"]
    assert other.candidate.candidate_id == r.candidate.candidate_id


def test_multi_symbol_persistence_dedup_and_restart(tmp_path):
    path = str(tmp_path / "candidates.json")
    for symbol in BOUND:
        first = run(symbol, Feed(ready_bars(symbol)), at(7, 31), store=CandidateStore(path))
        again = run(symbol, Feed(ready_bars(symbol)), at(7, 46), store=CandidateStore(path))
        assert again.transition is None and again.candidate.revision == first.candidate.revision
    assert sorted(c.symbol for c in CandidateStore(path).all_candidates()) == list(BOUND)


def test_server_clock_is_recorded_and_fingerprinted():
    clock = [{"broker": "VT Markets", "server": "VTMarkets-Demo", "effective_from_utc": "2026-09-20T21:00:00+00:00",
              "effective_until_utc": "2026-09-27T20:00:00+00:00", "effective_until_basis": "WEEK_BOUND",
              "utc_offset_hours": 3, "source": "SERVER_CONSENSUS", "evidence_symbols": ["EURUSD", "GBPUSD"],
              "scope": "SERVER_SHARED"}]
    plain, _ = observe("USDJPY", at(7, 31))
    timed, _ = observe("USDJPY", at(7, 31), server_clock=clock)
    assert plain.server_clock is None
    assert timed.server_clock == tuple(clock) and timed.fingerprint != plain.fingerprint
    r = run("EURUSD", Feed(ready_bars("EURUSD")), at(7, 31), server_clock=clock)
    assert r.market_state.server_clock == tuple(clock) and r.provenance["server_clock"] == clock
