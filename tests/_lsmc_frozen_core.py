"""Test-only helper (not collected as a test module -- leading underscore):
canonical Large-SMC-relevant projection of the shared
config/governance/strategy_lifecycle.yaml registry, for the three
`test_frozen_validation_core_unchanged_by_this_mission` regression tests in
test_large_smc_eurusd_admission_wp2.py, test_large_smc_eurusd_friction_campaign_wp3a1.py,
and test_large_smc_eurusd_friction_evidence_wp3a.py.

Why this exists (LSMC_SHARED_REGISTRY_FREEZE_SCOPE_AUDIT): those three tests originally
included the ENTIRE shared strategy_lifecycle.yaml file in a whole-file git-diff-must-
be-empty check. That file's own header documents it as a multi-strategy registry ("the
ONLY machine-readable record of a strategy's current AG-EGSVF lifecycle_stage... owns
exactly one fact per strategy"), and the introducing commit (e596507) enumerates the
actual frozen validation-core files by name in its own commit message -- this registry
file is not among them. A whole-file byte-freeze therefore over-scoped the invariant:
it incidentally blocked every OTHER strategy from ever updating its own registry entry,
not just Large SMC's. This helper narrows the check to what those tests actually need
to prove: Large SMC's OWN entry (and the one genuinely global field, schema_version)
never drifted -- while other strategies' entries remain free to evolve independently,
exactly as the registry's own documented multi-strategy design intends.
"""
from __future__ import annotations

import json
import subprocess

import yaml

LARGE_SMC_STRATEGY_ID = "ST_LARGE_SMC_V1"
REGISTRY_PATH = "config/governance/strategy_lifecycle.yaml"


def large_smc_registry_projection(repo_root: str, ref: "str | None") -> str:
    """Canonical deterministic serialization (sorted keys, no whitespace ambiguity)
    of the Large-SMC-relevant slice of the shared registry at git ref `ref` -- or the
    live working tree when `ref` is None: schema_version (the one genuinely global,
    non-per-strategy field) plus ST_LARGE_SMC_V1's own entry only."""
    if ref is None:
        with open(f"{repo_root}/{REGISTRY_PATH}", "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = subprocess.check_output(
            ["git", "show", f"{ref}:{REGISTRY_PATH}"], cwd=repo_root, text=True,
        )
    data = yaml.safe_load(raw)
    projection = {
        "schema_version": data.get("schema_version"),
        "strategies": {
            LARGE_SMC_STRATEGY_ID: (data.get("strategies") or {}).get(LARGE_SMC_STRATEGY_ID),
        },
    }
    return json.dumps(projection, sort_keys=True, separators=(",", ":"))


def assert_large_smc_registry_projection_unchanged(repo_root: str, baseline_ref: str) -> None:
    """Fail-closed equivalent of the old whole-file `git diff <ref> -- <registry> == ""`
    check, narrowed to Large SMC's own registry projection only."""
    baseline = large_smc_registry_projection(repo_root, ref=baseline_ref)
    current = large_smc_registry_projection(repo_root, ref=None)
    assert current == baseline, (
        f"ST_LARGE_SMC_V1's own lifecycle-registry projection (schema_version and/or "
        f"its own strategies entry) changed since {baseline_ref}: baseline={baseline!r} "
        f"current={current!r}"
    )
