"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P16 acceptance tests for
post_asian_pilot.shadow_day_classifier -- deterministic FX shadow day classification.
Uses a real tmp_path archive tree shaped exactly like
journal/ticket_delivery/archive/fx_ticket_archive/, never the live journal/ directory.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from post_asian_pilot.shadow_day_classifier import (  # noqa: E402
    EXCLUDED_DAY,
    INVALID_DAY,
    PENDING_RECONCILIATION,
    VALID_DAY,
    classify_day,
    classify_series,
)

STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_VERSION = "1.1.1"


def _unit_dir(repo_root: Path, symbol: str, cycle: str, year: int) -> Path:
    return repo_root / "journal" / "ticket_delivery" / "archive" / "fx_ticket_archive" / STRATEGY_ID / symbol / cycle / str(year)


def _write_unit(repo_root: Path, symbol: str, cycle: str, date_str: str, evaluation_time: str,
                 cycle_state: str = "WATCH", reason_codes=None):
    year = int(date_str[:4])
    d = _unit_dir(repo_root, symbol, cycle, year)
    d.mkdir(parents=True, exist_ok=True)
    record = {
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "symbol": symbol, "cycle": cycle, "trading_date": date_str,
        "cycle_state": cycle_state, "evaluation_time_utc": evaluation_time,
        "reason_codes": reason_codes or [],
        "payload": {"decision_status": cycle_state},
    }
    (d / f"{date_str}.json").write_text(json.dumps(record), encoding="utf-8")


def _write_all_four_units(repo_root: Path, date_str: str, eval_hour_asian="09:30", eval_hour_ny="13:30",
                           cycle_state="WATCH", reason_codes=None):
    for symbol in ("EURUSD", "GBPUSD"):
        _write_unit(repo_root, symbol, "ASIAN_LONDON", date_str, f"{date_str}T{eval_hour_asian}:00+00:00",
                    cycle_state=cycle_state, reason_codes=reason_codes)
        _write_unit(repo_root, symbol, "LONDON_NEWYORK", date_str, f"{date_str}T{eval_hour_ny}:00+00:00",
                    cycle_state=cycle_state, reason_codes=reason_codes)


ARCHIVE_DATE = "2026-09-09"  # Wednesday, on/after the archive-only activation date


def test_valid_day_when_all_four_units_have_legitimate_terminal_state(tmp_path):
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == VALID_DAY


def test_losing_trade_terminal_state_is_still_a_valid_day(tmp_path):
    """P4.2: classification never depends on win/loss -- a NO_TRADE/READY terminal
    state is equally valid regardless of what a later-resolved outcome would show."""
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="READY")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == VALID_DAY


def test_data_error_unit_makes_the_day_invalid(tmp_path):
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    _write_unit(tmp_path, "EURUSD", "ASIAN_LONDON", ARCHIVE_DATE, f"{ARCHIVE_DATE}T09:45:00+00:00",
                cycle_state="DATA_ERROR", reason_codes=["MISSING_CANDLE"])
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == INVALID_DAY
    assert any("DATA_ERROR" in r for r in result.classification_reasons)


def test_anomaly_reason_code_makes_the_day_invalid(tmp_path):
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    _write_unit(tmp_path, "EURUSD", "LONDON_NEWYORK", ARCHIVE_DATE, f"{ARCHIVE_DATE}T13:45:00+00:00",
                cycle_state="DATA_ERROR", reason_codes=["SNAPSHOT_IMMUTABILITY_VIOLATION"])
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == INVALID_DAY
    assert any("ANOMALY" in r for r in result.classification_reasons)


def test_weekend_is_excluded_not_invalid(tmp_path):
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date(2026, 9, 12), str(tmp_path))  # Saturday
    assert result.classification == EXCLUDED_DAY


def test_missing_unit_evidence_is_invalid_when_other_units_have_evidence(tmp_path):
    # Only 3 of 4 units evaluated.
    _write_unit(tmp_path, "EURUSD", "ASIAN_LONDON", ARCHIVE_DATE, f"{ARCHIVE_DATE}T09:30:00+00:00")
    _write_unit(tmp_path, "GBPUSD", "ASIAN_LONDON", ARCHIVE_DATE, f"{ARCHIVE_DATE}T09:30:00+00:00")
    _write_unit(tmp_path, "EURUSD", "LONDON_NEWYORK", ARCHIVE_DATE, f"{ARCHIVE_DATE}T13:30:00+00:00")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == INVALID_DAY
    assert any("MISSING_MANDATORY_EVIDENCE" in r for r in result.classification_reasons)


def test_no_evidence_at_all_is_pending_not_invalid(tmp_path):
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == PENDING_RECONCILIATION


def test_pre_archive_activation_date_is_pending_reconciliation(tmp_path):
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date(2026, 9, 3), str(tmp_path))
    assert result.classification == PENDING_RECONCILIATION
    assert "PRE_ARCHIVE_ONLY_ACTIVATION" in result.classification_reasons[0]


def test_out_of_window_correction_does_not_override_in_window_terminal_state(tmp_path):
    """The last IN-WINDOW record is authoritative; a later out-of-window scheduler
    run (the existing 24/7-repetition FX tasks) producing DATA_ERROR must not
    retroactively invalidate a day whose in-window evaluation already completed."""
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    # Out-of-window (after LONDON_NEWYORK's 15:00 UTC close) DATA_ERROR correction --
    # a genuinely later record for the SAME unit, not a replacement of the in-window
    # base file (which the real 24/7-repetition scheduler tasks never overwrite either,
    # per report_archive's own additive-correction-only contract).
    correction_dir = _unit_dir(tmp_path, "EURUSD", "LONDON_NEWYORK", 2026)
    correction = {
        "new_record": {
            "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "symbol": "EURUSD", "cycle": "LONDON_NEWYORK", "trading_date": ARCHIVE_DATE,
            "cycle_state": "DATA_ERROR", "evaluation_time_utc": f"{ARCHIVE_DATE}T18:00:00+00:00",
            "reason_codes": ["SNAPSHOT_IMMUTABILITY_VIOLATION"],
        }
    }
    (correction_dir / f"{ARCHIVE_DATE}.correction-001.json").write_text(json.dumps(correction), encoding="utf-8")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == VALID_DAY


def test_strategy_version_is_recorded_on_every_day_record(tmp_path):
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.strategy_id == STRATEGY_ID
    assert result.strategy_version == STRATEGY_VERSION


def test_classify_series_aggregates_counts_independently(tmp_path):
    _write_all_four_units(tmp_path, "2026-09-09", cycle_state="WATCH")  # VALID
    # 2026-09-10 (Thursday): no evidence -> PENDING
    result = classify_series(
        STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3", "SERIES_TEST",
        dt.date(2026, 9, 9), dt.date(2026, 9, 13), str(tmp_path),
    )
    assert result["valid_days"] == 1
    assert result["excluded_days"] == 2  # Sat 09-12, Sun 09-13
    assert result["unresolved_days"] == 2  # 09-10, 09-11
    assert result["invalid_days"] == 0
    assert len(result["days"]) == 5


def test_duplicate_correction_record_uses_latest_state_only(tmp_path):
    _write_all_four_units(tmp_path, ARCHIVE_DATE, cycle_state="WATCH")
    # A correction for one unit, superseding its WATCH with READY.
    correction_dir = _unit_dir(tmp_path, "EURUSD", "ASIAN_LONDON", 2026)
    correction = {
        "new_record": {
            "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
            "symbol": "EURUSD", "cycle": "ASIAN_LONDON", "trading_date": ARCHIVE_DATE,
            "cycle_state": "READY", "evaluation_time_utc": f"{ARCHIVE_DATE}T09:45:00+00:00",
            "reason_codes": [],
        }
    }
    (correction_dir / f"{ARCHIVE_DATE}.correction-001.json").write_text(json.dumps(correction), encoding="utf-8")
    result = classify_day(STRATEGY_ID, STRATEGY_VERSION, "AG_TRADE_ASSISTANT_V1_0_3",
                           "SERIES_TEST", dt.date.fromisoformat(ARCHIVE_DATE), str(tmp_path))
    assert result.classification == VALID_DAY
    eurusd_asian = next(u for u in result.units if u.symbol == "EURUSD" and u.cycle == "ASIAN_LONDON")
    assert "correction-001" in eurusd_asian.source_artifact_id
