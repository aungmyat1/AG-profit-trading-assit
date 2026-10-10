"""AGP-4H-C: detection-only EURUSD fixture, causality, and oracle classification."""
from research_external.oracles.lsmc_detection_run import run


def test_eurusd_detection_only_l1_l6_pass_without_actionability():
    report = run()
    gate = report["L1-L6_detection_only"]
    assert report["strategy"] == "ST_LARGE_SMC_V1@1.1.0"
    assert report["fixture_classification"] == "HOST_CAPTURED_DERIVED"
    assert gate["logic_verified"] is True
    assert all(gate["checks"].values())
    assert report["actionability_evaluated"] is False
    assert all(tf["prefix_diffs"] == [] for tf in report["timeframes"].values())


def test_every_sm_conformance_difference_is_classified_with_spec_citation():
    report = run()
    comparisons = [c for tf in report["timeframes"].values() for c in tf["comparisons"]]
    assert comparisons
    assert all(c["classification"] == "DEFINITION_DIFF" and c["spec_citation"] for c in comparisons)
    assert report["L1-L6_detection_only"]["difference_classification"]["LOGIC_DEFECT"] == 0
    assert report["L1-L6_detection_only"]["difference_classification"]["DATA_DEFECT"] == 0


def test_registry_records_only_eurusd_detection_verdict():
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    record = yaml.safe_load((root / "strategies/registry.yaml").read_text())["strategies"]["ST_LARGE_SMC_V1"]["detection_logic_verification"]
    assert record["status"] == "LOGIC_VERIFIED"
    assert record["identity"] == "ST_LARGE_SMC_V1@1.1.0/EURUSD/DETECTION_ONLY"
    assert "actionability is a separate layer" in record["scope"]
