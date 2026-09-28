"""AG_FX_OPPORTUNITY_PLATFORM_V2 P4: execution containment for the whole platform.

Invariant: BROKER_ORDER_CHECK_CALLS = BROKER_ORDER_SEND_CALLS = OTHER_EXECUTION_MUTATIONS = 0,
proven statically (imports/calls), in a fresh interpreter (transitive imports) and at
runtime (three pairs x both cycles x every phase with MT5 mutation APIs trapped).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import MetaTrader5
import pytest

from fx_opportunity.scanner import load_cycle_context, scan_cycle
from opportunity.candidate_store import CandidateStore
from test_fx_opportunity_market_state import DAY, M15, at, inside, range_session, ready_bars
from test_fx_opportunity_scanner import THREE, MultiFeed

REPO = Path(__file__).resolve().parents[1]
MUTATION_APIS = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
                 "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel")
FORBIDDEN_ROOTS = ("execution", "execution_runtime", "authorization", "ticket_delivery", "notifications",
                   "proposal_envelope", "strategy_manager", "trade_management", "scheduler")
FORBIDDEN_MODULES = ("mt5.connection", "mt5.account", "mt5.management_gateway", "mt5.executor",
                     "mt5.mt5_gateway", "post_asian_pilot.proposal", "post_asian_pilot.store",
                     "post_asian_pilot.governor", "post_asian_pilot.pipeline")


def test_execution_packages_are_not_restored():
    for root in (REPO, REPO / "src"):
        for name in ("execution", "authorization", "ticket_delivery"):
            assert not (root / name).exists(), root / name


def test_platform_transitive_imports_are_capability_zero():
    code = (
        "import sys; import fx_opportunity, fx_opportunity.scanner, fx_opportunity.market_state, "
        "fx_opportunity.instruments; "
        f"roots={FORBIDDEN_ROOTS!r}; mods={FORBIDDEN_MODULES!r}; "
        "bad=[m for m in sys.modules if m.split('.')[0] in roots or m in mods]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(REPO), str(REPO / "src")]))
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _calls_and_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            yield "call", f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        elif isinstance(node, ast.Import):
            for a in node.names:
                yield "import", a.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield "import", node.module


@pytest.mark.parametrize("path", sorted((REPO / "src" / "fx_opportunity").glob("*.py"))
                         + [REPO / "scripts" / "run_fx_opportunity_once.py"], ids=lambda p: p.name)
def test_no_mutation_call_or_execution_import(path):
    for kind, name in _calls_and_imports(path):
        if kind == "call":
            assert name not in MUTATION_APIS, (path.name, name)
        else:
            assert name.split(".")[0] not in FORBIDDEN_ROOTS and name not in FORBIDDEN_MODULES, (path.name, name)


def test_runtime_zero_broker_mutation_three_pairs_both_cycles(monkeypatch, tmp_path):
    calls = []
    for name in MUTATION_APIS:
        monkeypatch.setattr(MetaTrader5, name, lambda *a, _n=name, **k: calls.append(_n), raising=False)
    store = CandidateStore(str(tmp_path / "c.json"))
    asian = MultiFeed({s: ready_bars(s) for s in THREE})
    london = MultiFeed({s: range_session(s, at(6), 20) + [inside(s, at(12) + i * M15) for i in range(12)]
                        for s in THREE})
    phases = {"POST_ASIAN": (asian, (at(5), at(6, 30), at(7, 16), at(7, 31), at(11))),
              "POST_LONDON": (london, (at(10), at(11, 30), at(12, 16), at(13, 1), at(15)))}
    statuses = set()
    for cycle, (feed, instants) in phases.items():
        ctx = load_cycle_context(cycle)
        for now in instants:
            for mode in ("REPLAY", "REAL"):
                for s in scan_cycle(ctx, THREE, trading_date=DAY, now=now, fetch_candles=feed,
                                    market_data_mode=mode, source="fixture",
                                    store=store if mode == "REPLAY" else None):
                    statuses.add(s.status)
                    assert s.summary()["trade_ticket"] == "NOT_CREATED"
                    assert s.proposal == "NO_PROPOSAL_AUTHORITY"
    assert calls == []
    assert {"OPPORTUNITY", "NO_OPPORTUNITY", "NO_COMPATIBLE_OPPORTUNITY_STRATEGY"} <= statuses
