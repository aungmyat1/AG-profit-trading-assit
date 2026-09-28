"""AG_FX_OPPORTUNITY_FOUNDATION_V1: EURUSD Opportunity slice -> fail-closed Proposal.

Fixture candles are labelled REPLAY (never REAL) except where a test must prove the
proposal-authority gate blocks even a candidate the existing eligibility boundary
would accept; those tests say so explicitly.
"""
from __future__ import annotations

import ast
import datetime as dt
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import MetaTrader5
from fx_opportunity import (
    CYCLES,
    PROPOSAL_FORMATION_NOT_WIRED,
    PROPOSAL_NO_AUTHORITY,
    TRADE_TICKET_NOT_CREATED,
    evaluate_fx_opportunity,
)
from fx_opportunity.runner import FxOpportunityScopeError
from mt5.market_data import MarketDataError
from opportunity.candidate_store import CandidateStore
from opportunity.contracts import ELIGIBILITY_BLOCKED, ELIGIBILITY_ELIGIBLE
from opportunity.registry_binding import resolve_strategy_binding
from post_asian_pilot.pilot_config import load_pilot_config
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 9, 21)
M15 = dt.timedelta(minutes=15)

BINDING = resolve_strategy_binding("ST_ASIAN_SWEEP_5R_V1")
PILOT_ASIAN = load_pilot_config(CYCLES["POST_ASIAN"])
PILOT_LONDON = load_pilot_config(CYCLES["POST_LONDON"])
STRATEGY = load_strategy(PILOT_ASIAN.strategy_source_path)


def at(h, m=0):
    return dt.datetime.combine(DAY, dt.time(h, m), tzinfo=UTC)


def c(t, o, h, l, cl):
    return Candle(time=t, open=o, high=h, low=l, close=cl, volume=100.0)


def range_session(start, bars):
    """Oscillating bars -> low efficiency ratio -> RANGE. High 1.1025 / low 1.0995."""
    out = []
    for i in range(bars):
        t = start + i * M15
        if i == 5:
            out.append(c(t, 1.1010, 1.1025, 1.1005, 1.1012))
        elif i == 11:
            out.append(c(t, 1.1010, 1.1015, 1.0995, 1.1008))
        elif i % 2 == 0:
            out.append(c(t, 1.1005, 1.1018, 1.1002, 1.1015))
        else:
            out.append(c(t, 1.1015, 1.1018, 1.1002, 1.1005))
    return out


def inside_bar(t):
    return c(t, 1.1008, 1.1016, 1.1003, 1.1010)


def lower_sweep_bar(t):
    # low pierces 1.0995 strictly, close back inside -> LOWER_SWEEP_STRICT_PENETRATION / LONG
    return c(t, 1.1004, 1.1009, 1.0988, 1.1001)


class Feed:
    """Injected read-only candle source; records every call."""

    def __init__(self, bars):
        self.bars = list(bars)
        self.calls = []

    def __call__(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        assert timeframe == "M15"
        out = [b for b in self.bars if start <= b.time < end]
        if not out:
            raise MarketDataError("DATA_MISSING", "fixture has no bars")
        return out


def asian_bars():
    return range_session(at(0), 24)


def run(feed, now, *, pilot=PILOT_ASIAN, mode="REPLAY", store=None, binding=BINDING, symbol="EURUSD"):
    return evaluate_fx_opportunity(
        cycle="POST_ASIAN" if pilot is PILOT_ASIAN else "POST_LONDON",
        symbol=symbol, trading_date=DAY, now=now, pilot=pilot, strategy=STRATEGY, binding=binding,
        fetch_candles=feed, market_data_mode=mode, source="fixture", store=store,
    )


# --- authority -----------------------------------------------------------------------


def test_registry_binding_has_opportunity_but_not_proposal_authority():
    assert BINDING.opportunity_authority is True
    assert BINDING.proposal_authority is False
    assert BINDING.execution_authority == "NONE"


# --- Opportunity outcomes ------------------------------------------------------------


def test_ready_sweep_is_an_opportunity_but_proposal_is_blocked():
    feed = Feed(asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))])
    r = run(feed, at(7, 31))
    assert r.decision.status == "READY"
    assert r.opportunity == "OPPORTUNITY"
    g = r.candidate.geometry
    assert (g.direction, g.entry, g.invalidation) == ("LONG", 1.1001, 1.0988)
    assert r.candidate.market_data_mode == "REPLAY"
    # existing eligibility boundary: replay data is never broker-bound
    assert r.eligibility.status == ELIGIBILITY_BLOCKED
    assert r.proposal == PROPOSAL_NO_AUTHORITY
    assert r.trade_ticket == TRADE_TICKET_NOT_CREATED


def test_authority_gate_blocks_even_when_existing_eligibility_passes():
    """Mode labelled REAL here ONLY to drive the existing eligibility boundary to
    ELIGIBLE; proves the proposal-authority gate is what stops formation."""
    feed = Feed(asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))])
    r = run(feed, at(7, 31), mode="REAL")
    assert r.eligibility.status == ELIGIBILITY_ELIGIBLE
    assert r.proposal == PROPOSAL_NO_AUTHORITY
    assert r.trade_ticket == TRADE_TICKET_NOT_CREATED


def test_authorized_binding_still_never_forms_a_proposal_here():
    feed = Feed(asian_bars() + [lower_sweep_bar(at(7))])
    r = run(feed, at(7, 16), binding=replace(BINDING, proposal_authority=True))
    assert r.proposal == PROPOSAL_FORMATION_NOT_WIRED
    assert r.trade_ticket == TRADE_TICKET_NOT_CREATED


def test_no_sweep_is_watch_then_expired_no_opportunity():
    bars = asian_bars() + [inside_bar(at(7) + i * M15) for i in range(16)]
    mid = run(Feed(bars), at(8, 1))
    assert (mid.decision.status, mid.opportunity) == ("WATCH", "NO_OPPORTUNITY")
    end = run(Feed(bars), at(11, 0))
    assert (end.decision.status, end.opportunity) == ("EXPIRED", "NO_OPPORTUNITY")
    assert end.candidate.outcome == "EXPIRED"


def test_before_reference_close_waits_without_fetching():
    feed = Feed(asian_bars())
    r = run(feed, at(5, 59))
    assert r.decision.missing_condition == "WAITING_REFERENCE_SESSION_COMPLETION"
    assert feed.calls == []


def test_between_reference_close_and_window_open_waits():
    r = run(Feed(asian_bars()), at(6, 30))
    assert r.decision.missing_condition == "WAITING_EXECUTION_WINDOW_OPEN"
    assert r.provenance["session_snapshot_id"].startswith("SNAPSHOT-EURUSD-2026-09-21")


def test_post_london_cycle_uses_its_own_canonical_windows():
    london = range_session(at(6), 20)
    feed = Feed(london + [lower_sweep_bar(at(12))])
    r = run(feed, at(12, 16), pilot=PILOT_LONDON)
    assert r.pair_id == "LONDON_NEWYORK"
    assert r.provenance["reference_window_utc"] == [at(6).isoformat(), at(11).isoformat()]
    assert r.decision.status == "READY"
    assert r.proposal == PROPOSAL_NO_AUTHORITY


# --- data quality --------------------------------------------------------------------


def test_missing_reference_candle_is_data_error():
    bars = asian_bars()
    del bars[7]
    r = run(Feed(bars + [lower_sweep_bar(at(7))]), at(7, 16))
    assert r.decision.status == "DATA_ERROR"
    assert any(code.startswith("BAR_COUNT_MISMATCH") for code in r.decision.reason_codes)
    assert r.opportunity == "NO_OPPORTUNITY"


def test_duplicated_reference_timestamp_is_data_error():
    bars = asian_bars()
    bars[3] = replace(bars[3], time=bars[2].time)
    r = run(Feed(bars + [lower_sweep_bar(at(7))]), at(7, 16))
    assert r.decision.status == "DATA_ERROR"
    assert "DUPLICATE_BAR_TIME" in r.decision.reason_codes


def test_duplicated_post_session_timestamp_is_data_error():
    dup = lower_sweep_bar(at(7))
    r = run(Feed(asian_bars() + [inside_bar(at(7)), dup]), at(7, 31))
    assert r.decision.status == "DATA_ERROR"
    assert r.decision.reason_codes == ("POST_SESSION_DUPLICATE_OR_UNORDERED_BARS",)


def test_market_data_error_is_data_error_not_exception():
    def broken(*_):
        raise MarketDataError("MT5_NOT_CONNECTED", "down")
    r = run(broken, at(7, 16))
    assert r.decision.reason_codes == ("MT5_NOT_CONNECTED",)


# --- look-ahead ----------------------------------------------------------------------


def test_forming_candle_is_never_evaluated():
    # the 07:15 sweep bar is still forming at 07:20
    feed = Feed(asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))])
    r = run(feed, at(7, 20))
    assert r.decision.status == "WATCH"
    assert r.provenance["post_session_bars_dropped"] == 1
    assert r.candidate.geometry is None


def test_future_candle_mutation_does_not_change_result():
    base = asian_bars() + [inside_bar(at(7)), inside_bar(at(7, 15))]
    future_a = [lower_sweep_bar(at(7, 30)), inside_bar(at(7, 45))]
    future_b = [c(at(7, 30), 1.2, 1.3, 1.0, 1.25), c(at(7, 45), 0.9, 0.95, 0.8, 0.85)]
    now = at(7, 31)  # 07:30 bar is forming
    a = run(Feed(base + future_a), now).summary()
    b = run(Feed(base + future_b), now).summary()
    none = run(Feed(base), now).summary()
    for s in (a, b, none):
        s["provenance"].pop("post_session_bars_dropped")
    assert a == b == none
    assert a["decision_status"] == "WATCH"


# --- determinism / persistence -------------------------------------------------------


def test_identical_input_replays_identically():
    bars = asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))]
    first = run(Feed(bars), at(7, 31)).summary()
    second = run(Feed(bars), at(7, 31)).summary()
    assert first == second
    assert first["provenance"]["lineage_fingerprint"]


def test_same_occurrence_keeps_identity_and_repeated_poll_is_idempotent(tmp_path):
    store = CandidateStore(str(tmp_path / "candidates.json"))
    bars = asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))]
    watch = run(Feed(bars), at(7, 16), store=store)
    ready = run(Feed(bars), at(7, 31), store=store)
    again = run(Feed(bars), at(7, 46), store=CandidateStore(str(tmp_path / "candidates.json")))
    assert watch.candidate.candidate_id == ready.candidate.candidate_id == again.candidate.candidate_id
    assert (watch.candidate.revision, ready.candidate.revision) == (1, 2)
    assert again.transition is None and again.candidate.revision == 2
    assert len(store.transitions(ready.candidate.candidate_id)) == 2


# --- scope ---------------------------------------------------------------------------


def test_non_slice_symbol_fails_closed():
    with pytest.raises(FxOpportunityScopeError):
        run(Feed(asian_bars()), at(7, 16), symbol="GBPUSD")


def test_strategy_version_mismatch_fails_closed():
    with pytest.raises(FxOpportunityScopeError):
        evaluate_fx_opportunity(
            cycle="POST_ASIAN", symbol="EURUSD", trading_date=DAY, now=at(7, 16), pilot=PILOT_ASIAN,
            strategy=replace(STRATEGY, version="9.9.9"), binding=BINDING,
            fetch_candles=Feed(asian_bars()), market_data_mode="REPLAY", source="fixture",
        )


# --- zero execution ------------------------------------------------------------------

_BROKER_MUTATION_APIS = ("order_send", "order_check", "positions_get", "positions_total",
                         "orders_get", "orders_total", "trade_buy", "trade_sell", "trade_close",
                         "trade_modify", "trade_cancel")


def test_zero_broker_calls_sentinel(monkeypatch, tmp_path):
    calls = []
    for name in _BROKER_MUTATION_APIS:
        monkeypatch.setattr(MetaTrader5, name, lambda *a, _n=name, **k: calls.append(_n), raising=False)
    store = CandidateStore(str(tmp_path / "c.json"))
    bars = asian_bars() + [inside_bar(at(7)), lower_sweep_bar(at(7, 15))]
    for now in (at(5), at(6, 30), at(7, 16), at(7, 31), at(11)):
        run(Feed(bars), now, store=store, mode="REAL")
    assert calls == []


def test_slice_imports_no_execution_or_proposal_formation_module():
    """Fresh interpreter so other suites' imports cannot mask or fake the result."""
    repo = Path(__file__).resolve().parents[1]
    code = (
        "import sys; import fx_opportunity.runner; "
        "bad=[m for m in sys.modules if m.split('.')[0] in "
        "('execution','execution_runtime','authorization','ticket_delivery','notifications','proposal_envelope')"
        " or m in ('mt5.connection','mt5.account','mt5.management_gateway','post_asian_pilot.proposal',"
        "'post_asian_pilot.store','post_asian_pilot.governor','post_asian_pilot.pipeline')]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(repo), str(repo / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


_ALLOWED_IMPORT_ROOTS = {"__future__", "datetime", "hashlib", "json", "dataclasses", "typing", "yaml",
                         "session_clock", "mt5", "opportunity", "post_asian_pilot", "strategy_engine"}
_FORBIDDEN_TOKENS = ("order_send", "order_check", "execution.", "telegram", "requests", "user_confirmed")


def test_static_scan_new_package_has_no_execution_capability():
    pkg = Path(__file__).resolve().parents[1] / "src" / "fx_opportunity"
    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = {node.module.split(".")[0]}
                assert node.module in (None, "mt5.market_data") or not node.module.startswith("mt5"), node.module
            else:
                continue
            assert roots <= _ALLOWED_IMPORT_ROOTS, (path.name, roots)
        code = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith("#"))
        body = ast.get_docstring(tree) or ""
        for token in _FORBIDDEN_TOKENS:
            assert token not in code.replace(body, ""), (path.name, token)
