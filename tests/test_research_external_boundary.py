"""AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 architectural boundary test.

Production code (`src/`) must never depend on research candidates. This test statically
scans every `.py` file under `src/` for any import that reaches into
`research_external` (the Candidate Factory's home, per this mission's research boundary
rule) and fails the build if one exists. It does not execute any module; it only parses
import statements, so it cannot be bypassed by making the import conditional at runtime.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _imports_research_external(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "research_external":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "research_external":
                return True
    return False


def test_no_src_file_imports_research_external():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in SRC_ROOT.rglob("*.py")
        if _imports_research_external(p)
    ]
    assert not offenders, (
        "Production code under src/ must never import research_external/ "
        f"(research-only Candidate Factory home). Offending files: {offenders}"
    )


def test_src_root_exists():
    # Guards against the scan above silently passing because SRC_ROOT doesn't exist.
    assert SRC_ROOT.is_dir()
    assert any(SRC_ROOT.rglob("*.py"))
