"""AG_FX_OPPORTUNITY_PLATFORM_V2 P3: three-pair cycle scan + manual CLI fail-closed paths.

Synthetic REPLAY fixtures only (shared with test_fx_opportunity_market_state); the CLI
tests never touch a real terminal -- one uses the repo stub, one a fake unauthorized module.
"""
from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import types
from pathlib import Path

import pytest

from fx_opportunity import scanner
from fx_opportunity.scanner import load_cycle_context, scan_cycle, scan_symbol
from opportunity.candidate_store import CandidateStore
from test_fx_opportunity_market_state import (
    Feed, at, inside, range_session, ready_bars, sweep, DAY, M15,
)

REPO = Path(__file__).resolve().parents[1]
THREE = ("EURUSD", "GBPUSD", "USDJPY")
CTX = {cycle: load_cycle_context(cycle) for cycle in ("POST_ASIAN", "POST_LONDON")}


class MultiFeed:
    def __init__(self, per_symbol):
        self.feeds = {s: Feed(b) for s, b in per_symbol.items()}

    def __call__(self, symbol, timeframe, start, end):
        return self.feeds[symbol](symbol, timeframe, start, end)


def scan(cycle, feed, now, **kw):
    return scan_cycle(CTX[cycle], THREE, trading_date=DAY, now=now, fetch_candles=feed,
                      market_data_mode="REPLAY", source="fixture", **kw)


def test_post_asian_three_pair_states():
    out = scan("POST_ASIAN", MultiFeed({s: ready_bars(s) for s in THREE}), at(7, 31))
    assert [(s.symbol, s.status) for s in out] == [
        ("EURUSD", "OPPORTUNITY"), ("GBPUSD", "OPPORTUNITY"), ("USDJPY", "NO_COMPATIBLE_OPPORTUNITY_STRATEGY")]
    jpy = out[2]
    assert jpy.result is None and jpy.market_state.reference_complete
    assert jpy.reason_codes == ("SYMBOL_NOT_IN_PILOT_UNIVERSE",)
    for s in out:
        summary = s.summary()
        assert (summary["proposal"], summary["trade_ticket"], summary["execution_authority"]) == (
            "NO_PROPOSAL_AUTHORITY", "NOT_CREATED", "NONE")
    assert out[0].result.strategy_role == "RESEARCH_STRATEGY"


def test_post_london_three_pair_states_no_forced_signal():
    bars = {s: range_session(s, at(6), 20) + [inside(s, at(12) + i * M15) for i in range(4)] for s in THREE}
    out = scan("POST_LONDON", MultiFeed(bars), at(13, 1))
    assert [s.status for s in out] == ["NO_OPPORTUNITY", "NO_OPPORTUNITY", "NO_COMPATIBLE_OPPORTUNITY_STRATEGY"]
    assert out[0].result.decision.status == "WATCH"
    assert out[0].result.provenance["reference_window_utc"] == [at(6).isoformat(), at(11).isoformat()]


def test_symbols_are_independent_and_data_errors_are_explicit():
    bars = {s: ready_bars(s) for s in THREE}
    del bars["GBPUSD"][7]  # incomplete reference session for GBPUSD only
    bars["USDJPY"] = []
    out = scan("POST_ASIAN", MultiFeed(bars), at(7, 31))
    assert [s.status for s in out] == ["OPPORTUNITY", "DATA_UNAVAILABLE", "NO_COMPATIBLE_OPPORTUNITY_STRATEGY"]
    assert out[2].market_state is None and "DATA_MISSING" in out[2].reason_codes


def test_three_pair_scan_is_deterministic():
    feed = lambda: MultiFeed({s: ready_bars(s) for s in THREE})  # noqa: E731
    a = [s.summary() for s in scan("POST_ASIAN", feed(), at(7, 31))]
    b = [s.summary() for s in scan("POST_ASIAN", feed(), at(7, 31))]
    assert a == b


def test_per_symbol_spreads_are_not_shared():
    out = scan("POST_ASIAN", MultiFeed({s: ready_bars(s) for s in THREE}), at(7, 31),
               spreads={"USDJPY": (0.012, "fixture_tick")})
    assert out[0].market_state.spread_pips is None
    assert out[2].market_state.spread_pips == 1.2


def test_unknown_symbol_is_explicit_not_raised():
    s = scan_symbol(CTX["POST_ASIAN"], "AUDUSD", trading_date=DAY, now=at(7, 31), fetch_candles=Feed([]),
                    market_data_mode="REPLAY", source="fixture")
    assert s.status == "UNKNOWN_INSTRUMENT"


def test_restart_persistence_across_three_pairs(tmp_path):
    path = str(tmp_path / "c.json")
    feed = lambda: MultiFeed({s: ready_bars(s) for s in THREE})  # noqa: E731
    first = scan("POST_ASIAN", feed(), at(7, 31), store=CandidateStore(path))
    again = scan("POST_ASIAN", feed(), at(7, 46), store=CandidateStore(path))
    assert [s.result.transition is None for s in again[:2]] == [True, True]
    assert [s.result.candidate.candidate_id for s in first[:2]] == [s.result.candidate.candidate_id for s in again[:2]]
    assert len(CandidateStore(path).all_candidates()) == 2  # no candidate for the unbound symbol


# --- manual CLI fail-closed paths ----------------------------------------------------


def test_cli_rejects_repo_stub_for_every_symbol():
    env = dict(os.environ, PYTHONPATH=str(REPO))  # repo root first -> the stub shadows the real package
    proc = subprocess.run([sys.executable, "scripts/run_fx_opportunity_once.py", "--cycle", "POST_ASIAN",
                           "--symbol", "ALL"], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 2, proc.stderr
    out = json.loads(proc.stdout)
    assert [(r["symbol"], r["status"]) for r in out["results"]] == [
        (s, "MT5_REAL_PACKAGE_UNAVAILABLE") for s in THREE]
    assert set(out["broker_mutation_calls"].values()) == {0}


def test_cli_classifies_unauthorized_terminal_without_reading_data(monkeypatch, capsys):
    calls = []
    fake = types.ModuleType("MetaTrader5")
    fake.__file__ = os.path.join(os.sep, "site-packages", "MetaTrader5", "__init__.py")
    fake.initialize = lambda **k: calls.append("initialize") or False
    fake.last_error = lambda: (-6, "Terminal: Authorization failed")
    fake.shutdown = lambda: calls.append("shutdown")
    for name in ("copy_rates_range", "symbol_info", "symbol_info_tick", "account_info"):
        setattr(fake, name, lambda *a, _n=name, **k: calls.append(_n))
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(sys, "argv", ["run_fx_opportunity_once.py", "--cycle", "POST_LONDON", "--symbol", "ALL"])
    cwd = os.getcwd()
    try:
        ns = runpy.run_path(str(REPO / "scripts" / "run_fx_opportunity_once.py"), run_name="cli_under_test")
        rc = ns["main"]()
    finally:
        os.chdir(cwd)
    out = json.loads(capsys.readouterr().out)
    assert rc == 2 and calls == ["initialize"]  # one attempt, no retry, no data read
    assert {r["status"] for r in out["results"]} == {"LIVE_MT5_AUTH_BLOCKED"}
    assert out["results"][0]["reason_codes"] == ["MT5_INITIALIZE_FAILED:-6"]


def _run_cli_with_fake(monkeypatch, capsys, account):
    calls = []
    fake = types.ModuleType("MetaTrader5")
    fake.__file__ = os.path.join(os.sep, "site-packages", "MetaTrader5", "__init__.py")
    fake.initialize = lambda **k: calls.append("initialize") or True
    fake.shutdown = lambda: calls.append("shutdown")
    fake.account_info = lambda: calls.append("account_info") or account
    fake.ACCOUNT_TRADE_MODE_DEMO = 0
    for name in ("copy_rates_range", "copy_rates_from_pos", "symbol_info", "symbol_info_tick"):
        setattr(fake, name, lambda *a, _n=name, **k: calls.append(_n))
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(sys, "argv", ["run_fx_opportunity_once.py", "--cycle", "POST_ASIAN", "--symbol", "ALL"])
    cwd = os.getcwd()
    try:
        rc = runpy.run_path(str(REPO / "scripts" / "run_fx_opportunity_once.py"), run_name="cli_under_test")["main"]()
    finally:
        os.chdir(cwd)
    return rc, calls, json.loads(capsys.readouterr().out)


def test_cli_refuses_non_demo_account_before_any_data(monkeypatch, capsys):
    rc, calls, out = _run_cli_with_fake(monkeypatch, capsys, types.SimpleNamespace(server="VTMarkets-Live", trade_mode=2, login=123))
    assert rc == 2 and calls == ["initialize", "account_info", "shutdown"]
    assert {r["status"] for r in out["results"]} == {"ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO"}
    assert "123" not in json.dumps(out) and "login" not in json.dumps(out)


def test_cli_refuses_server_not_listed_for_broker(monkeypatch, capsys):
    rc, calls, out = _run_cli_with_fake(monkeypatch, capsys, types.SimpleNamespace(server="Other-Demo", trade_mode=0, login=123))
    assert rc == 2 and "copy_rates_range" not in calls
    assert (out["broker"], out["server"], out["account_environment"]) == ("VT_MARKETS", "Other-Demo", "DEMO")
    assert {r["status"] for r in out["results"]} == {"BROKER_SERVER_MISMATCH"}
