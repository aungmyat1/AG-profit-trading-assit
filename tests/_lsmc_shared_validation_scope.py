"""Test-only helper (not collected as a test module -- leading underscore):
LSMC_SHARED_VALIDATION_FREEZE_SCOPE_REMEDIATION_V1.

Companion to _lsmc_frozen_core.py's LSMC_SHARED_REGISTRY_FREEZE_SCOPE_AUDIT,
applied to the same over-scoping pattern found in the
`test_frozen_validation_core_unchanged_by_this_mission` regressions in
test_large_smc_eurusd_admission_wp2.py, test_large_smc_eurusd_friction_campaign_wp3a1.py,
and test_large_smc_eurusd_friction_evidence_wp3a.py.

Those tests previously included `src/validation_framework/svos_context_export.py`
in a whole-file byte-freeze. That module (`build_svos_context`) is designed as
per-strategy shared infrastructure -- it takes `strategy_id` as a parameter --
but Large-SMC has ZERO actual coupling to it: neither `src/large_smc_research/`
nor `src/validation_framework/adapters/large_smc_adapter.py` imports it,
calls it, or reads `CONTEXT_SCHEMA_VERSION`. In practice it is exclusively
exercised by SSC/SVOS (`scripts/export_ssc_svos_context.py`). Byte-freezing
it therefore blocked SSC's own legitimate, backward-compatible evolution
(commit 101488f: additive optional kwargs + a schema_version bump) of a
module Large-SMC never reads -- the same over-scoping the registry freeze
had, just with zero shared state instead of one strategy's own registry
entry to project out.

Removing it from the byte-freeze list does not remove protection: Large-SMC's
actual observable contract (strategy identity/config via
test_strategy_semantics_files_unchanged_by_this_mission, and validation
admission/friction/gate semantics via the other 9 still-byte-frozen
validation_framework modules Large-SMC DOES import) is untouched. What
that whole-file freeze was actually reaching for -- "svos_context_export.py
can never silently start mattering to Large-SMC's contract" -- is enforced
here directly and more precisely: a decoupling guard that fails the moment
Large-SMC code starts importing it, forcing a deliberate, reviewed freeze
decision (byte-freeze it again, or design a scoped projection like the
registry's) at the moment that coupling is introduced, rather than
incidentally blocking unrelated SSC evolution forever.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Set

DECOUPLED_MODULE_LEAF = "svos_context_export"
LARGE_SMC_SOURCE_PATHS = (
    "src/large_smc_research",
    "src/validation_framework/adapters/large_smc_adapter.py",
)


def _imported_module_names(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            # `from package import submodule` -- the submodule name only shows up in
            # node.names, not node.module, so also record the joined form (matches
            # `from validation_framework import svos_context_export`).
            for alias in node.names:
                modules.add(f"{node.module}.{alias.name}")
    return modules


def assert_large_smc_never_imports_svos_context_export(repo_root: str) -> None:
    """Fail-closed: if any file under Large-SMC's own source (research engine
    or its validation-framework adapter) ever imports `svos_context_export`
    -- as `validation_framework.svos_context_export`, a relative
    `.svos_context_export`, or the bare module name -- this fails
    immediately, before any byte-level drift in that file could silently
    reach Large-SMC's contract."""
    root = Path(repo_root)
    checked_any = False
    for rel in LARGE_SMC_SOURCE_PATHS:
        target = root / rel
        paths = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for path in paths:
            checked_any = True
            imported = _imported_module_names(path)
            hit = {m for m in imported if m.rsplit(".", 1)[-1] == DECOUPLED_MODULE_LEAF}
            assert not hit, (
                f"{path} imports {hit} -- Large-SMC has started depending on "
                "svos_context_export.py, which is deliberately NOT in the "
                "Large-SMC byte-freeze set (see "
                "LSMC_SHARED_VALIDATION_FREEZE_SCOPE_REMEDIATION_V1 in this "
                "module's docstring). Re-add it to the frozen file list, or "
                "give it a scoped projection like _lsmc_frozen_core.py's "
                "registry projection, before this coupling ships."
            )
    assert checked_any, f"no Large-SMC source files found under {LARGE_SMC_SOURCE_PATHS!r} -- guard is not exercising anything"
