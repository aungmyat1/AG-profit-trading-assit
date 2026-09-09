"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P4 -- deterministic FX shadow day classifier.

Implements the frozen day-classification schema from the signed
`AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1` contract
(docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md), which itself
recorded `existing_shadow_runner = NONE ... a future, separately authorized milestone
will implement the day-aggregation/scheduling code using these frozen definitions` --
this module is that future milestone. It does NOT invent a new definition of VALID_DAY;
every classification rule below cites the contract section it implements.

Evidence source: the per-unit ticket_delivery archive
(`journal/ticket_delivery/archive/fx_ticket_archive/<strategy_id>/<symbol>/<cycle>/
<year>/<date>[.correction-NNN].json`), active since AG_STAGE1_ARCHIVE_ONLY_ACTIVATION_V1
(2026-09-08). Dates before that activation have no per-date archived evidence this
classifier can read -- classified `PENDING_RECONCILIATION` (contract: "evidence exists
but deterministic classification is not yet possible" is extended here, explicitly and
narrowly, to "no archived per-unit evidence exists for this date at all" -- a real,
disclosed limitation of this classifier, not a claim the day itself was operationally
invalid). This is a deliberate, conservative fail-closed choice: never silently promote
an unverifiable pre-archive date to VALID_DAY.

What this classifier CAN verify from evidence: per-unit terminal decision state,
DATA_ERROR presence, non-applicable-unit declaration, and any anomaly reason code
recorded on the evidence itself (e.g. SNAPSHOT_IMMUTABILITY_VIOLATION). What it CANNOT
verify from evidence alone (and therefore never uses to promote a day to VALID_DAY,
only ever to hold it at PENDING_RECONCILIATION when ambiguous): live MT5 reachability
at evaluation time, restart-timeline reconstruction detail beyond what is already
reflected in the terminal decision, and broker-side execution reachability (structurally
guaranteed unreachable by config/trading.yaml, not re-verified per day here).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CLASSIFIER_VERSION = "AG_FX_SHADOW_DAY_CLASSIFIER_V1"
CONTRACT_VERSION = "AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1"

VALID_DAY = "VALID_DAY"
INVALID_DAY = "INVALID_DAY"
EXCLUDED_DAY = "EXCLUDED_DAY"
PENDING_RECONCILIATION = "PENDING_RECONCILIATION"

_ARCHIVE_ROOT = os.path.join("journal", "ticket_delivery", "archive", "fx_ticket_archive")

# Contract section "Daily evidence unit": four expected units per trading day.
EXPECTED_UNITS: Tuple[Tuple[str, str], ...] = (
    ("ASIAN_LONDON", "EURUSD"),
    ("ASIAN_LONDON", "GBPUSD"),
    ("LONDON_NEWYORK", "EURUSD"),
    ("LONDON_NEWYORK", "GBPUSD"),
)

# config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml / AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml
CYCLE_WINDOWS_UTC: Dict[str, Tuple[dt.time, dt.time]] = {
    "ASIAN_LONDON": (dt.time(7, 0), dt.time(11, 0)),
    "LONDON_NEWYORK": (dt.time(12, 0), dt.time(15, 0)),
}

_LEGITIMATE_TERMINAL_STATES = {"READY", "WATCH", "NO_TRADE", "BLOCKED"}
_ARCHIVE_ONLY_ACTIVATION_DATE = dt.date(2026, 9, 8)

# Reason codes that, if present on an otherwise-legitimate terminal record, indicate a
# real anomaly the contract's INVALID_DAY definition covers ("corrupted ledger",
# "inconsistent restart reconstruction", "unresolved session/timestamp failure") even
# though the record's own cycle_state may not literally say DATA_ERROR.
_ANOMALY_REASON_CODES = {"SNAPSHOT_IMMUTABILITY_VIOLATION"}


@dataclass(frozen=True)
class UnitClassification:
    cycle: str
    symbol: str
    status: str  # PASS | DATA_ERROR | ANOMALY | NO_EVIDENCE
    reasons: Tuple[str, ...]
    source_artifact_id: Optional[str]
    evaluation_time_utc: Optional[str]


@dataclass(frozen=True)
class DayClassification:
    strategy_id: str
    strategy_version: str
    application_release: str
    series_id: str
    observation_date: str
    classification: str
    classification_reasons: Tuple[str, ...]
    units: Tuple[UnitClassification, ...]
    source_artifact_ids: Tuple[str, ...]
    generated_at: str
    classifier_version: str
    contract_version: str = CONTRACT_VERSION
    details: Dict[str, Any] = field(default_factory=dict)


def _unit_dir(repo_root: str, strategy_id: str, symbol: str, cycle: str, trading_date: dt.date) -> str:
    return os.path.join(repo_root, _ARCHIVE_ROOT, strategy_id, symbol, cycle, str(trading_date.year))


def _load_all_records_for_date(directory: str, date_str: str) -> List[Tuple[str, dict]]:
    """Returns [(path, record_dict)] for the base file and every correction, in
    ascending correction order (base first). A malformed file is skipped, not guessed
    at -- surfaces as reduced evidence, never a fabricated record."""
    if not os.path.isdir(directory):
        return []
    candidates = []
    base = os.path.join(directory, f"{date_str}.json")
    if os.path.isfile(base):
        candidates.append((0, base))
    for name in os.listdir(directory):
        prefix = f"{date_str}.correction-"
        if name.startswith(prefix) and name.endswith(".json"):
            try:
                n = int(name[len(prefix):-len(".json")])
            except ValueError:
                continue
            candidates.append((n, os.path.join(directory, name)))
    candidates.sort(key=lambda pair: pair[0])

    results: List[Tuple[str, dict]] = []
    for _n, path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        record = raw.get("new_record", raw) if isinstance(raw, dict) else None
        if isinstance(record, dict):
            results.append((path, record))
    return results


def _in_window(evaluation_time_utc: Optional[str], trading_date: dt.date, cycle: str) -> bool:
    if not evaluation_time_utc:
        return False
    try:
        ts = dt.datetime.fromisoformat(evaluation_time_utc.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    ts_utc = ts.astimezone(dt.timezone.utc)
    if ts_utc.date() != trading_date:
        return False
    start, end = CYCLE_WINDOWS_UTC[cycle]
    return start <= ts_utc.time() < end


def classify_unit(
    repo_root: str, strategy_id: str, symbol: str, cycle: str, trading_date: dt.date,
) -> UnitClassification:
    """Terminal-state classification for one (cycle, symbol) unit, using the LAST
    in-window record (evaluation_time_utc inside the cycle's own execution_window) as
    the unit's authoritative evidence -- a later, out-of-window scheduler run (the
    existing 24/7-repetition tasks, see AG_SCHEDULED_WORK_OBJECTIVE_ALIGNMENT_PHASE2
    finding) is a legitimate no-op/anomaly outside the tested window and must not
    retroactively invalidate a day whose in-window evaluation already completed."""
    date_str = trading_date.isoformat()
    directory = _unit_dir(repo_root, strategy_id, symbol, cycle, trading_date)
    all_records = _load_all_records_for_date(directory, date_str)

    in_window = [
        (path, rec) for path, rec in all_records
        if _in_window(rec.get("evaluation_time_utc"), trading_date, cycle)
    ]
    if not in_window:
        return UnitClassification(
            cycle=cycle, symbol=symbol, status="NO_EVIDENCE",
            reasons=("NO_IN_WINDOW_EVIDENCE",), source_artifact_id=None, evaluation_time_utc=None,
        )

    path, record = in_window[-1]  # latest in-window evaluation is authoritative
    cycle_state = record.get("cycle_state")
    reason_codes = set(record.get("reason_codes") or [])

    if reason_codes & _ANOMALY_REASON_CODES:
        return UnitClassification(
            cycle=cycle, symbol=symbol, status="ANOMALY",
            reasons=tuple(sorted(reason_codes & _ANOMALY_REASON_CODES)),
            source_artifact_id=path, evaluation_time_utc=record.get("evaluation_time_utc"),
        )
    if cycle_state == "DATA_ERROR":
        return UnitClassification(
            cycle=cycle, symbol=symbol, status="DATA_ERROR",
            reasons=tuple(reason_codes) or ("DATA_ERROR",),
            source_artifact_id=path, evaluation_time_utc=record.get("evaluation_time_utc"),
        )
    if cycle_state in _LEGITIMATE_TERMINAL_STATES:
        return UnitClassification(
            cycle=cycle, symbol=symbol, status="PASS",
            reasons=(f"TERMINAL_STATE:{cycle_state}",),
            source_artifact_id=path, evaluation_time_utc=record.get("evaluation_time_utc"),
        )
    return UnitClassification(
        cycle=cycle, symbol=symbol, status="ANOMALY",
        reasons=(f"UNRECOGNIZED_CYCLE_STATE:{cycle_state}",),
        source_artifact_id=path, evaluation_time_utc=record.get("evaluation_time_utc"),
    )


def classify_day(
    strategy_id: str,
    strategy_version: str,
    application_release: str,
    series_id: str,
    trading_date: dt.date,
    repo_root: str = ".",
    *,
    now: Optional[dt.datetime] = None,
) -> DayClassification:
    """P4.2: never consults any future trade outcome, R result, or win/loss -- only
    the terminal decision_status/cycle_state that was already recorded at/before the
    end of the unit's own execution window. Zero-lookahead by construction: this
    function never reads artifacts/outcome_resolution/records/ at all."""
    now = now or dt.datetime.now(dt.timezone.utc)

    if trading_date.weekday() >= 5:  # Sat=5, Sun=6 -- FX weekend closure
        return DayClassification(
            strategy_id=strategy_id, strategy_version=strategy_version,
            application_release=application_release, series_id=series_id,
            observation_date=trading_date.isoformat(), classification=EXCLUDED_DAY,
            classification_reasons=("WEEKEND_NON_TRADING_DAY",), units=(),
            source_artifact_ids=(), generated_at=now.isoformat(),
            classifier_version=CLASSIFIER_VERSION,
        )

    if trading_date < _ARCHIVE_ONLY_ACTIVATION_DATE:
        return DayClassification(
            strategy_id=strategy_id, strategy_version=strategy_version,
            application_release=application_release, series_id=series_id,
            observation_date=trading_date.isoformat(), classification=PENDING_RECONCILIATION,
            classification_reasons=("NO_PERSISTED_EVIDENCE_FOR_DATE:PRE_ARCHIVE_ONLY_ACTIVATION",),
            units=(), source_artifact_ids=(), generated_at=now.isoformat(),
            classifier_version=CLASSIFIER_VERSION,
            details={"archive_only_activation_date": _ARCHIVE_ONLY_ACTIVATION_DATE.isoformat()},
        )

    units = tuple(
        classify_unit(repo_root, strategy_id, symbol, cycle, trading_date)
        for cycle, symbol in EXPECTED_UNITS
    )
    source_artifact_ids = tuple(u.source_artifact_id for u in units if u.source_artifact_id)

    statuses = {u.status for u in units}
    reasons: List[str] = []
    if "ANOMALY" in statuses:
        classification = INVALID_DAY
        reasons.extend(f"ANOMALY:{u.cycle}:{u.symbol}:{','.join(u.reasons)}" for u in units if u.status == "ANOMALY")
    elif "DATA_ERROR" in statuses:
        classification = INVALID_DAY
        reasons.extend(f"DATA_ERROR:{u.cycle}:{u.symbol}" for u in units if u.status == "DATA_ERROR")
    elif "NO_EVIDENCE" in statuses:
        if statuses == {"NO_EVIDENCE"}:
            classification = PENDING_RECONCILIATION
            reasons.append("NO_IN_WINDOW_EVIDENCE_FOR_ANY_UNIT")
        else:
            classification = INVALID_DAY
            reasons.extend(f"MISSING_MANDATORY_EVIDENCE:{u.cycle}:{u.symbol}" for u in units if u.status == "NO_EVIDENCE")
    else:
        classification = VALID_DAY
        reasons.append("ALL_FOUR_UNITS_EVALUATED_WITH_LEGITIMATE_TERMINAL_STATE")

    return DayClassification(
        strategy_id=strategy_id, strategy_version=strategy_version,
        application_release=application_release, series_id=series_id,
        observation_date=trading_date.isoformat(), classification=classification,
        classification_reasons=tuple(reasons), units=units,
        source_artifact_ids=source_artifact_ids, generated_at=now.isoformat(),
        classifier_version=CLASSIFIER_VERSION,
    )


def classify_series(
    strategy_id: str, strategy_version: str, application_release: str, series_id: str,
    start_date: dt.date, as_of_date: dt.date, repo_root: str = ".",
) -> Dict[str, Any]:
    """Aggregates classify_day() over every calendar day from start_date through
    as_of_date inclusive. Returns per-classification counts and the full per-day
    record list -- never a single collapsed number, so valid/invalid/excluded/
    unresolved stay independently inspectable (P4.4)."""
    days: List[DayClassification] = []
    d = start_date
    while d <= as_of_date:
        days.append(classify_day(strategy_id, strategy_version, application_release, series_id, d, repo_root))
        d += dt.timedelta(days=1)

    counts = {VALID_DAY: 0, INVALID_DAY: 0, EXCLUDED_DAY: 0, PENDING_RECONCILIATION: 0}
    for day in days:
        counts[day.classification] += 1

    return {
        "series_id": series_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "start_date": start_date.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "valid_days": counts[VALID_DAY],
        "invalid_days": counts[INVALID_DAY],
        "excluded_days": counts[EXCLUDED_DAY],
        "unresolved_days": counts[PENDING_RECONCILIATION],
        "days": days,
        "classifier_version": CLASSIFIER_VERSION,
        "contract_version": CONTRACT_VERSION,
    }
