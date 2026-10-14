"""B1 bypass tests: the canonical MT5 adapter is reachable only through the guarded adapter.

No scanner, Telegram callback, skill or assistant/API surface may import the adapter or the guard, or
call any broker step; importing those surfaces never loads the adapter module."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADAPTER = "demo_execution.mt5_canonical_adapter"
GUARD = "demo_execution.guarded_adapter"
SURFACES = {
    "scanner": ("src/session_scanner", "src/crypto_opportunity_scanner"),
    "telegram_callback": ("src/host_delivery", "src/telegram_delivery", "src/ticket_delivery"),
    "assistant": ("src/api", "src/services"),
}
SKILLS = (".agents/skills", ".claude/skills")
FORBIDDEN_CALLS = {"order_send", "order_check", "authorize_order_check", "authorize_order_send",
                   "record_order_checked", "record_broker_ack"}
FORBIDDEN_NAMES = {"MT5CanonicalAdapter", "GuardedCanonicalAdapter"}


def _imports(tree: ast.AST) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{alias.name}" for alias in node.names}
            out |= {alias.name for alias in node.names}
    return out


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_surface_never_imports_or_calls_the_execution_path(surface):
    hits = []
    for base in SURFACES[surface]:
        for path in sorted((REPO / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = _imports(tree)
            if names & ({ADAPTER, GUARD, "mt5_canonical_adapter", "guarded_adapter"} | FORBIDDEN_NAMES):
                hits.append(f"{path.relative_to(REPO)}: import")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                    if name in FORBIDDEN_CALLS | FORBIDDEN_NAMES:
                        hits.append(f"{path.relative_to(REPO)}:{node.lineno} calls {name}")
    assert hits == []


def test_skills_never_reference_the_adapter_or_the_guard_steps():
    needles = ("mt5_canonical_adapter", "MT5CanonicalAdapter", "GuardedCanonicalAdapter",
               "authorize_order_send", "authorize_order_check")
    hits = [f"{p.relative_to(REPO)}: {n}" for base in SKILLS for p in sorted((REPO / base).rglob("*"))
            if p.is_file() and p.suffix in (".md", ".py", ".yaml", ".yml", ".json")
            for n in needles if n in p.read_text(encoding="utf-8", errors="ignore")]
    assert hits == []


def test_no_runtime_module_imports_the_adapter():
    """Only the host orchestration (not in this repo) wires the adapter; nothing in src/ or scripts/."""
    hits = []
    for base in ("src", "scripts"):
        for path in sorted((REPO / base).rglob("*.py")):
            if path == REPO / "src/demo_execution/mt5_canonical_adapter.py":
                continue
            if _imports(ast.parse(path.read_text(encoding="utf-8"))) & {ADAPTER, "MT5CanonicalAdapter"}:
                hits.append(str(path.relative_to(REPO)))
    assert hits == []


def test_importing_the_surfaces_never_loads_the_adapter():
    modules = ["session_scanner.scanner", "host_delivery.telegram_confirm", "telegram_delivery.adapter",
               "ticket_delivery.renderer", "demo_execution"]
    code = ("import importlib, sys\n"
            f"for m in {modules!r}:\n"
            "    importlib.import_module(m)\n"
            f"print(int({ADAPTER!r} in sys.modules))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                         env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"}, check=True)
    assert out.stdout.strip().splitlines()[-1] == "0"


def test_positive_control_the_scanner_detects_an_import_and_a_call():
    tree = ast.parse("from demo_execution.mt5_canonical_adapter import MT5CanonicalAdapter\n"
                     "x.authorize_order_send()\n")
    assert ADAPTER in _imports(tree) and "MT5CanonicalAdapter" in _imports(tree)
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert calls & FORBIDDEN_CALLS == {"authorize_order_send"}
