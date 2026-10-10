"""Static dependency regression; never imports broker or delivery modules.

This checks known third-party roots, not universal import resolution: main contains
imports of absent project modules (e.g. historical_replay and assistant). Unknown
roots cannot safely be classified as PyPI dependencies from their names alone.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = {
    "MetaTrader5": "MetaTrader5", "yaml": "PyYAML", "pandas": "pandas",
    "smartmoneyconcepts": "smartmoneyconcepts", "requests": "requests",
    "fastapi": "fastapi", "uvicorn": "uvicorn", "pytest": "pytest",
    "numpy": "numpy", "httpx": "httpx", "pydantic": "pydantic", "pyarrow": "pyarrow",
    "dotenv": "python-dotenv", "matplotlib": "matplotlib",
}


def imported_roots():
    roots = set()
    for directory in ("src", "scripts", "tests"):
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots.add(node.module.split(".")[0])
    return roots


def test_known_external_imports_have_pinned_requirements():
    declared = {
        line.split("==")[0].strip().lower()
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    }
    missing = {THIRD_PARTY[root] for root in imported_roots() & THIRD_PARTY.keys()
               if THIRD_PARTY[root].lower() not in declared}
    assert not missing, f"Imported distributions missing pins: {sorted(missing)}"


def test_mt5_pin_is_windows_only_and_matches_project():
    requirements = (ROOT / "requirements.txt").read_text()
    project = (ROOT / "pyproject.toml").read_text()
    assert 'MetaTrader5==5.0.5735 ; sys_platform == "win32"' in requirements
    assert "MetaTrader5==5.0.5735; sys_platform == 'win32'" in project
