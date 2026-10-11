"""AGP-4H-C: detection-only EURUSD fixture, causality, and oracle classification."""
from research_external.oracles.lsmc_detection_run import run


def test_eurusd_detection_only_l1_l6_pass_with_zero_data_and_logic_defects():
    report = run()
    gate = report["L1-L6_detection_only"]
    assert report["strategy"] == "ST_LARGE_SMC_V1@1.1.0"
    assert report["fixture_classification"] == "HOST_CAPTURED"
    assert gate["logic_verified"] is True
    assert all(gate["checks"].values())
    assert gate["mismatch_count"] == 0
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
    assert "Single-snapshot fixture" in record["verification_basis"]
    assert "a44437e" in record["verification_basis"]
    assert record["merge_gate"] == "host re-run match (AGP-4H-HOST)"
    assert "MT5 copy_rates D1 for the same dates" in record["merge_gate_detail"]
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


def test_d1_fixture_is_broker_day_aligned():
    import json
    from research_external.oracles.lsmc_detection_run import FIXTURE, _broker_day_alignment
    rows = json.loads(FIXTURE.read_text())["D1"]
    assert _broker_day_alignment(rows) is True
    # A valid D1 open at 17:00 New York is accepted across the DST offset.
    assert _broker_day_alignment([{"time_utc": "2026-06-21T21:00:00Z"}]) is True


def test_report_has_seeded_ten_difference_reviews_and_separated_bos_choch_counts():
    report = run()
    reviews = report["seeded_manual_review"]
    assert reviews["seed"] == 20261013
    assert reviews["sample_size"] == 10
    assert all(x["raw_bar_ohlc"] and x["raw_check"] and x["spec_citation"] for x in reviews["reviews"])
    assert {c["output"] for tf in report["timeframes"].values() for c in tf["comparisons"]} >= {
        "BOS", "CHOCH", "swings", "ob", "fvg", "liquidity"}
    assert report["L1-L6_detection_only"]["difference_classification"]["DATA_DEFECT"] == 0


def test_rebuilt_fixture_d1_matches_captured_h1_on_every_broker_day_boundary():
    import json
    from zoneinfo import ZoneInfo
    from research_external.oracles.lsmc_detection_run import (
        FIXTURE, HOST_SNAPSHOT, _broker_day_alignment, rebuild_broker_d1,
    )
    fixture = json.loads(FIXTURE.read_text())
    snapshot = json.loads(HOST_SNAPSHOT.read_text())
    rebuilt, edges = rebuild_broker_d1(snapshot["H1"])
    expected = {row["time_utc"]: row for row in snapshot["D1"]}
    assert len(rebuilt) == 4  # the fixture includes a 120-hour H1 slice
    assert all(expected[row["time_utc"]] == row for row in rebuilt)
    # The full host snapshot also records the owner-checked all-span result.
    assert snapshot["source"] == "VT MT5 copy_rates_range EURUSD-VIP, single snapshot"
    report = run()["data_provenance"]
    assert report["D1_complete_day_match_count"] == report["D1_snapshot_complete_days"] == 4
    assert fixture["D1"] == snapshot["D1"]
    assert _broker_day_alignment(rebuilt)
    assert edges["partial_days"] == [{
        "server_day": "2026-07-27", "open_utc": "2026-07-26T21:00:00+00:00",
        "close_utc": "2026-07-27T21:00:00+00:00", "observed_h1_bars": 21,
        "expected_h1_bars": 24, "boundary_class": "SUNDAY_OPEN_OR_CAPTURE_EDGE",
    }, {
        "server_day": "2026-08-03", "open_utc": "2026-08-02T21:00:00+00:00",
        "close_utc": "2026-08-03T21:00:00+00:00", "observed_h1_bars": 3,
        "expected_h1_bars": 24, "boundary_class": "SUNDAY_OPEN_OR_CAPTURE_EDGE",
    }]
    # Friday 17:00 NY is the omitted weekend bucket; no partial bar is fabricated.
    friday_close_empty = [x for x in edges["empty_server_days"] if x["open_utc"] == "2026-07-31T21:00:00+00:00"]
    assert friday_close_empty
    report = run()["data_provenance"]
    assert report["D1_friday_close_empty_buckets_not_filled"]
    assert all(x["time_utc"] != "2026-07-31T21:00:00Z" for x in rebuilt)
    assert all(__import__("datetime").datetime.fromisoformat(row["time_utc"].replace("Z", "+00:00")).astimezone(
        ZoneInfo("America/New_York")).strftime("%H:%M") == "17:00" for row in rebuilt)


def test_synthetic_broker_d1_bucket_crosses_2026_11_01_dst_with_25h_boundary():
    from datetime import datetime, timedelta, timezone
    from research_external.oracles.lsmc_detection_run import _broker_day_alignment, rebuild_broker_d1
    from host_evidence.symbol_metadata import server_time_to_utc, server_bar_close_utc
    start = server_time_to_utc(datetime(2026, 11, 1, 0, 0))
    first_close = server_bar_close_utc(start, timedelta(days=1))
    second_close = server_bar_close_utc(first_close, timedelta(days=1))
    times = [start + timedelta(hours=i) for i in range(25)]
    times.extend(first_close + timedelta(hours=i) for i in range(24))
    rows = [{"timestamp_utc": t.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
             "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.1} for t in times]
    rebuilt, edges = rebuild_broker_d1(rows)
    assert [row["time_utc"] for row in rebuilt] == [
        "2026-10-31T21:00:00Z", "2026-11-01T22:00:00Z"]
    assert first_close - start == timedelta(hours=25)
    assert second_close - first_close == timedelta(hours=24)
    assert _broker_day_alignment(rebuilt)
    assert [len(times)] == [49]
    assert edges["partial_days"] == []
