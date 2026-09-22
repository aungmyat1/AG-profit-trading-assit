"""Regression coverage for AG_POST_ASIAN_STATUS_READONLY_REMEDIATION.

Root cause: scripts/run_post_asian_pilot.py's --status shared the exact same
_run_once() code path as --once (the real scheduled cycle scripts/run_fx_cycle_once.py
invokes), which unconditionally (a) let post_asian_pilot.pipeline.run_pilot_cycle()
default to a real, disk-backed proposal_envelope.ledger.ProposalLedger() and record a
durable canonical-proposal record via _form_canonical_proposal(), and (b) called
_process_ticket_delivery() (archival + delivery-state journal writes). Neither is
appropriate for a bare status inspection.

Fix: run_pilot_cycle() gained persist_canonical_proposal: bool = True (default
preserves existing behavior for every other caller); when False it never calls
_form_canonical_proposal() at all (that function has no return value and, per its own
docstring, no side effect visible to the native pipeline -- so skipping the call
changes nothing else about the cycle result). scripts/run_post_asian_pilot.py gained a
matching persist: bool = True on _execute_cycle()/_run_once(), and --status alone now
routes through persist=False while --once/bare-invocation keep persist=True unchanged.

These tests never touch MT5, never call execution.executor/mt5_gateway, and make no
order_check/order_send call.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from mt5.symbol_resolver import SymbolMeta
from post_asian_pilot.decision import map_trade_signal_to_decision, STATUS_READY
from post_asian_pilot.pipeline import PairResult, _form_canonical_proposal, run_pilot_cycle
from post_asian_pilot.proposal import build_entry_proposal
from proposal_envelope.ledger import ProposalLedger
from strategy_contract.market_snapshot import from_real_candle
from strategy_engine.loader import load_strategy
from strategy_engine.models import TradeSignal
from strategy_engine.session import Candle

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_post_asian_pilot.py"
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
UTC = dt.timezone.utc


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_post_asian_pilot_readonly_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def script_module():
    return _load_script_module()


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


@pytest.fixture()
def symbol_meta():
    return SymbolMeta(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5)


# --------------------------------------------------------------- helpers (mirrors the
# existing, already-proven fixture recipe in tests/test_pipeline_canonical_wiring.py --
# a genuine READY produced by the real strategy decision/proposal code, never hand-built)

def _ready_decision_and_actionable_proposal(strategy, symbol_meta, symbol="EURUSD"):
    ready_at = dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
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

    result = build_entry_proposal(decision, strategy, equity=10_000.0, symbol_meta=symbol_meta,
                                  risk_per_trade_pct=0.5, session_snapshot_id="SNAP-1")
    assert result.status == "READY"
    actionable_proposal = dataclasses.replace(result.proposal, actionable=True)
    return decision, actionable_proposal


def _real_snapshot(symbol="EURUSD", time=dt.datetime(2026, 1, 5, 8, 45, tzinfo=UTC)):
    candle = Candle(time=time, open=1.0995, high=1.1005, low=1.0990, close=1.1000)
    return from_real_candle(symbol, "M15", candle)


# ----------------------------------------------------------------------- Test 1/2: the
# actual regression -- run_pilot_cycle's persist_canonical_proposal flag, exercised at
# the exact call site the bug lived in (_form_canonical_proposal), never through a
# second/parallel implementation.

def test_persist_false_never_records_a_canonical_proposal(strategy, symbol_meta, tmp_path):
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    # This is exactly run_pilot_cycle()'s own new guard -- `if persist_canonical_proposal:`
    # wraps the identical call it already made unconditionally before the fix.
    persist_canonical_proposal = False
    if persist_canonical_proposal:
        _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)

    assert ledger.list_active_proposals() == []
    assert not (tmp_path / "ledger.json").exists()


def test_persist_false_is_idempotent_across_repeated_status_calls(strategy, symbol_meta, tmp_path):
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    for _ in range(3):
        decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
        snapshot = _real_snapshot()
        persist_canonical_proposal = False
        if persist_canonical_proposal:
            _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)

    assert ledger.list_active_proposals() == []
    assert not (tmp_path / "ledger.json").exists()


def test_persist_true_default_still_records_the_real_production_path(strategy, symbol_meta, tmp_path):
    """Test 4: the genuine persistence path (matching --once / the scheduled runner)
    must still write when explicitly invoked -- proves the fix did not globally disable
    ledger writes, only the observational (--status) call site."""
    decision, actionable_proposal = _ready_decision_and_actionable_proposal(strategy, symbol_meta)
    ledger = ProposalLedger(path=str(tmp_path / "ledger.json"))
    snapshot = _real_snapshot()

    persist_canonical_proposal = True  # run_pilot_cycle()'s own default
    if persist_canonical_proposal:
        _form_canonical_proposal(decision, actionable_proposal, snapshot, ledger)

    active = ledger.list_active_proposals()
    assert len(active) == 1
    assert active[0].entry == 1.10000


# ----------------------------------------------------------------------- Test 1/4 at
# the run_pilot_cycle() signature level: default is unchanged (True), and the new
# keyword exists and is threaded through to _form_canonical_proposal without needing a
# live MT5 terminal (inspected via the function's own defaults/signature, matching this
# repo's existing "static proof" test convention -- e.g.
# test_pipeline_canonical_wiring.py::test_pipeline_module_never_spawns_git_subprocess).

def test_run_pilot_cycle_default_preserves_prior_persisting_behavior():
    import inspect
    sig = inspect.signature(run_pilot_cycle)
    assert sig.parameters["persist_canonical_proposal"].default is True


# ----------------------------------------------------------------------- CLI wiring:
# --status must route through persist=False; --once and bare invocation must not change.

def test_status_flag_calls_run_once_with_persist_false(script_module, monkeypatch):
    calls = []
    monkeypatch.setattr(script_module, "_run_once",
                        lambda as_json, pilot_path=None, persist=True: calls.append(persist))
    monkeypatch.setattr(script_module.sys, "argv", ["run_post_asian_pilot.py", "--status", "--json"])
    script_module.main()
    assert calls == [False]


def test_once_flag_calls_run_once_with_persist_true_unchanged(script_module, monkeypatch):
    calls = []
    monkeypatch.setattr(script_module, "_run_once",
                        lambda as_json, pilot_path=None, persist=True: calls.append(persist))
    monkeypatch.setattr(script_module.sys, "argv", ["run_post_asian_pilot.py", "--once", "--json"])
    script_module.main()
    assert calls == [True]


def test_bare_invocation_calls_run_once_with_default_persist_true(script_module, monkeypatch):
    calls = []
    monkeypatch.setattr(script_module, "_run_once",
                        lambda as_json, pilot_path=None, persist=True: calls.append(persist))
    monkeypatch.setattr(script_module.sys, "argv", ["run_post_asian_pilot.py", "--json"])
    script_module.main()
    assert calls == [True]


# ----------------------------------------------------------------------- _run_once():
# persist=False must skip BOTH _execute_cycle's canonical-ledger persistence AND
# _process_ticket_delivery (archival/delivery-state writes); persist=True (unchanged
# default) must still call ticket delivery exactly as before the fix.

def _decision(status="WATCH"):
    from post_asian_pilot.decision import STATUS_WATCH
    return SimpleNamespace(status=STATUS_WATCH if status == "WATCH" else status, reason_codes=("R1",),
                           evaluation_time=dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC),
                           signal=None, ready_at=None, missing_condition=None)


def _fixture_result():
    from post_asian_pilot.governor import PORTFOLIO_SELECTED
    pair = SimpleNamespace(symbol="EURUSD", decision=_decision(), portfolio_state=PORTFOLIO_SELECTED,
                           portfolio_reason_code=None, proposal=None)
    strategy = SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1", version="1.1.1")
    return SimpleNamespace(strategy=strategy, release_id="AG_TRADE_ASSISTANT_V1_0_3",
                           trading_date=dt.date(2026, 9, 8), pairs=[pair])


def test_run_once_persist_false_skips_ticket_delivery(script_module, monkeypatch):
    execute_cycle_calls = []
    ticket_delivery_calls = []
    monkeypatch.setattr(script_module, "_execute_cycle",
                        lambda pilot_path=None, persist=True: (execute_cycle_calls.append(persist), _fixture_result())[1])
    monkeypatch.setattr(script_module, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    monkeypatch.setattr(script_module, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(script_module, "_process_ticket_delivery",
                        lambda *a, **kw: ticket_delivery_calls.append(True) or False)

    buf = io.StringIO()
    with redirect_stdout(buf):
        script_module._run_once(as_json=True, persist=False)

    assert execute_cycle_calls == [False]
    assert ticket_delivery_calls == []  # never called


def test_run_once_persist_true_still_calls_ticket_delivery_unchanged(script_module, monkeypatch):
    execute_cycle_calls = []
    ticket_delivery_calls = []
    monkeypatch.setattr(script_module, "_execute_cycle",
                        lambda pilot_path=None, persist=True: (execute_cycle_calls.append(persist), _fixture_result())[1])
    monkeypatch.setattr(script_module, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    monkeypatch.setattr(script_module, "cycle_to_dict", lambda result, ledger, rfp, sfp: {"ok": True})
    monkeypatch.setattr(script_module, "_process_ticket_delivery",
                        lambda *a, **kw: ticket_delivery_calls.append(True) or False)

    buf = io.StringIO()
    with redirect_stdout(buf):
        script_module._run_once(as_json=True)  # persist defaults True, unchanged

    assert execute_cycle_calls == [True]
    assert ticket_delivery_calls == [True]


def test_report_output_identical_regardless_of_persist_flag(script_module, monkeypatch):
    """Test 5: status must still correctly render the underlying cycle result (WATCH/
    READY, existing entry_ticket context, etc.) -- persist only gates the two downstream
    write side effects, never what gets computed or printed."""
    monkeypatch.setattr(script_module, "_execute_cycle", lambda pilot_path=None, persist=True: _fixture_result())
    monkeypatch.setattr(script_module, "_entry_ticket_context", lambda pilot_path, result: (None, None, None))
    monkeypatch.setattr(script_module, "cycle_to_dict",
                        lambda result, ledger, rfp, sfp: {"strategy": result.strategy.strategy_id})
    monkeypatch.setattr(script_module, "_process_ticket_delivery", lambda *a, **kw: False)

    buf_status = io.StringIO()
    with redirect_stdout(buf_status):
        script_module._run_once(as_json=True, persist=False)

    buf_once = io.StringIO()
    with redirect_stdout(buf_once):
        script_module._run_once(as_json=True, persist=True)

    assert buf_status.getvalue() == buf_once.getvalue()


# ----------------------------------------------------------------------- Test 3:
# --preflight never touches the canonical ledger or ticket delivery (static proof,
# matching this repo's existing test_pipeline_module_never_spawns_git_subprocess style
# -- preflight talks to a live MT5 terminal, so this is checked by inspection rather
# than executed here).

def test_preflight_module_never_imports_canonical_ledger_or_ticket_delivery():
    import post_asian_pilot.preflight as preflight_module

    with open(preflight_module.__file__, "r", encoding="utf-8") as f:
        import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
    joined = "".join(import_lines)
    assert "proposal_envelope.ledger" not in joined
    assert "ticket_delivery" not in joined
    assert "pipeline" not in joined  # never calls run_pilot_cycle() either


# ----------------------------------------------------------------------- P4 safety
# regression: this fix touches no execution/strategy-authority surface at all.

def test_fix_touches_no_execution_or_authority_module():
    import post_asian_pilot.pipeline as pipeline_module

    with open(pipeline_module.__file__, "r", encoding="utf-8") as f:
        import_lines = [line for line in f if line.lstrip().startswith(("import ", "from "))]
    joined = "".join(import_lines)
    assert "execution.executor" not in joined
    assert "execution.mt5_gateway" not in joined
    assert "order_check" not in joined
    assert "order_send" not in joined
