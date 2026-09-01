"""scripts/run_strategy.py must not evaluate a non-ACTIVE registry strategy.

run_strategy.py is analysis-only (no risk sizing, no order_send) but it can still
print a signal-shaped result (direction/entry/stop_loss). Before this gate existed,
passing --strategy ST_LARGE_SMC_V1 was blocked only by an incidental config-schema
mismatch, not by a designed status check. This proves the registry gate itself.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location("run_strategy", ROOT / "scripts" / "run_strategy.py")
run_strategy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_strategy)


def test_active_strategy_is_not_blocked():
    assert run_strategy._check_registry_active("ST_ASIAN_SWEEP_5R_V1") is None


def test_research_draft_strategy_is_blocked():
    assert run_strategy._check_registry_active("ST_LARGE_SMC_V1") == "STRATEGY_NOT_ACTIVE"


def test_inactive_research_strategy_is_blocked():
    assert run_strategy._check_registry_active("SMC_3R_V1") == "STRATEGY_NOT_ACTIVE"


def test_unregistered_strategy_is_blocked():
    assert run_strategy._check_registry_active("NOT_A_REAL_STRATEGY") == "STRATEGY_NOT_REGISTERED"


def test_main_blocks_before_mt5_connect(monkeypatch, capsys):
    def _fail_connect():
        raise AssertionError("connect() must not be called for a blocked strategy")

    monkeypatch.setattr(run_strategy, "connect", _fail_connect)
    rc = run_strategy.main(["--symbol", "EURUSD", "--strategy", "ST_LARGE_SMC_V1", "--json"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "STRATEGY_NOT_ACTIVE" in out
