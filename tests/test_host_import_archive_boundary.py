"""C11 host-import quarantine: reference bytes cannot become runtime dependencies."""
from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = REPO_ROOT / "archive" / "host_import"
EVIDENCE = REPO_ROOT / "status" / "evidence" / "host_c11_inventory_2026-10-11.json"
MODULE_ROOTS = tuple(REPO_ROOT / name for name in ("src", "scripts", "tests"))
SKIP_PARTS = {".git", "node_modules", ".venv", "__pycache__"}


def _python_modules():
    return [
        path
        for root in MODULE_ROOTS
        for path in root.rglob("*.py")
        if not (set(path.parts) & SKIP_PARTS)
    ]


def _is_archived_host_import(name: str | None) -> bool:
    return bool(name) and (name == "archive.host_import" or name.startswith("archive.host_import."))


def _imports_archived_host_code(path: Path) -> bool:
    """Statically catch direct and common dynamic imports without importing a module."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_archived_host_import(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if _is_archived_host_import(node.module):
                return True
            if node.module == "archive" and any(alias.name == "host_import" for alias in node.names):
                return True
        elif isinstance(node, ast.Call) and node.args:
            func = node.func
            dynamic_import = (
                isinstance(func, ast.Name) and func.id in {"__import__", "import_module"}
            ) or (
                isinstance(func, ast.Attribute) and func.attr == "import_module"
            )
            target = node.args[0]
            if dynamic_import and isinstance(target, ast.Constant) and _is_archived_host_import(target.value):
                return True
    return False


def _deployment_definition_files():
    """Installers, task definitions and MCP manifests are the only deployment readers in scope."""
    files = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or set(path.parts) & SKIP_PARTS or ARCHIVE_ROOT in path.parents:
            continue
        lower_name = path.name.lower()
        relative = path.relative_to(REPO_ROOT).as_posix()
        if (
            lower_name == ".mcp.json"
            or relative == ".vscode/tasks.json"
            or any(token in lower_name for token in ("install", "task", "schedule"))
        ):
            files.append(path)
    return sorted(files)


def test_host_import_is_archive_only_and_evidence_is_retained():
    assert ARCHIVE_ROOT.is_dir()
    assert EVIDENCE.is_file(), "C11 inventory evidence must remain tracked outside the archive"
    assert not (REPO_ROOT / "src" / "host_import").exists()
    assert not list(ARCHIVE_ROOT.rglob("__init__.py")), "archive bytes must not form Python packages"


def test_no_runtime_module_imports_archived_host_code():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_modules()
        if _imports_archived_host_code(path)
    ]
    assert not offenders, f"archive/host_import is reference-only; imports found in: {offenders}"


def test_deployment_definitions_never_reference_archived_eas_or_binaries():
    artifacts = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in ARCHIVE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".mq5", ".ex5"}
    )
    assert artifacts, "the C11 archive must retain the imported EA source evidence"

    tokens = {token for artifact in artifacts for token in (artifact, Path(artifact).name)}
    offenders = {}
    for definition in _deployment_definition_files():
        text = definition.read_text(encoding="utf-8", errors="replace").replace("\\", "/")
        found = sorted(token for token in tokens if token in text)
        if found:
            offenders[str(definition.relative_to(REPO_ROOT))] = found
    assert not offenders, f"deployment definitions reference archived order-capable artifacts: {offenders}"
