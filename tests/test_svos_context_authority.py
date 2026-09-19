"""Tests for the SSC SVOS context authority remediation (generator + generated artifact).

Verifies the generated `svos_context.json` accurately represents v1.0.1 authority:
candidate manifest present + post-hoc disclosure (no retroactive preregistration PASS),
HYP_001 HYPOTHESIS_NOT_SUPPORTED binding, HYP_002 pre-remediation, unsigned economic
gate, untouched holdout, forward not eligible, fail-closed missing-authority, and
generator determinism. No Route B rerun, no optimization, no protected-data access.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CTX_PATH = REPO / "artifacts" / "validation" / "ST_SESSION_SWEEP_CONTINUATION_V1" / "svos_context.json"
GENERATOR_PATH = REPO / "scripts" / "export_ssc_svos_context.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("export_ssc_svos_context", str(GENERATOR_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ctx():
    with open(CTX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_strategy_identity_v1_0_1(ctx):
    assert ctx["strategy_id"] == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert ctx["strategy_version"] == "1.0.1"
    assert ctx["svos_lifecycle_stage"] == "OFFLINE_RESEARCH"


def test_candidate_manifest_present_and_post_hoc(ctx):
    cm = ctx["candidate_manifest"]
    assert cm["present"] is True
    assert cm["retroactive_preregistration"] is False
    assert cm["post_hoc_reconstruction_disclosed"] is True
    assert cm["candidate_version"] == "1.1.0"
    assert cm["parent_version"] == "1.0.0"


def test_no_retroactive_preregistration_pass(ctx):
    assert ctx["gates"]["G1"]["status"] == "PARTIAL"


def test_hyp001_negative_result_binding(ctx):
    h = ctx["hypotheses"]["HYP_001_EXIT_CAPTURE"]
    assert h["status"] == "HYPOTHESIS_NOT_SUPPORTED"
    assert h["paired_n"] == 88
    assert h["control_runner_target_r"] == 3.0
    assert h["treatment_runner_target_r"] == 1.5
    assert h["delta_net_R"] == pytest.approx(-2.227145)
    assert h["terminal"] is False


def test_hyp002_pre_remediation(ctx):
    h = ctx["hypotheses"]["HYP_002_SETUP_SELECTIVITY"]
    assert h["status"] == "VALIDATED_NEGATIVE"
    assert h["role_relative_to_v1_0_1"] == "PRE_REMEDIATION_NON_COUNTING"
    assert h["terminal"] is True


def test_unsigned_economic_gate(ctx):
    assert ctx["economic_gate"]["status"] == "PROPOSED"
    assert ctx["economic_gate"]["signed"] is False


def test_holdout_untouched(ctx):
    assert ctx["holdout"]["sealed"] is True
    assert ctx["holdout"]["access_count"] == 0


def test_forward_not_eligible(ctx):
    assert ctx["forward"]["eligible"] is False
    assert ctx["forward"]["campaign_started"] is False


def test_no_g2_plus_pass_manufactured(ctx):
    """G0/G1 remain PARTIAL, so furthest_verified_gate stays None even though G2 is now a
    legitimate frozen-population PASS (DEV_002 POPULATION_V1); G3 remains non-PASS
    (unsigned economic-gate contract). No progress is manufactured beyond the frozen
    population itself."""
    assert ctx["furthest_verified_gate"] is None
    assert ctx["gates"]["G0"]["status"] == "PARTIAL"
    assert ctx["gates"]["G1"]["status"] == "PARTIAL"
    assert ctx["gates"]["G2"]["status"] == "PASS"
    assert ctx["g2_population"]["status"] == "POPULATION_FROZEN"
    assert ctx["gates"]["G3"]["status"] != "PASS"


def test_fail_closed_missing_authority_artifact():
    mod = _load_generator()
    with pytest.raises(FileNotFoundError):
        mod._read_json("definitely/not/a/real/artifact.json")
    with pytest.raises(FileNotFoundError):
        mod._read_yaml("definitely/not/a/real/artifact.yaml")


def test_candidate_manifest_hash_binding_reads_and_verifies():
    mod = _load_generator()
    cm = mod._read_candidate_manifest()
    assert cm["present"] is True
    assert cm["retroactive_preregistration"] is False


def test_generator_determinism():
    mod = _load_generator()
    fixed = datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc)
    c1 = json.dumps(mod.collect_context(now=fixed), sort_keys=True)
    c2 = json.dumps(mod.collect_context(now=fixed), sort_keys=True)
    assert c1 == c2
