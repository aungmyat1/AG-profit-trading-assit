"""AGP-LANE-B3 (owner ruling 2026-10-11, item 2): the open-bar guard stays a wrapper, and no production path
calls the frozen crypto_cfd_contract.rules.evaluate except through it.

Static: every module under src/ and scripts/ is parsed; any import of rules.evaluate, or any `.evaluate`
call on a name bound to crypto_cfd_contract.rules, is a bypass unless allow-listed below with a reason.
Runtime: rules.evaluate is wrapped so that a call from anywhere but guard.evaluate fails, then the production
ticket path (v1_tickets.crypto_cfd) and the replay engine run on a recorded instant.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import crypto_cfd_contract  # noqa: E402
from crypto_cfd_contract import guard, rules  # noqa: E402

RULES_MOD = "crypto_cfd_contract.rules"
ALLOWED = {
    "src/crypto_cfd_contract/guard.py": "the open-bar guard wrapper itself",
    # Frozen research candidate CRYPTO_CFD_C001: outcome-defining file pinned by sha256 in
    # research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json (cannot change without a new candidate).
    # Offline edge-discovery backtest, not a scan/ticket path; it hands rules.evaluate closed slices only.
    "src/edge_discovery/replay_c001.py": "frozen C001 research replay (sha256-pinned), not a production path",
}


def _bypasses(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    in_pkg = path.parent.name == "crypto_cfd_contract"
    rules_names, hits = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = ("crypto_cfd_contract." if in_pkg and node.level else "") + (node.module or "")
            mod = mod.rstrip(".") or ("crypto_cfd_contract" if in_pkg and node.level else "")
            for a in node.names:
                if mod == RULES_MOD and a.name in ("evaluate", "*"):
                    hits.append(f"{node.lineno}: from {mod} import {a.name}")
                if mod == "crypto_cfd_contract" and a.name == "rules":
                    rules_names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == RULES_MOD:
                    rules_names.add(a.asname or a.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "evaluate":
            target = ast.unparse(node.value)
            if target in rules_names:
                hits.append(f"{node.lineno}: {target}.evaluate")
    return hits


def test_no_production_module_bypasses_the_guard():
    found = {}
    for path in sorted([*ROOT.glob("src/**/*.py"), *ROOT.glob("scripts/**/*.py")]):
        rel = path.relative_to(ROOT).as_posix()
        hits = _bypasses(path)
        if hits and rel not in ALLOWED:
            found[rel] = hits
    assert found == {}


def test_allow_list_is_exact_and_pinned():
    for rel in ALLOWED:
        assert _bypasses(ROOT / rel), f"{rel} no longer calls rules.evaluate; drop it from ALLOWED"
    freeze = json.loads((ROOT / "research/edge_discovery/candidates/CRYPTO_CFD_C001.freeze.json").read_text())
    pinned = freeze["outcome_defining_file_sha256"]["src/edge_discovery/replay_c001.py"]
    assert hashlib.sha256((ROOT / "src/edge_discovery/replay_c001.py").read_bytes()).hexdigest() == pinned


def test_scanner_detects_a_planted_bypass(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from crypto_cfd_contract import rules as r\nx = r.evaluate('BTCUSD', None, [], [], [])\n"
                   "from crypto_cfd_contract.rules import evaluate\n", encoding="utf-8")
    assert len(_bypasses(bad)) == 2


def test_public_entry_point_is_the_guard():
    assert crypto_cfd_contract.evaluate is guard.evaluate


def test_runtime_every_rules_call_comes_from_the_guard(monkeypatch):
    import scripts.ccfd_sweep_retest_replay as R
    from v1_tickets import crypto_cfd

    real, calls = rules.evaluate, []

    def checked(*a, **kw):
        caller = sys._getframe(1)
        assert caller.f_code is guard.evaluate.__code__, f"rules.evaluate bypass from {caller.f_code.co_filename}"
        calls.append(1)
        return real(*a, **kw)
    monkeypatch.setattr(rules, "evaluate", checked)
    data = R.load_symbol("BTCUSD")
    now = dt.datetime(2026, 10, 9, 14, 0, tzinfo=dt.timezone.utc)      # inside the WEEKDAY crypto window
    ticket = crypto_cfd.build_crypto_cfd_cycle("BTCUSD", now, feed=R.ReplayFeed(data, now), balance=None)
    assert ticket["engine_result"] is not None
    n_ticket = len(calls)
    from market_structure.config import load_market_structure_config
    counts = {"D1": 50, "H1": 100, "M15": 96, "M5": 576}
    R.engine("BTCUSD", now, R.closed_inputs(data, now, counts), load_market_structure_config())
    assert n_ticket >= 1 and len(calls) > n_ticket
