"""Adversarial proof that tests/_lsmc_frozen_core.py's narrowed Large-SMC registry
freeze guard discriminates correctly -- i.e. it was narrowed, not weakened
(LSMC_SHARED_REGISTRY_FREEZE_SCOPE_AUDIT, WP5).

Case A (unrelated strategy mutation) uses the real, currently-uncommitted SSC v1.0.1
version-rollover change already sitting in this working tree -- the exact real-world
scenario that originally triggered this whole audit.

Cases B/C construct a synthetic mutated registry file under a temp repo_root and
compare its projection directly against the real e596507 baseline projection, proving
the projection function itself is sensitive to a Large-SMC-entry change and to the one
genuinely global field (schema_version), not merely vacuously equal to everything.
"""
from __future__ import annotations

import json
import os

from _lsmc_frozen_core import (
    assert_large_smc_registry_projection_unchanged,
    large_smc_registry_projection,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE_REF = "e596507"


def test_case_a_unrelated_strategy_mutation_passes():
    """SSC's semantic_version changing (1.0.0 -> 1.0.1, the real uncommitted rollover
    diff currently in this working tree) must NOT trip the Large-SMC freeze guard."""
    assert_large_smc_registry_projection_unchanged(REPO_ROOT, BASELINE_REF)


def test_case_b_large_smc_entry_mutation_is_detected(tmp_path):
    """A mutated ST_LARGE_SMC_V1 entry must be detected as a real projection change."""
    baseline = large_smc_registry_projection(REPO_ROOT, ref=BASELINE_REF)
    mutated = json.loads(baseline)
    mutated["strategies"]["ST_LARGE_SMC_V1"]["semantic_version"] = "9.9.9"
    mutated_registry_yaml = (
        f'schema_version: "{mutated["schema_version"]}"\n\n'
        "strategies:\n"
        "  ST_LARGE_SMC_V1:\n"
        f'    semantic_version: "9.9.9"\n'
        f'    lifecycle_stage: {mutated["strategies"]["ST_LARGE_SMC_V1"]["lifecycle_stage"]}\n'
    )
    governance_dir = tmp_path / "config" / "governance"
    governance_dir.mkdir(parents=True)
    (governance_dir / "strategy_lifecycle.yaml").write_text(mutated_registry_yaml, encoding="utf-8")

    current = large_smc_registry_projection(str(tmp_path), ref=None)
    assert current != baseline, "a mutated ST_LARGE_SMC_V1 entry must change the projection"


def test_case_c_global_field_mutation_is_detected(tmp_path):
    """A mutated schema_version (the one genuinely global field) must be detected."""
    baseline = large_smc_registry_projection(REPO_ROOT, ref=BASELINE_REF)
    baseline_data = json.loads(baseline)
    lsmc_entry = baseline_data["strategies"]["ST_LARGE_SMC_V1"]
    mutated_registry_yaml = (
        'schema_version: "2"\n\n'
        "strategies:\n"
        "  ST_LARGE_SMC_V1:\n"
        f'    semantic_version: "{lsmc_entry["semantic_version"]}"\n'
        f'    lifecycle_stage: {lsmc_entry["lifecycle_stage"]}\n'
    )
    governance_dir = tmp_path / "config" / "governance"
    governance_dir.mkdir(parents=True)
    (governance_dir / "strategy_lifecycle.yaml").write_text(mutated_registry_yaml, encoding="utf-8")

    current = large_smc_registry_projection(str(tmp_path), ref=None)
    assert current != baseline, "a mutated schema_version must change the projection"
