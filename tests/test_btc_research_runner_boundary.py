import ast
from pathlib import Path


def test_runner_uses_bybit_and_has_no_execution_submission_imports():
    source = Path("scripts/run_btc_sweep_research.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "execution_runtime.bybit_linear_perp_feed" in imports
    assert not imports & {"execution.executor", "execution.coordinator", "mt5.management_gateway"}
    assert "order_send" not in source
