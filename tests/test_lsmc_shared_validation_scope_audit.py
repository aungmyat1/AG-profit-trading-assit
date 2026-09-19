"""Adversarial proof that tests/_lsmc_shared_validation_scope.py's decoupling guard
discriminates correctly -- it was narrowed, not weakened
(LSMC_SHARED_VALIDATION_FREEZE_SCOPE_REMEDIATION_V1).

Case A: the real, already-committed SSC/SVOS evolution of svos_context_export.py
(commit 101488f) must NOT trip the guard, since Large-SMC's real source tree has
no import of it today -- the exact scenario this remediation exists to unblock.

Cases B/C: synthetic Large-SMC source trees that DO import svos_context_export
(via the adapter file, and via a file under src/large_smc_research/) must be
detected -- proving the guard is sensitive to the one thing it exists to catch,
not vacuously passing.
"""
from __future__ import annotations

import os

import pytest

from _lsmc_shared_validation_scope import assert_large_smc_never_imports_svos_context_export

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_case_a_real_repo_has_no_large_smc_coupling_today():
    """Real repository state: Large-SMC's adapter and research engine do not import
    svos_context_export.py, so SSC/SVOS evolving it (e.g. commit 101488f) must not
    trip this guard."""
    assert_large_smc_never_imports_svos_context_export(REPO_ROOT)


def _write_adapter(tmp_path, body: str) -> None:
    adapter_dir = tmp_path / "src" / "validation_framework" / "adapters"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "large_smc_adapter.py").write_text(body, encoding="utf-8")


def test_case_b_absolute_import_in_adapter_is_detected(tmp_path):
    _write_adapter(
        tmp_path,
        "from validation_framework.svos_context_export import build_svos_context\n",
    )
    with pytest.raises(AssertionError, match="svos_context_export"):
        assert_large_smc_never_imports_svos_context_export(str(tmp_path))


def test_case_c_import_in_research_engine_is_detected(tmp_path):
    _write_adapter(tmp_path, "# no coupling here\n")
    research_dir = tmp_path / "src" / "large_smc_research"
    research_dir.mkdir(parents=True)
    (research_dir / "engine.py").write_text(
        "from validation_framework import svos_context_export\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="svos_context_export"):
        assert_large_smc_never_imports_svos_context_export(str(tmp_path))


def test_case_d_unrelated_import_does_not_false_positive(tmp_path):
    _write_adapter(
        tmp_path,
        "from validation_framework.evaluator import evaluate_transition\n"
        "from validation_framework.lifecycle_registry import get_lifecycle_stage\n",
    )
    research_dir = tmp_path / "src" / "large_smc_research"
    research_dir.mkdir(parents=True)
    (research_dir / "engine.py").write_text(
        "from validation_framework.models import GateResult\n", encoding="utf-8",
    )
    assert_large_smc_never_imports_svos_context_export(str(tmp_path))
