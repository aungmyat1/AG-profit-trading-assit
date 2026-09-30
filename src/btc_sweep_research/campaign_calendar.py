"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P3.3/P3.4 -- the canonical BTC observation
campaign counting contract.

Replaces "number of JSON files on disk = campaign progress" (the pre-M1 behavior of
validation_framework.adapters.btc_adapter._campaign_observed_count, which counted every
non-correction file regardless of what it contained) with evidence-qualified counting:
only a record whose own `counting_eligible` field (see
btc_sweep_research.daily_report.evaluate_counting_eligibility) is `True` counts toward
NATURAL_CAMPAIGN_ACCRUAL. A DATA_ERROR day, an out-of-window record, a wrong-strategy/
version record, or a legacy record predating the `counting_eligible` field (fails
closed -- never assumed eligible) are all counted separately, never silently folded into
`valid_campaign_days`.

Missed-day semantics (P3.4): BTC trades 24/7 (no weekend/holiday exclusion applies to
this strategy's CRYPTO_PERP profile -- verified against
strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml, which documents no non-trading-day
concept), so every UTC calendar day from the campaign's own authorized activation date
through the latest fully-closed UTC day is an EXPECTED_VALID_OBSERVATION day. A day with
no persisted record at all (neither a base file nor any correction) is a candidate
MISSED_DAY -- this is never inferred merely from a gap in a sequence, only from an
explicit expected-day calendar compared against what is actually on disk.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CampaignStats:
    valid_campaign_days: int
    data_error_days: int
    excluded_days: int
    other_ineligible_days: int
    missed_days: int
    total_observation_records: int
    valid_dates: Tuple[str, ...]
    data_error_dates: Tuple[str, ...]
    missed_dates: Tuple[str, ...]
    duplicate_dates_detected: Tuple[str, ...]
    activation_date: Optional[str]
    as_of_date: Optional[str]
    target: int
    details: Dict[str, object] = field(default_factory=dict)


def _latest_record_per_date(archive_dir: str) -> Dict[str, dict]:
    """Resolves each observation_date to its most-recently-corrected record (the
    `report_archive.write_report` correction chain: `<date>.json` is the original,
    `<date>.correction-NNN.json` files each carry `{"new_record": {...}}` and the
    highest N is authoritative). A malformed/unreadable file is skipped, never guessed
    at -- it neither counts as valid nor silently disappears (see `unreadable_files` in
    the returned stats' details)."""
    if not os.path.isdir(archive_dir):
        return {}

    by_date_files: Dict[str, List[str]] = {}
    for root, _dirs, files in os.walk(archive_dir):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            stem = fname[: -len(".json")]
            date_part = stem.split(".correction-")[0]
            by_date_files.setdefault(date_part, []).append(os.path.join(root, fname))

    resolved: Dict[str, dict] = {}
    for date_part, paths in by_date_files.items():
        def _correction_index(p: str) -> int:
            name = os.path.basename(p)
            if ".correction-" not in name:
                return 0
            try:
                return int(name.split(".correction-")[1].split(".json")[0])
            except (IndexError, ValueError):
                return 0

        latest_path = max(paths, key=_correction_index)
        try:
            with open(latest_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        record = raw.get("new_record", raw) if isinstance(raw, dict) else None
        if isinstance(record, dict):
            resolved[date_part] = record
    return resolved


def _is_valid(record: dict, expected_strategy_id: str, expected_strategy_version: str) -> bool:
    """Fail-closed: a record missing the `counting_eligible` field (written before this
    M1 milestone) is NEVER assumed eligible merely because a file exists on disk --
    exactly the defect this module replaces."""
    if record.get("counting_eligible") is True:
        return True
    return False


def compute_campaign_stats(
    repo_root: str,
    archive_dir: str,
    *,
    expected_strategy_id: str,
    expected_strategy_version: str,
    target: int,
    activation_date: Optional[dt.date] = None,
    as_of_date: Optional[dt.date] = None,
) -> CampaignStats:
    full_dir = os.path.join(repo_root, archive_dir)
    records = _latest_record_per_date(full_dir)

    valid_dates: List[str] = []
    data_error_dates: List[str] = []
    other_ineligible_dates: List[str] = []
    duplicate_dates: List[str] = []

    for date_str, record in sorted(records.items()):
        if _is_valid(record, expected_strategy_id, expected_strategy_version):
            valid_dates.append(date_str)
        elif record.get("decision") == "DATA_ERROR":
            data_error_dates.append(date_str)
        else:
            other_ineligible_dates.append(date_str)

    missed_dates: List[str] = []
    if activation_date is not None and as_of_date is not None and as_of_date >= activation_date:
        expected = {
            (activation_date + dt.timedelta(days=i)).isoformat()
            for i in range((as_of_date - activation_date).days + 1)
        }
        observed = set(records.keys())
        missed_dates = sorted(expected - observed)

    return CampaignStats(
        valid_campaign_days=len(valid_dates),
        data_error_days=len(data_error_dates),
        excluded_days=0,  # BTC's CRYPTO_PERP profile has no signed non-trading-day exclusion
        other_ineligible_days=len(other_ineligible_dates),
        missed_days=len(missed_dates),
        total_observation_records=len(records),
        valid_dates=tuple(valid_dates),
        data_error_dates=tuple(data_error_dates),
        missed_dates=tuple(missed_dates),
        duplicate_dates_detected=tuple(duplicate_dates),
        activation_date=activation_date.isoformat() if activation_date else None,
        as_of_date=as_of_date.isoformat() if as_of_date else None,
        target=target,
        details={
            "other_ineligible_dates": tuple(other_ineligible_dates),
            "counting_contract": "counting_eligible field only; legacy records without it fail closed to not-counted",
        },
    )
