"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P3.5 acceptance tests for the BTC campaign
counting contract (btc_sweep_research.campaign_calendar, wired into
validation_framework.adapters.btc_adapter). Uses a real tmp_path archive tree -- never
touches the live journal/reports/btc/ directory.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btc_sweep_research.campaign_calendar import compute_campaign_stats  # noqa: E402

STRATEGY_ID = "ST_LIQUIDITY_SWEEP_RETEST_V1"
STRATEGY_VERSION = "2.0.0"


def _write(archive_dir: Path, date_str: str, **overrides):
    record = {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "decision": "NO_TRADE",
        "data_quality": {"status": "PASS"},
        "qualification_evidence_eligible": True,
        "counting_eligible": True,
    }
    record.update(overrides)
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{date_str}.json").write_text(json.dumps(record), encoding="utf-8")


def _correction(archive_dir: Path, date_str: str, n: int, **overrides):
    record = {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "decision": "NO_TRADE",
        "data_quality": {"status": "PASS"},
        "qualification_evidence_eligible": True,
        "counting_eligible": True,
    }
    record.update(overrides)
    (archive_dir / f"{date_str}.correction-{n:03d}.json").write_text(
        json.dumps({"new_record": record}), encoding="utf-8"
    )


def _stats(tmp_path, activation="2026-09-01", as_of="2026-09-03"):
    return compute_campaign_stats(
        str(tmp_path),
        "btc_archive",
        expected_strategy_id=STRATEGY_ID,
        expected_strategy_version=STRATEGY_VERSION,
        target=30,
        activation_date=dt.date.fromisoformat(activation),
        as_of_date=dt.date.fromisoformat(as_of),
    )


def test_valid_ready_watch_no_trade_each_count_once(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", decision="READY")
    _write(archive, "2026-09-02", decision="WATCH")
    _write(archive, "2026-09-03", decision="NO_TRADE")
    stats = _stats(tmp_path)
    assert stats.valid_campaign_days == 3
    assert stats.missed_days == 0


def test_data_error_increments_error_days_not_valid(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", decision="DATA_ERROR",
           data_quality={"status": "FAIL"}, counting_eligible=False)
    _write(archive, "2026-09-02")
    _write(archive, "2026-09-03")
    stats = _stats(tmp_path)
    assert stats.valid_campaign_days == 2
    assert stats.data_error_days == 1
    assert "2026-09-01" in stats.data_error_dates


def test_outside_window_does_not_count(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", qualification_evidence_eligible=False, counting_eligible=False)
    _write(archive, "2026-09-02")
    _write(archive, "2026-09-03")
    stats = _stats(tmp_path)
    assert stats.valid_campaign_days == 2
    assert "2026-09-01" not in stats.valid_dates


def test_unauthorized_catch_up_does_not_count(tmp_path):
    """A record produced outside the signed report window (the only mechanism this
    repository has for an unauthorized/late catch-up attempt) must never count --
    counting_eligible is False whenever qualification_evidence_eligible is False,
    regardless of what decision the record otherwise carries."""
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", decision="READY",
           qualification_evidence_eligible=False, counting_eligible=False)
    stats = _stats(tmp_path, as_of="2026-09-01")
    assert stats.valid_campaign_days == 0


def test_duplicate_same_day_record_counts_once_via_latest_correction(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", decision="WATCH")
    _correction(archive, "2026-09-01", 1, decision="DATA_ERROR",
                data_quality={"status": "FAIL"}, counting_eligible=False)
    stats = _stats(tmp_path, as_of="2026-09-01")
    # Latest correction (DATA_ERROR) is authoritative -- exactly one date's worth of
    # evidence, not two, and it reflects the corrected (non-counting) state.
    assert stats.total_observation_records == 1
    assert stats.valid_campaign_days == 0
    assert stats.data_error_days == 1


def test_wrong_strategy_version_is_rejected(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", strategy_version="1.0.0", counting_eligible=False)
    stats = _stats(tmp_path, as_of="2026-09-01")
    assert stats.valid_campaign_days == 0


def test_missing_required_market_data_is_not_valid(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01", data_quality={"status": "FAIL"}, counting_eligible=False)
    stats = _stats(tmp_path, as_of="2026-09-01")
    assert stats.valid_campaign_days == 0


def test_legacy_record_without_counting_eligible_field_fails_closed(tmp_path):
    """A record written before this M1 milestone has no `counting_eligible` field at
    all -- it must never be silently treated as valid just because the file exists."""
    archive = tmp_path / "btc_archive"
    archive.mkdir(parents=True)
    legacy = {
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
        "decision": "WATCH", "data_quality": {"status": "PASS"},
    }
    (archive / "2026-09-01.json").write_text(json.dumps(legacy), encoding="utf-8")
    stats = _stats(tmp_path, as_of="2026-09-01")
    assert stats.valid_campaign_days == 0
    assert stats.total_observation_records == 1


def test_missed_day_calculated_from_expected_calendar_not_from_gaps(tmp_path):
    archive = tmp_path / "btc_archive"
    _write(archive, "2026-09-01")
    # 2026-09-02 and 2026-09-03 never archived at all.
    stats = _stats(tmp_path, activation="2026-09-01", as_of="2026-09-03")
    assert stats.missed_days == 2
    assert stats.missed_dates == ("2026-09-02", "2026-09-03")


def test_no_missed_days_before_activation_date(tmp_path):
    archive = tmp_path / "btc_archive"
    stats = _stats(tmp_path, activation="2026-09-05", as_of="2026-09-03")
    assert stats.missed_days == 0
    assert stats.missed_dates == ()


def test_empty_archive_directory_is_zero_not_error(tmp_path):
    stats = _stats(tmp_path, as_of="2026-09-03")
    assert stats.valid_campaign_days == 0
    assert stats.total_observation_records == 0
    assert stats.missed_days == 3
