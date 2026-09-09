"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P16 governance tests for
scripts/generate_economic_evidence_report.py: evidence-complete != economic-pass, OOS
stays NOT_VERIFIED without genuine held-out evidence, no lifecycle promotion, no
authorization change. Loads the real script module via importlib (matches this
repo's existing pattern, e.g. tests/test_btc_daily_cli.py) so it exercises the actual
CLI-callable functions, not a reimplementation.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_report_module():
    path = ROOT / "scripts" / "generate_economic_evidence_report.py"
    spec = importlib.util.spec_from_file_location("generate_economic_evidence_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_never_declares_economic_gate_pass_without_a_signed_threshold():
    """P11: 'Use only repository/governance-defined thresholds for formal PASS ...
    Do not invent one.' No signed economic threshold exists anywhere in this
    repository (grep-verified) -- economic_gate_pass must therefore be
    ECONOMIC_GATE_THRESHOLD_UNDEFINED for every strategy, regardless of how the
    underlying metrics look."""
    module = _load_report_module()
    report = module.build_report()
    for section in ("session_trade", "large_smc", "crypto"):
        assert report[section]["economic_gate_pass"] == "ECONOMIC_GATE_THRESHOLD_UNDEFINED"


def test_oos_status_reflects_real_gate_not_fabricated():
    """P10: OOS_VALIDATION must not read PASS merely because net metrics were
    computed -- it is sourced from the real validation_framework gate, which is
    NOT_VERIFIED repository-wide (no OOS artifact exists for any of the three
    strategies)."""
    module = _load_report_module()
    report = module.build_report()
    for section in ("session_trade", "large_smc", "crypto"):
        assert report[section]["oos_status"] == "NOT_VERIFIED"


def test_evidence_complete_and_economic_pass_are_independent_fields():
    """P9: FRICTION_EVIDENCE_COMPLETE=PASS and ECONOMIC_GATE_PASS=FAIL must be a
    representable, non-contradictory combination -- session_trade has complete
    friction evidence (every resolved record has entry/stop_loss) yet its economic
    gate is still undefined/not-passing."""
    module = _load_report_module()
    report = module.build_report()
    session = report["session_trade"]
    assert session["friction_evidence_complete"] is True
    assert session["economic_gate_pass"] != "PASS"


def test_report_module_never_imports_execution_or_authorization_paths():
    source = (ROOT / "scripts" / "generate_economic_evidence_report.py").read_text(encoding="utf-8")
    forbidden = (
        "execution.executor", "execution.coordinator", "mt5.management_gateway",
        "order_send", "order_check", "demo_authorized=True", "demo_authorized = True",
        ".promote_strategy(", "authorize_demo(", "set_lifecycle_stage(",
    )
    assert not any(term in source for term in forbidden)


def test_report_is_read_only_does_not_write_any_evidence_file(tmp_path, monkeypatch):
    """Running the report generator against the real repo must not create or modify
    any file -- it only reads existing evidence and computes derived numbers."""
    module = _load_report_module()
    import os
    watched = [
        "artifacts/outcome_resolution/records",
        "journal/reports/btc",
        "journal/ticket_delivery/archive",
        "strategies/registry.yaml",
        "config/governance/strategy_lifecycle.yaml",
    ]
    before = {}
    for rel in watched:
        p = ROOT / rel
        if p.is_file():
            before[rel] = p.stat().st_mtime
        elif p.is_dir():
            before[rel] = sorted(str(f) for f in p.rglob("*") if f.is_file())
    module.build_report()
    for rel in watched:
        p = ROOT / rel
        if p.is_file():
            assert p.stat().st_mtime == before[rel]
        elif p.is_dir():
            after = sorted(str(f) for f in p.rglob("*") if f.is_file())
            assert after == before[rel]
