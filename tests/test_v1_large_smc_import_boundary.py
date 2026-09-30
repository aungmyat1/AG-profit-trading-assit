"""AG V1 T4/T5: research-only import boundary for Large-SMC 1.1.0 and the restored core.

large_smc_core (byte-exact C10/C11/decision from 2b75bbf), large_smc_watch (1.1.0) and
fx_discovery must not import execution, trade_management, authorization, owner_decision,
svos, MT5 management or order gateways, notifications/Telegram or HTTP clients, and must
never call order_send/order_check/position functions."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("large_smc_core", "large_smc_watch", "fx_discovery")
FORBIDDEN_TOP = {"execution", "trade_management", "authorization", "owner_decision", "svos",
                 "notifications", "telegram", "requests", "httpx", "aiohttp", "socket", "api"}
FORBIDDEN_MODULES = {"mt5.management_gateway", "execution.mt5_gateway", "execution.executor", "MetaTrader5"}
FORBIDDEN_CALLS = {"order_send", "order_check", "positions_get", "position_close"}


@pytest.mark.parametrize("pkg", PACKAGES)
def test_static_imports_and_calls(pkg):
    for path in sorted((ROOT / "src" / pkg).glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in FORBIDDEN_TOP and n not in FORBIDDEN_MODULES, f"{path.name}: {n}"
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in FORBIDDEN_CALLS, f"{path.name} calls {name}"


def test_runtime_import_loads_no_forbidden_module():
    code = ("import sys; sys.path[:0]=['.','src'];"
            "import large_smc_core.c10_stop_policy, large_smc_core.target_model, large_smc_core.decision,"
            " large_smc_watch, fx_discovery.features;"
            # socket is loaded by the stdlib/pandas themselves; it is checked statically above.
            f"bad=[m for m in sys.modules if m.split('.')[0] in {sorted(FORBIDDEN_TOP - {'socket'})!r} or m in {sorted(FORBIDDEN_MODULES - {'MetaTrader5'})!r}];"
            "print('FORBIDDEN=' + ','.join(sorted(bad)))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert [ln for ln in out.stdout.splitlines() if ln.startswith("FORBIDDEN=")] == ["FORBIDDEN="], out.stdout


def test_restored_core_is_byte_exact_with_2b75bbf():
    for name in ("c10_stop_policy", "target_model", "decision"):
        try:
            original = subprocess.run(["git", "show", f"2b75bbf:src/large_smc_research/{name}.py"], cwd=ROOT,
                                      capture_output=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("git history for 2b75bbf not available")
        assert (ROOT / "src" / "large_smc_core" / f"{name}.py").read_bytes() == original


def test_features_is_byte_exact_blob_f16baab():
    try:
        out = subprocess.run(["git", "hash-object", "src/fx_discovery/features.py"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git not available")
    assert out == "f16baab1bf1c147a10cabe80a14a670bd8b53bc8"


def test_v107_contract_preserved_and_110_is_a_separate_file():
    import yaml
    v107 = yaml.safe_load((ROOT / "strategies" / "ST_LARGE_SMC_V1.yaml").read_text(encoding="utf-8"))
    v110 = yaml.safe_load((ROOT / "strategies" / "ST_LARGE_SMC_V1_1_1_0.yaml").read_text(encoding="utf-8"))
    assert v107["version"] == "1.0.7"
    assert v110["version"] == "1.1.0" and v110["proposal_generation_authorized"] is False
