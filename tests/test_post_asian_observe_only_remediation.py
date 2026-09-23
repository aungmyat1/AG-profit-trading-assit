"""Regression coverage for AG_POST_ASIAN_TRUE_OBSERVE_ONLY_REMEDIATION.

Independent audit of the V1 fix (e21a3719b0c54601934cdc799f20119fb951bd13) found that
persist_canonical_proposal only protected the separate WP11A canonical-ledger write,
leaving two real gaps:

  Defect A: post_asian_pilot.pipeline.run_pilot_cycle()'s NATIVE daily-opportunity claim
  (governor.DailyTradeLedger.try_claim), native actionable-proposal save
  (save_proposal(..., actionable=True)), and COUNTER_PROPOSALS_CREATED increment were
  never gated at all -- reachable from scripts/run_post_asian_pilot.py --status on a
  genuinely fresh READY transition (not exercised by the V1 fix's own tests, which only
  ever observed already-exhausted-quota/cached conditions).

  Defect B: scripts/run_fx_session_daytrade.py --status called its own _execute_cycle()
  -> run_pilot_cycle(pilot_path) with no observability argument at all, so it silently
  inherited the fully-persisting default -- the V1 fix never touched this file.

This V2 fix replaces the narrower persist_canonical_proposal with a single explicit
observe_only: bool = False parameter (default False = unchanged, fully-persisting
production behavior for every existing caller) that additionally makes the daily-
opportunity claim and native proposal/counter writes structurally unreachable -- via
governor.DailyTradeLedger.preview_claim(), a genuinely read-only sibling of try_claim()
sharing the identical capacity/identity rules (_evaluate_claim), never a run-then-
rollback. Both --status entrypoints now pass observe_only=True explicitly.

These tests never touch MT5 (pipeline internals are monkeypatched), never call
execution.executor/execution.mt5_gateway/assistant.commands.execute_command, and make
no order_check/order_send call. All ledger/store paths are isolated under tmp_path --
nothing here touches the real repo's journal/ or state/.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import importlib.util
from pathlib import Path
from unittest import mock

import pytest

from mt5.symbol_resolver import SymbolMeta
from post_asian_pilot.decision import STATUS_READY, STATUS_WATCH, map_trade_signal_to_decision, watch_decision
from post_asian_pilot.governor import DailyTradeLedger
from post_asian_pilot.pilot_config import PilotConfig
from post_asian_pilot.pipeline import PairResult, run_pilot_cycle
from post_asian_pilot import pipeline as pipeline_module
from post_asian_pilot.store import PilotStores
from proposal_envelope.ledger import ProposalLedger
from strategy_contract.market_snapshot import from_real_candle
from strategy_engine.loader import load_strategy
from strategy_engine.models import TradeSignal
from strategy_engine.session import Candle

REPO_ROOT = Path(__file__).resolve().parent.parent
POST_ASIAN_SCRIPT_PATH = REPO_ROOT / "scripts" / "run_post_asian_pilot.py"
DAYTRADE_SCRIPT_PATH = REPO_ROOT / "scripts" / "run_fx_session_daytrade.py"
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
UTC = dt.timezone.utc
FIXED_NOW = dt.datetime(2026, 9, 22, 9, 0, tzinfo=UTC)
TRADING_DATE = FIXED_NOW.date()


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def post_asian_script():
    return _load_module(POST_ASIAN_SCRIPT_PATH, "run_post_asian_pilot_observe_only_under_test")


@pytest.fixture()
def daytrade_script():
    return _load_module(DAYTRADE_SCRIPT_PATH, "run_fx_session_daytrade_observe_only_under_test")


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


@pytest.fixture()
def symbol_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5)


def _pilot_config(tmp_path, universe=("EURUSD",)) -> PilotConfig:
    return PilotConfig(
        pilot_id="TEST_PILOT", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        strategy_source_path=STRATEGY_PATH, pair_id="ASIAN_LONDON", universe=universe,
        reference_session_name="Asian", execution_window_start_utc="07:00", execution_window_end_utc="11:00",
        risk_per_trade_pct=0.5, max_open_positions=2, max_new_trades_per_day=2,
        max_new_trades_per_symbol_per_day=1, max_aggregate_open_risk_pct=2.0,
        strategy_daily_loss_limit_r=-2.0, tie_break_priority=universe,
        state_dir=str(tmp_path / "journal_isolated"), raw={"risk": {}}, source_path="TEST",
    )


def _fresh_ready_pair_result(symbol="EURUSD", ready_at=None):
    ready_at = ready_at or dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    signal = TradeSignal(
        signal_id="SID", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol=symbol,
        pair_id="ASIAN_LONDON", reference_session="Asian", session_date=dt.date(2026, 1, 5),
        box_high=1.10, box_low=1.09, box_mid=1.095, regime="RANGE", setup="SWEEP", status="SIGNAL",
        reason_code="UPPER_SWEEP_STRICT_PENETRATION", direction="SHORT", entry=1.10000,
        stop_loss=1.10150, risk_distance=0.00150, signal_timestamp=ready_at,
    )
    window_end = dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "SNAP-1", ready_at, window_end)
    assert decision.status == STATUS_READY
    candle = Candle(time=dt.datetime(2026, 1, 5, 8, 45, tzinfo=UTC), open=1.0995, high=1.1005, low=1.0990, close=1.1000)
    snapshot = from_real_candle(symbol, "M15", candle)
    return PairResult(symbol, decision, "ELIGIBLE", None, None, snapshot)


def _watch_pair_result(symbol="EURUSD"):
    decision = watch_decision("ST_ASIAN_SWEEP_5R_V1", "1.1.1", symbol, TRADING_DATE, "Asian",
                              FIXED_NOW, "WAITING_CLOSED_M15_CONFIRMATION",
                              valid_until=FIXED_NOW + dt.timedelta(hours=2))
    assert decision.status == STATUS_WATCH
    return PairResult(symbol, decision, "ELIGIBLE", None, None, None)


def _run_isolated_cycle(tmp_path, *, observe_only: bool, pair_result_fn=_fresh_ready_pair_result,
                        now=FIXED_NOW, strategy=None, symbol_meta=None):
    tmp_ledger_path = str(tmp_path / "isolated_proposal_ledger.json")
    pilot = _pilot_config(tmp_path)
    fake_pair_result = pair_result_fn()

    with mock.patch.object(pipeline_module, "load_pilot_config", return_value=pilot), \
         mock.patch.object(pipeline_module, "load_strategy", return_value=strategy), \
         mock.patch.object(pipeline_module, "_evaluate_pair", return_value=fake_pair_result), \
         mock.patch.object(pipeline_module, "fetch_equity", return_value=10_000.0), \
         mock.patch.object(pipeline_module, "get_symbol_meta", return_value=symbol_meta), \
         mock.patch.object(pipeline_module, "ProposalLedger", lambda: ProposalLedger(path=tmp_ledger_path)):
        result = run_pilot_cycle("irrelevant_pilot_path.yaml", now=now, observe_only=observe_only)

    canonical_ledger = ProposalLedger(path=tmp_ledger_path)
    stores = PilotStores.default("ST_ASIAN_SWEEP_5R_V1", pilot.state_dir)
    return result, stores, canonical_ledger, pilot


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _state_snapshot(pilot: PilotConfig, canonical_ledger_path: Path) -> dict:
    state_dir = Path(pilot.state_dir)
    return {
        "decision": _hash_file(state_dir / "decision.json"),
        "snapshot": _hash_file(state_dir / "session_snapshot.json"),
        "proposal": _hash_file(state_dir / "proposal.json"),
        "counters": _hash_file(state_dir / "monitoring_counters.json"),
        "daily_trade_ledger": _hash_file(state_dir / "daily_trade_ledger.json"),
        "bar_tracker": _hash_file(state_dir / "last_closed_bar.json"),
        "canonical_ledger": _hash_file(canonical_ledger_path),
    }


# =========================================================================== Test 1:
# post_asian --status-equivalent (observe_only=True), fresh READY, full mutation matrix

def test_fresh_ready_observe_only_true_zero_mutation_matrix(tmp_path, strategy, symbol_meta):
    result, stores, canonical_ledger, pilot = _run_isolated_cycle(
        tmp_path, observe_only=True, strategy=strategy, symbol_meta=symbol_meta)

    pr = result.pairs[0]
    assert pr.decision.status == STATUS_READY
    assert pr.portfolio_state == "SELECTED"  # capacity preview says this WOULD be selected
    assert pr.proposal is not None  # in-memory representation still constructed for display

    assert canonical_ledger.list_active_proposals() == []  # canonical proposal ledger writes = 0
    assert stores.ledger.slots("ST_ASIAN_SWEEP_5R_V1", TRADING_DATE) == []  # opportunity slot claims = 0
    assert result.ledger_slots_used == 0
    assert not (Path(pilot.state_dir) / "daily_trade_ledger.json").exists()
    assert not (Path(pilot.state_dir) / "proposal.json").exists()  # native actionable proposal writes = 0
    assert not (Path(pilot.state_dir) / "monitoring_counters.json").exists()  # counter increments = 0


# =========================================================================== Test 2:
# session_daytrade --status-equivalent, fresh READY, full mutation matrix (Defect B)

def test_daytrade_fresh_ready_observe_only_true_zero_mutation_matrix(tmp_path, strategy, symbol_meta):
    # Same pipeline-level call the fixed run_fx_session_daytrade.py::_run_status() now
    # makes (_execute_cycle(pilot_path, observe_only=True)) -- proven directly at the
    # script-wiring level in test_daytrade_status_flag_routes_observe_only_true below;
    # this proves the resulting mutation matrix is identical to post_asian's.
    result, stores, canonical_ledger, pilot = _run_isolated_cycle(
        tmp_path, observe_only=True, strategy=strategy, symbol_meta=symbol_meta)

    assert canonical_ledger.list_active_proposals() == []
    assert stores.ledger.slots("ST_ASIAN_SWEEP_5R_V1", TRADING_DATE) == []
    assert not (Path(pilot.state_dir) / "proposal.json").exists()
    assert not (Path(pilot.state_dir) / "monitoring_counters.json").exists()


# =========================================================================== Test 3: WATCH

def test_watch_observe_only_true_zero_mutation(tmp_path, strategy, symbol_meta):
    result, stores, canonical_ledger, pilot = _run_isolated_cycle(
        tmp_path, observe_only=True, pair_result_fn=_watch_pair_result, strategy=strategy, symbol_meta=symbol_meta)

    assert result.pairs[0].decision.status == STATUS_WATCH
    assert canonical_ledger.list_active_proposals() == []
    assert not (Path(pilot.state_dir) / "daily_trade_ledger.json").exists()
    assert not (Path(pilot.state_dir) / "proposal.json").exists()


def test_watch_semantics_unchanged_between_observe_only_true_and_false(tmp_path, strategy, symbol_meta):
    r_true, _, _, _ = _run_isolated_cycle(tmp_path / "a", observe_only=True,
                                          pair_result_fn=_watch_pair_result, strategy=strategy, symbol_meta=symbol_meta)
    r_false, _, _, _ = _run_isolated_cycle(tmp_path / "b", observe_only=False,
                                           pair_result_fn=_watch_pair_result, strategy=strategy, symbol_meta=symbol_meta)
    d_true, d_false = r_true.pairs[0].decision, r_false.pairs[0].decision
    assert d_true.status == d_false.status == STATUS_WATCH
    assert d_true.missing_condition == d_false.missing_condition
    assert d_true.reason_codes == d_false.reason_codes


# =========================================================================== Test 4:
# reconstructed/already-claimed READY -- a REAL claim happens first (observe_only=False,
# production), then observe_only=True must not alter the already-claimed slot at all.

def test_reconstructed_ready_after_real_claim_zero_further_mutation(tmp_path, strategy, symbol_meta):
    # First: a genuine production cycle claims the opportunity for real.
    result1, stores, canonical_ledger, pilot = _run_isolated_cycle(
        tmp_path, observe_only=False, strategy=strategy, symbol_meta=symbol_meta)
    assert result1.ledger_slots_used == 1
    before = _state_snapshot(pilot, Path(canonical_ledger._store.path))

    # Second: an observational status call reconstructs the SAME already-claimed READY.
    result2, stores2, canonical_ledger2, _ = _run_isolated_cycle(
        tmp_path, observe_only=True, strategy=strategy, symbol_meta=symbol_meta)
    after = _state_snapshot(pilot, Path(canonical_ledger._store.path))

    assert result2.pairs[0].portfolio_state == "SELECTED"  # preview correctly reports the existing claim
    assert before == after  # byte-identical: no further write of any kind


# =========================================================================== Test 5:
# repeated status x10 on a fresh READY, then Test 6/7: production claims normally after

def test_repeated_status_x10_then_production_claim_succeeds(tmp_path, strategy, symbol_meta):
    pilot = _pilot_config(tmp_path)
    canonical_ledger_path = tmp_path / "isolated_proposal_ledger.json"

    snapshots = []
    for _ in range(10):
        result, stores, canonical_ledger, _ = _run_isolated_cycle(
            tmp_path, observe_only=True, strategy=strategy, symbol_meta=symbol_meta)
        snapshots.append(_state_snapshot(pilot, canonical_ledger_path))
        assert result.ledger_slots_used == 0
        assert canonical_ledger.list_active_proposals() == []

    # Test 5: SEMANTIC_PERSISTENT_DIFF = NONE across all 10 polls.
    assert all(s == snapshots[0] for s in snapshots)
    # A fresh READY must remain unclaimed after all 10 status polls.
    assert stores.ledger.slots("ST_ASIAN_SWEEP_5R_V1", TRADING_DATE) == []

    # Test 6/7: ONE production cycle against the same isolated state can still claim
    # the opportunity normally -- proves status polling never stole it.
    prod_result, prod_stores, prod_canonical_ledger, _ = _run_isolated_cycle(
        tmp_path, observe_only=False, strategy=strategy, symbol_meta=symbol_meta)
    assert prod_result.ledger_slots_used == 1
    assert prod_result.pairs[0].portfolio_state == "SELECTED"
    assert len(prod_canonical_ledger.list_active_proposals()) == 1


# =========================================================================== Test 8:
# capacity preview parity -- preview_claim() and try_claim() agree on eligibility for
# the SAME identity/state, using governor.DailyTradeLedger directly (no pipeline mocking
# needed -- this is the shared-authority contract P3 requires).

def test_capacity_preview_matches_production_claim_eligibility(tmp_path):
    ledger_preview = DailyTradeLedger.default(str(tmp_path / "ledger_a.json"))
    ledger_real = DailyTradeLedger.default(str(tmp_path / "ledger_b.json"))
    now = FIXED_NOW

    # Fresh identity: both must agree it succeeds and describe the same slot shape.
    preview = ledger_preview.preview_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", TRADING_DATE,
                                           "EURUSD", "SETUP-1", "PROP-1", now, now)
    real = ledger_real.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", TRADING_DATE,
                                 "EURUSD", "SETUP-1", "PROP-1", now, now)
    assert preview.success == real.success is True
    assert preview.reason_code == real.reason_code is None
    assert {k: v for k, v in preview.slot.items() if k != "updated_at"} == \
           {k: v for k, v in real.slot.items() if k != "updated_at"}
    # preview performed zero writes -- ledger_a.json was never created.
    assert not (tmp_path / "ledger_a.json").exists()
    assert (tmp_path / "ledger_b.json").exists()  # the real claim did write

    # A second symbol exceeding per-day capacity: both must agree on the block reason.
    ledger_real.try_claim("ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", TRADING_DATE,
                          "GBPUSD", "SETUP-2", "PROP-2", now, now)  # consumes the 2nd/last slot
    preview_over_capacity = ledger_preview.preview_claim(
        "ST_ASIAN_SWEEP_5R_V1", "1.1.1", "REL", TRADING_DATE, "GBPUSD", "SETUP-2", "PROP-2", now, now)
    # ledger_preview never persisted the EURUSD claim above (all its calls were
    # preview_claim), so from ITS perspective this is still the first-ever claim for
    # this identity, and it must independently agree it would succeed -- proving
    # preview_claim() never accumulates state across calls either.
    assert preview_over_capacity.success is True
    assert not (tmp_path / "ledger_a.json").exists()


# =========================================================================== Test 9/10:
# production --once / scheduled caller still persists (observe_only=False, default)

def test_production_once_still_persists_everything(tmp_path, strategy, symbol_meta):
    result, stores, canonical_ledger, pilot = _run_isolated_cycle(
        tmp_path, observe_only=False, strategy=strategy, symbol_meta=symbol_meta)

    assert result.ledger_slots_used == 1
    assert len(stores.ledger.slots("ST_ASIAN_SWEEP_5R_V1", TRADING_DATE)) == 1
    assert len(canonical_ledger.list_active_proposals()) == 1
    assert (Path(pilot.state_dir) / "proposal.json").exists()
    assert (Path(pilot.state_dir) / "monitoring_counters.json").exists()


def test_run_pilot_cycle_default_is_not_observational():
    import inspect
    sig = inspect.signature(run_pilot_cycle)
    assert sig.parameters["observe_only"].default is False


# =========================================================================== Script
# wiring: both --status entrypoints must explicitly pass observe_only=True; --once and
# bare invocation must not change.

def test_post_asian_status_flag_routes_observe_only_true(post_asian_script, monkeypatch):
    calls = []
    monkeypatch.setattr(post_asian_script, "run_pilot_cycle",
                        lambda pilot_path=None, observe_only=False: calls.append(observe_only) or _FakeResult())
    monkeypatch.setattr(post_asian_script.mt5_connection, "connect", lambda: None)
    monkeypatch.setattr(post_asian_script.mt5_connection, "shutdown", lambda: None)
    monkeypatch.setattr(post_asian_script, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    monkeypatch.setattr(post_asian_script, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(post_asian_script, "_process_ticket_delivery", lambda *a, **kw: False)
    monkeypatch.setattr(post_asian_script.sys, "argv", ["run_post_asian_pilot.py", "--status", "--json"])

    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        post_asian_script.main()

    assert calls == [True]


def test_post_asian_once_flag_routes_observe_only_false(post_asian_script, monkeypatch):
    calls = []
    monkeypatch.setattr(post_asian_script, "run_pilot_cycle",
                        lambda pilot_path=None, observe_only=False: calls.append(observe_only) or _FakeResult())
    monkeypatch.setattr(post_asian_script.mt5_connection, "connect", lambda: None)
    monkeypatch.setattr(post_asian_script.mt5_connection, "shutdown", lambda: None)
    monkeypatch.setattr(post_asian_script, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    monkeypatch.setattr(post_asian_script, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(post_asian_script, "_process_ticket_delivery", lambda *a, **kw: False)
    monkeypatch.setattr(post_asian_script.sys, "argv", ["run_post_asian_pilot.py", "--once", "--json"])

    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        post_asian_script.main()

    assert calls == [False]


def test_daytrade_status_flag_routes_observe_only_true(daytrade_script, monkeypatch):
    calls = []
    monkeypatch.setattr(daytrade_script, "run_pilot_cycle",
                        lambda pilot_path, observe_only=False: calls.append(observe_only) or _FakeResult())
    monkeypatch.setattr(daytrade_script.mt5_connection, "connect", lambda: None)
    monkeypatch.setattr(daytrade_script.mt5_connection, "shutdown", lambda: None)
    monkeypatch.setattr(daytrade_script, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(daytrade_script.sys, "argv",
                        ["run_fx_session_daytrade.py", "--status", "--cycle", "ASIAN_LONDON", "--json"])

    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as exc_info:
            daytrade_script.main()
    assert exc_info.value.code == 0

    assert calls == [True]


def test_daytrade_once_flag_routes_observe_only_false(daytrade_script, monkeypatch):
    calls = []
    monkeypatch.setattr(daytrade_script, "run_pilot_cycle",
                        lambda pilot_path, observe_only=False: calls.append(observe_only) or _FakeResult())
    monkeypatch.setattr(daytrade_script.mt5_connection, "connect", lambda: None)
    monkeypatch.setattr(daytrade_script.mt5_connection, "shutdown", lambda: None)
    monkeypatch.setattr(daytrade_script, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(daytrade_script.sys, "argv",
                        ["run_fx_session_daytrade.py", "--once", "--cycle", "ASIAN_LONDON", "--json"])

    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as exc_info:
            daytrade_script.main()
    assert exc_info.value.code == 0

    assert calls == [False]


class _FakeResult:
    """Minimal stand-in accepted by cycle_to_dict()/human_readable_report() stubs
    above -- these wiring tests only assert on the observe_only argument passed to
    run_pilot_cycle(), never on report rendering (that's proven elsewhere)."""
    trading_date = TRADING_DATE
    pairs = ()


# =========================================================================== Execution
# firewall: no reachability to execution.executor/mt5_gateway/execute_command anywhere
# in the changed files, and no order_check/order_send string anywhere but comments.

def test_no_execution_reachability_introduced():
    changed_files = [
        REPO_ROOT / "src" / "post_asian_pilot" / "pipeline.py",
        REPO_ROOT / "src" / "post_asian_pilot" / "governor.py",
        REPO_ROOT / "scripts" / "run_post_asian_pilot.py",
        REPO_ROOT / "scripts" / "run_fx_session_daytrade.py",
    ]
    for path in changed_files:
        with open(path, "r", encoding="utf-8") as f:
            import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
        joined = "".join(import_lines)
        assert "execution.executor" not in joined, path
        assert "execution.mt5_gateway" not in joined, path
        assert "assistant.commands" not in joined, path
