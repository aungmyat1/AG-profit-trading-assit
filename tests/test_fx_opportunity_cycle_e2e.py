"""AG_FX_OPPORTUNITY_PROPOSAL_SLICE_V1 — clean-clone E2E acceptance (Phase 8).

Six golden scenarios (EURUSD/GBPUSD/USDJPY × ASIAN_LONDON/LONDON_NEWYORK),
each proving the full capability-zero cycle:

    read-only market data acquired -> session classified -> opportunity
    evaluated -> eligibility evaluated -> proposal produced -> dedup
    deterministic -> ledger persistence deterministic -> owner-readable
    output generated, and BROKER CALLS = 0 / order_check = 0 / order_send = 0
    / Demo = 0 / Live = 0.

The FakeMT5 double replaces the `MetaTrader5` module reference inside the
REAL restored modules (mt5.connection / mt5.market_data), so the production
code paths run for real; only the terminal boundary is faked. Broker-mutating
APIs are tripwires that raise AssertionError the moment anything reaches them.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "run_fx_opportunity_cycle", ROOT / "scripts" / "run_fx_opportunity_cycle.py"
)
cli = importlib.util.module_from_spec(_spec)
sys.modules["run_fx_opportunity_cycle"] = cli
_spec.loader.exec_module(cli)

from mt5 import connection as mt5_connection  # noqa: E402
from mt5 import market_data as mt5_market_data  # noqa: E402
from proposal_envelope.ledger import ProposalLedger  # noqa: E402

UTC = timezone.utc
DAY = date(2026, 9, 23)
ALLOWED_MT5_CALLS = {
    "initialize", "shutdown", "terminal_info", "symbol_info", "symbol_select",
    "copy_rates_range", "copy_rates_from_pos", "symbol_info_tick", "last_error",
}


# --------------------------------------------------------------------- fake MT5
class FakeMT5:
    """Read-only MT5 terminal double. Records every call; order/deal/position
    APIs are AssertionError tripwires (capability-zero proof)."""

    def __init__(self, bars):
        self.bars = sorted(bars, key=lambda b: b["time"])
        self.calls: list[str] = []

    def _rec(self, name):
        self.calls.append(name)

    # -- lifecycle / metadata (read-only) --------------------------------------
    def initialize(self, *args, **kwargs):
        self._rec("initialize")
        return True

    def shutdown(self):
        self._rec("shutdown")

    def terminal_info(self):
        self._rec("terminal_info")
        return SimpleNamespace(trade_allowed=False, connected=True)

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        self._rec("symbol_info")
        return SimpleNamespace(visible=True, name=symbol)

    def symbol_select(self, symbol, enable):
        self._rec("symbol_select")
        return True

    def symbol_info_tick(self, symbol):
        self._rec("symbol_info_tick")
        return SimpleNamespace(bid=0.0, ask=0.0)

    # -- market data (read-only) ----------------------------------------------
    def copy_rates_range(self, symbol, timeframe, start_epoch, end_epoch):
        self._rec("copy_rates_range")
        return [dict(b) for b in self.bars if start_epoch <= b["time"] < end_epoch]

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self._rec("copy_rates_from_pos")
        return [dict(b) for b in self.bars[-count:]] if count else []

    # -- broker-mutation tripwires ---------------------------------------------
    def order_send(self, *args, **kwargs):
        raise AssertionError("order_send reached -- BROKER MUTATION in capability-zero path")

    def order_check(self, *args, **kwargs):
        raise AssertionError("order_check reached -- order validation in capability-zero path")

    def positions_get(self, *args, **kwargs):
        raise AssertionError("positions_get reached -- account-state access in capability-zero path")

    def history_deals_get(self, *args, **kwargs):
        raise AssertionError("history_deals_get reached -- account-state access in capability-zero path")


# ------------------------------------------------------------ candle generators
def _bar(t, o, h, l, c):
    return {"time": int(t.timestamp()), "open": o, "high": h, "low": l, "close": c, "tick_volume": 100.0}


def _session_bars(start_hour, count, base, amp):
    out = []
    for i in range(count):
        t = datetime(DAY.year, DAY.month, DAY.day, start_hour, 0, tzinfo=UTC) + timedelta(minutes=15 * i)
        frac = (i % 8) / 7.0
        mid = base + (frac - 0.5) * 2 * amp * 0.6
        o, c = mid - amp * 0.10, mid + amp * 0.10
        out.append(_bar(t, o, max(o, c) + amp * 0.05, min(o, c) - amp * 0.05, c))
    return out


def _trade_bars(start_hour, count, box_low, box_high, sweep_at=2):
    out = []
    for i in range(count):
        t = datetime(DAY.year, DAY.month, DAY.day, start_hour, 0, tzinfo=UTC) + timedelta(minutes=15 * i)
        if i == sweep_at:
            o, c = box_low + 10e-4, box_low + 5e-4
            out.append(_bar(t, o, o + 2e-4, box_low - 10e-4, c))
        else:
            o, c = box_low + 8e-4, box_low + 10e-4
            out.append(_bar(t, o, o + 3e-4, o - 3e-4, c))
    return out


SYMBOL_BASES = {"EURUSD": (1.1000, 0.0015), "GBPUSD": (1.3100, 0.0020), "USDJPY": (150.00, 0.20)}
PAIR_WINDOWS = {
    "ASIAN_LONDON": dict(ref_hour=0, ref_bars=24, trade_hour=7, trade_bars=16, as_of="2026-09-23T11:00:00+00:00"),
    "LONDON_NEWYORK": dict(ref_hour=6, ref_bars=20, trade_hour=12, trade_bars=12, as_of="2026-09-23T15:00:00+00:00"),
}


def _fake_for(symbol: str) -> FakeMT5:
    """One coherent trading day per symbol:

    00:00-06:00  Asian reference box          (ASIAN_LONDON reference)
    06:00-11:00  London bars, ONE sweep of the ASIAN box low at 07:30
                 (serves as: LONDON_NEWYORK reference box + ASIAN_LONDON
                  trade window -- the 07:00-11:00 subset)
    12:00-15:00  NY bars, ONE sweep of the LONDON box low at 12:30
                 (LONDON_NEWYORK trade window)
    """
    base, amp = SYMBOL_BASES[symbol]
    asian = _session_bars(0, 24, base, amp)
    asian_low, asian_high = min(b["low"] for b in asian), max(b["high"] for b in asian)

    london = []
    for i in range(20):
        t = datetime(DAY.year, DAY.month, DAY.day, 6, 0, tzinfo=UTC) + timedelta(minutes=15 * i)
        if i == 6:  # 07:30 bar -- sweeps the Asian box low, closes back inside
            o, c = asian_low + 10e-4, asian_low + 5e-4
            london.append(_bar(t, o, o + 2e-4, asian_low - 10e-4, c))
        else:
            o, c = asian_low + 8e-4, asian_low + 10e-4
            london.append(_bar(t, o, o + 3e-4, o - 3e-4, c))
    london_low, london_high = min(b["low"] for b in london), max(b["high"] for b in london)

    ny = []
    for i in range(12):
        t = datetime(DAY.year, DAY.month, DAY.day, 12, 0, tzinfo=UTC) + timedelta(minutes=15 * i)
        if i == 2:  # 12:30 bar -- sweeps the London box low, closes back inside
            o, c = london_low + 10e-4, london_low + 5e-4
            ny.append(_bar(t, o, o + 2e-4, london_low - 10e-4, c))
        else:
            o, c = london_low + 8e-4, london_low + 10e-4
            ny.append(_bar(t, o, o + 3e-4, o - 3e-4, c))

    return FakeMT5(asian + london + ny)


@pytest.fixture()
def patched_mt5(monkeypatch):
    def _install(fake: FakeMT5):
        monkeypatch.setattr(mt5_connection, "mt5", fake)
        monkeypatch.setattr(mt5_market_data, "mt5", fake)
        monkeypatch.setattr(mt5_market_data, "_broker_offset_hours", lambda symbol: 0)
        return fake

    return _install


def _run(tmp_path, pair, symbol, fake_install):
    fake = fake_install(_fake_for(symbol))
    argv = [
        "--pair", pair, "--symbols", symbol,
        "--as-of", PAIR_WINDOWS[pair]["as_of"],
        "--strategy-config", str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1.yaml"),
        "--state-dir", str(tmp_path / "state"),
        "--report-dir", str(tmp_path / "reports"),
    ]
    exit_code = cli.main(argv)
    summary = json.loads((tmp_path / "reports" / f"{pair}_{DAY.isoformat()}" / "cycle_summary.json").read_text())
    return exit_code, summary, fake, tmp_path


# =============================================================== golden scenarios
@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD", "USDJPY"])
@pytest.mark.parametrize("pair", ["ASIAN_LONDON", "LONDON_NEWYORK"])
def test_full_cycle_proposal_deterministic(tmp_path, patched_mt5, pair, symbol):
    """All eight Phase-8 proofs for one golden sweep scenario."""
    exit_code, summary, fake, base = _run(tmp_path, pair, symbol, patched_mt5)

    # (1) cycle ran to an explicit terminal outcome
    assert exit_code == 0, summary
    assert len(summary["cycles"]) == 1
    cycle = summary["cycles"][0]
    assert cycle["symbol"] == symbol
    assert cycle["status"] == "PROPOSAL_RECORDED", cycle

    # (2) market data acquired through the read-only surface only
    assert "copy_rates_range" in fake.calls
    assert set(fake.calls) <= ALLOWED_MT5_CALLS, sorted(set(fake.calls) - ALLOWED_MT5_CALLS)

    # (3) session classified / opportunity evaluated (funnel reached ENTRY_CONFIRMED)
    assert cycle["stage"] == "ENTRY_CONFIRMED"
    assert cycle["outcome"] == "ACTIVE"

    # (4) eligibility evaluated -> ELIGIBLE via the audited authority
    assert cycle["eligibility_status"] == "ELIGIBLE"

    # (5) proposal produced with capability-zero governance, deterministic identity
    assert cycle["envelope_id"].startswith("OPP:ST_ASIAN_SWEEP_5R_V1:")
    assert cycle["execution_authority"] == "NONE"
    assert cycle["proposal_only"] is True

    # (6) owner-readable output generated
    report_dir = base / "reports" / f"{pair}_{DAY.isoformat()}"
    ticket_path = report_dir / f"{cycle['envelope_id'].replace(':', '_')}.txt"
    ticket = ticket_path.read_text()
    assert "NOT AN ORDER, NOT AUTHORIZATION" in ticket
    assert "execution_authority  : NONE" in ticket
    assert symbol in ticket

    # (7)+(8) dedup + ledger persistence deterministic across a full re-run
    state = base / "state"
    ledger_bytes_after_first = (state / "proposal_ledger.json").read_bytes()
    store_bytes_after_first = (state / "fx_candidate_store.json").read_bytes()
    exit_code_2, summary_2, fake_2, _ = _run(tmp_path, pair, symbol, patched_mt5)
    assert exit_code_2 == 0
    cycle_2 = summary_2["cycles"][0]
    assert cycle_2["status"] == "PROPOSAL_RECORDED"
    assert cycle_2["envelope_id"] == cycle["envelope_id"]  # deterministic identity
    assert cycle_2["candidate_id"] == cycle["candidate_id"]
    assert (state / "proposal_ledger.json").read_bytes() == ledger_bytes_after_first  # byte-stable
    assert (state / "fx_candidate_store.json").read_bytes() == store_bytes_after_first  # no revision pollution
    ledger = ProposalLedger(str(state / "proposal_ledger.json"))
    assert len(ledger.list_active_proposals()) == 1  # dedup: exactly one record

    # capability counters (tripwires prove order_* never even resolved)
    assert "order_send" not in fake.calls and "order_check" not in fake.calls
    assert "order_send" not in fake_2.calls and "order_check" not in fake_2.calls


# =============================================================== explicit outcomes
def test_watch_when_session_not_closed(tmp_path, patched_mt5):
    fake = patched_mt5(_fake_for("EURUSD"))
    exit_code = cli.main([
        "--pair", "ASIAN_LONDON", "--symbols", "EURUSD",
        "--as-of", "2026-09-23T03:00:00+00:00",
        "--strategy-config", str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1.yaml"),
        "--state-dir", str(tmp_path / "state"), "--report-dir", str(tmp_path / "reports"),
    ])
    assert exit_code == 2
    summary = json.loads(
        (tmp_path / "reports" / f"ASIAN_LONDON_{DAY.isoformat()}" / "cycle_summary.json").read_text()
    )
    cycle = summary["cycles"][0]
    assert cycle["status"] == "WATCH"
    assert cycle["reason_codes"] == ["SESSION_NOT_CLOSED"]
    assert not (tmp_path / "state" / "proposal_ledger.json").exists()  # nothing persisted


def test_data_error_when_market_data_missing(tmp_path, patched_mt5):
    fake = patched_mt5(FakeMT5([]))  # terminal answers, no bars
    exit_code = cli.main([
        "--pair", "ASIAN_LONDON", "--symbols", "EURUSD",
        "--as-of", PAIR_WINDOWS["ASIAN_LONDON"]["as_of"],
        "--strategy-config", str(ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1.yaml"),
        "--state-dir", str(tmp_path / "state"), "--report-dir", str(tmp_path / "reports"),
    ])
    assert exit_code == 2
    summary = json.loads(
        (tmp_path / "reports" / f"ASIAN_LONDON_{DAY.isoformat()}" / "cycle_summary.json").read_text()
    )
    cycle = summary["cycles"][0]
    assert cycle["status"] == "DATA_ERROR"
    assert cycle["reason_codes"], "data error must carry explicit reason codes"
    assert "DATA_MISSING" in cycle["reason_codes"][0] or "INSUFFICIENT" in cycle["reason_codes"][0]
    assert not (tmp_path / "state" / "fx_candidate_store.json").exists()  # no candidate invented


def test_replay_or_synthetic_mode_can_never_be_fabricated():
    """The CLI's event view hard-codes REAL and derives everything else from
    the bar the read-only feed returned -- there is no mode parameter to forge."""
    from strategy_engine.session.candles import Candle

    view = cli._ClosedBarView(
        candle=Candle(time=datetime(2026, 9, 23, 10, 45, tzinfo=UTC), open=1.0, high=1.1, low=0.9, close=1.05),
        symbol="EURUSD",
    )
    assert view.market_data_mode == "REAL"
    assert view.is_closed is True
    # deterministic fingerprint: same bar -> same fingerprint, always
    view2 = cli._ClosedBarView(
        candle=Candle(time=datetime(2026, 9, 23, 10, 45, tzinfo=UTC), open=1.0, high=1.1, low=0.9, close=1.05),
        symbol="EURUSD",
    )
    assert view.fingerprint == view2.fingerprint
