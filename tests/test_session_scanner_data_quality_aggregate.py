"""Regression coverage for Scanner V1 aggregate data-quality gating."""
from __future__ import annotations

from session_scanner import scanner as scanner_module
from session_scanner.quality import INVALID, STALE, VALID, SeriesQuality, fetch_with_sync
from session_scanner.timebase import TIME_GATE_PASS

SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
TIMEFRAMES = ("D1", "H1", "M15", "M5")


def _live_valid_fixture() -> dict:
    return {
        "time": {"time_gate": TIME_GATE_PASS},
        "instruments": [
            {"canonical_symbol": symbol, "data_quality_gate": "PASS",
             "data_quality": {tf: {"status": "VALID"} for tf in TIMEFRAMES}}
            for symbol in SYMBOLS
        ],
    }


def _aggregate(scan: dict) -> str:
    return scanner_module._aggregate_data_quality_gate(
        scan["time"], scan["instruments"], len(SYMBOLS)
    )


def _quality(status: str) -> SeriesQuality:
    return SeriesQuality("M15", status, 0, 0, None, None, None)


def _item(symbol: str, gate: str = "PASS", **diagnostics) -> dict:
    item = {"canonical_symbol": symbol, "data_quality_gate": gate}
    item.update(diagnostics)
    return item


def test_all_valid_live_fixture_aggregates_pass():
    scan = _live_valid_fixture()
    assert all(i["data_quality_gate"] == "PASS" for i in scan["instruments"])
    assert _aggregate(scan) == "PASS"


def test_one_invalid_instrument_fails_aggregate():
    scan = _live_valid_fixture()
    scan["instruments"][2]["data_quality_gate"] = "FAIL"  # USDJPY
    assert _aggregate(scan) == "FAIL"


def test_first_bad_retry_good_uses_final_quality_for_instrument_and_aggregate():
    reads = iter(["stale", "valid"])
    statuses = {"stale": STALE, "valid": VALID}
    synced = fetch_with_sync(lambda: [next(reads)], lambda bars: _quality(statuses[bars[0]]))
    item = _item("USDJPY", synced.as_dict()["data_quality_gate"])
    scan = _live_valid_fixture()
    scan["instruments"][2] = item
    assert synced.first_read_status == STALE
    assert synced.quality.status == VALID
    assert item["data_quality_gate"] == "PASS"
    assert _aggregate(scan) == "PASS"


def test_first_bad_retry_bad_fails_instrument_and_aggregate():
    reads = iter(["stale", "invalid"])
    statuses = {"stale": STALE, "invalid": INVALID}
    synced = fetch_with_sync(lambda: [next(reads)], lambda bars: _quality(statuses[bars[0]]))
    item = _item("USDJPY", synced.as_dict()["data_quality_gate"])
    scan = _live_valid_fixture()
    scan["instruments"][2] = item
    assert synced.quality.status == INVALID
    assert item["data_quality_gate"] == "FAIL"
    assert _aggregate(scan) == "FAIL"


def test_optional_diagnostic_does_not_fail_mandatory_aggregate():
    scan = _live_valid_fixture()
    for item in scan["instruments"]:
        item["optional_diagnostic"] = {"status": "WARN", "reason": "NON_MANDATORY_OBSERVATION"}
    assert _aggregate(scan) == "PASS"


def test_missing_mandatory_instrument_fails_closed():
    scan = _live_valid_fixture()
    scan["instruments"] = scan["instruments"][:3]
    assert _aggregate(scan) == "FAIL"
