import ast
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BASE = "1a8e7c5d922ba48423dca1b7858f8895afe0d66f"
FORBIDDEN_IMPORTS = (
    "MetaTrader5", "mt5", "src.mt5", "execution.mt5_gateway",
    "mt5.management_gateway", "apps.owner_edge",
)


def python_files(directory):
    return sorted(path for path in (ROOT / directory).rglob("*.py") if path.is_file())


def imported_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_contracts_have_no_broker_mt5_or_runtime_imports():
    for path in python_files("packages/contracts"):
        names = imported_names(path)
        assert not [name for name in names if any(name == item or name.startswith(item + ".") for item in FORBIDDEN_IMPORTS)]


def test_strategy_control_and_ai_shells_have_no_mutation_dependencies():
    for directory in ("packages/strategy-core", "apps/control-api", "apps/web"):
        for path in python_files(directory):
            names = imported_names(path)
            assert not [name for name in names if any(name == item or name.startswith(item + ".") for item in FORBIDDEN_IMPORTS)]


def test_future_new_order_mutation_owner_is_only_designated_as_owner_edge():
    adr = (ROOT / "docs/architecture/AG_EDGE_AI_RUNTIME_V1_FOUNDATION_ADR.md").read_text(encoding="utf-8")
    edge = (ROOT / "apps/owner-edge/README.md").read_text(encoding="utf-8")
    assert "Owner Edge (future)" in adr
    assert "sole designated target boundary for new-order broker" in edge
    assert "AI has zero broker authority" in adr


def test_production_runtime_and_authority_files_match_frozen_base():
    protected = [
        "src", "scripts", "web", "strategies", "config", "scheduler",
        "src/owner_decision", "src/execution", "src/mt5",
    ]
    result = subprocess.run(
        ["git", "diff", "--quiet", BASE, "--", *protected],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr or "protected runtime/authority files differ from migration base"


def test_broker_mutation_call_sites_equal_frozen_base():
    patterns = r"\.(order_check|order_send)\("
    baseline = subprocess.run(
        ["git", "grep", "-nE", patterns, BASE, "--", "src/execution", "src/mt5"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    current = subprocess.run(
        ["git", "grep", "-nE", patterns, "--", "src/execution", "src/mt5"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert baseline.returncode in (0, 1)
    assert current.returncode in (0, 1)
    normalize = lambda lines, has_revision: "\n".join(
        line.split(":", 1)[1] if has_revision else line for line in lines.splitlines()
    )
    assert normalize(current.stdout, False) == normalize(baseline.stdout, True)
    assert {line.split(":", 1)[0] for line in current.stdout.splitlines()} == {
        "src/execution/mt5_gateway.py", "src/mt5/management_gateway.py",
    }
