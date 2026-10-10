"""AGP-4H-C: detection-only EURUSD fixture, causality, and oracle classification."""
from research_external.oracles.lsmc_detection_run import run


def test_eurusd_detection_checks_pass_but_host_data_gate_blocks_verdict():
    report = run()
    gate = report["L1-L6_detection_only"]
    assert report["strategy"] == "ST_LARGE_SMC_V1@1.1.0"
    assert report["fixture_classification"] == "HOST_CAPTURED_DERIVED"
    assert gate["logic_verified"] is False
    assert all(value for key, value in gate["checks"].items() if key != "D1_broker_day_alignment")
    assert gate["checks"]["D1_broker_day_alignment"] is False
    assert report["actionability_evaluated"] is False
    assert all(tf["prefix_diffs"] == [] for tf in report["timeframes"].values())


def test_every_sm_conformance_difference_is_classified_with_spec_citation():
    report = run()
    comparisons = [c for tf in report["timeframes"].values() for c in tf["comparisons"]]
    assert comparisons
    assert all(c["classification"] == "DEFINITION_DIFF" and c["spec_citation"] for c in comparisons)
    assert report["L1-L6_detection_only"]["difference_classification"]["LOGIC_DEFECT"] == 0
    assert report["L1-L6_detection_only"]["difference_classification"]["DATA_DEFECT"] == 1


def test_registry_records_only_eurusd_detection_verdict():
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    record = yaml.safe_load((root / "strategies/registry.yaml").read_text())["strategies"]["ST_LARGE_SMC_V1"]["detection_logic_verification"]
    assert record["status"] == "PENDING_HOST_RERUN_MATCH"
    assert record["candidate_detection_checks"] == "LOGIC_VERIFIED"
    assert record["identity"] == "ST_LARGE_SMC_V1@1.1.0/EURUSD/DETECTION_ONLY"
    assert "actionability is a separate layer" in record["scope"]


def test_smc_oracle_outputs_are_delayed_by_swing_length():
    from research_external.oracles.lsmc_detection_run import LENGTH, _bars, _smc_causal, FIXTURE
    import json
    data = json.loads(FIXTURE.read_text())
    output = _smc_causal(_bars(data["H1"]))
    for key in ("swings", "bos_choch", "liquidity", "ob", "fvg"):
        assert all(event[0] >= LENGTH for event in output[key])
    for key in ("adapter_fvg", "adapter_ob"):
        assert all(event[0] >= LENGTH for event in output[key])


def test_raw_smc_swing_labels_leak_future_but_wrapper_hides_unconfirmed_bookends():
    import json
    import pandas as pd
    from smartmoneyconcepts import smc
    from research_external.oracles.lsmc_detection_run import FIXTURE, LENGTH, _bars, _smc_causal
    from market_structure.smc_adapter import candles_to_dataframe
    rows = json.loads(FIXTURE.read_text())["H1"]
    bars = _bars(rows)
    full_raw = smc.swing_highs_lows(candles_to_dataframe(bars), swing_length=LENGTH)
    prefix_raw = smc.swing_highs_lows(candles_to_dataframe(bars[:LENGTH + 1]), swing_length=LENGTH)
    assert not pd.isna(full_raw.iloc[0]["HighLow"])
    assert pd.isna(prefix_raw.iloc[0]["HighLow"])
    full_causal = _smc_causal(bars)["swings"]
    leaked_bookend = (2, (('HighLow', float(full_raw.iloc[0]["HighLow"])),
                          ('Level', float(full_raw.iloc[0]["Level"]))))
    assert leaked_bookend not in full_causal
    assert all(event[0] >= LENGTH for event in full_causal)


def test_d1_fixture_is_utc_resampled_not_broker_day_aligned():
    import json
    from research_external.oracles.lsmc_detection_run import FIXTURE, _broker_day_alignment
    rows = json.loads(FIXTURE.read_text())["D1"]
    assert _broker_day_alignment(rows) is False
    # A valid D1 open at 17:00 New York is accepted across the DST offset.
    assert _broker_day_alignment([{"time_utc": "2026-06-21T21:00:00Z"}]) is True


def test_report_has_seeded_ten_difference_reviews_and_separated_bos_choch_counts():
    report = run()
    reviews = report["seeded_manual_review"]
    assert reviews["seed"] == 20261011
    assert reviews["sample_size"] == 10
    assert all(x["raw_bar_ohlc"] and x["raw_check"] and x["spec_citation"] for x in reviews["reviews"])
    assert {c["output"] for tf in report["timeframes"].values() for c in tf["comparisons"]} >= {
        "BOS", "CHOCH", "swings", "ob", "fvg", "liquidity"}
    assert report["L1-L6_detection_only"]["difference_classification"]["DATA_DEFECT"] == 1
