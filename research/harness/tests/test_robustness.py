import math

import numpy as np
import pytest

from research.harness.ledger import load_engine_ledger
from research.harness.robustness import block_bootstrap_ci, drop_best, run_matrix
from research.harness.tests.fixtures import bars, cost_model, trade


def _ledger():
    rows = []
    for i in range(20):
        sym = "EURUSD" if i % 2 else "GBPUSD"
        month = "01" if i < 10 else "02"
        day = f"{2 + i % 9:02d}"
        rows.append(trade(i, symbol=sym, reason="TARGET" if i % 3 == 0 else "STOP",
                          entry_time=f"2024-{month}-{day}T00:00:00Z", exit_time=f"2024-{month}-{day}T02:00:00Z"))
    return load_engine_ledger(rows)


def test_matrix_sections_and_cost_monotonic():
    m = run_matrix(_ledger(), cost_model(spread=0.0001, commission=0.00005), n_boot=200)
    for k in ("baseline", "cost", "entry_delay", "leave_one_symbol_out", "leave_one_month_out",
              "drop_best", "block_bootstrap"):
        assert k in m
    assert m["cost"]["1.0x"]["total_R"] > m["cost"]["1.5x"]["total_R"] > m["cost"]["2.0x"]["total_R"]
    assert m["entry_delay"].startswith("NOT_EVALUATED")
    assert set(m["leave_one_symbol_out"]) == {"EURUSD", "GBPUSD"}
    assert set(m["leave_one_month_out"]) == {"2024-01", "2024-02"}
    assert m["leave_one_symbol_out"]["EURUSD"]["n"] == 10
    assert m["baseline"]["cost_breakdown_R"]["spread_R"] == pytest.approx(20 * 0.1)


def test_entry_delay_uses_bars():
    lg = load_engine_ledger([trade(1, entry_time="2024-01-02T00:00:00Z", exit_time="2024-01-02T00:30:00Z")])
    b = bars(n=6, rows=[(1.1, 1.1003, 1.0997, 1.1)] * 5 + [(1.1, 1.1025, 1.0999, 1.102)])
    m = run_matrix(lg, cost_model(), bars_by_symbol={"EURUSD": b}, n_boot=50)
    assert m["entry_delay"]["1_bar"]["n"] == 1 and m["entry_delay"]["1_bar"]["total_R"] == pytest.approx(2.0)
    assert m["entry_delay"]["2_bar"]["skipped_no_valid_fill"] == 0


def test_drop_best_counts():
    x = list(range(100))
    assert drop_best(x, 0.01)["dropped"] == 1 and drop_best(x, 0.10)["n"] == 90
    assert drop_best(x, 0.05)["total_R"] == sum(range(95))
    assert drop_best([5.0, 1.0, -1.0], 0.01)["dropped"] == 1  # ceil: always drops >= 1


def test_block_bootstrap_deterministic_and_brackets_mean():
    x = np.random.default_rng(1).normal(0.1, 1.0, 300)
    a, b = block_bootstrap_ci(x, n_boot=500, seed=7), block_bootstrap_ci(x, n_boot=500, seed=7)
    assert a == b and a["block"] == math.ceil(300 ** (1 / 3))
    assert a["ci_low"] < a["mean_R"] < a["ci_high"]
    assert block_bootstrap_ci([1.0])["ci_low"] is None
