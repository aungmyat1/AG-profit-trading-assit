import csv, json, sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict

sys.path.insert(0, r"D:\ddev\AG profit trading\src")

from session_trading_source_v1.asian_range import build_asian_range, is_in_asian_session
from session_trading_source_v1.models import Candle, Direction, OccurrenceState, SweepStatus
from session_trading_source_v1.sweep import detect_sweeps
from session_trading_source_v1.occurrence import generate_occurrences, MANAGEMENT_END_UTC
from session_trading_source_v1 import STRATEGY_ID, VERSION, COMPONENT

DATASET_PATH = r"D:\ddev\AG profit trading\.claude\worktrees\ssc1d-ext-r1\artifacts\validation\ST_SESSION_SWEEP_CONTINUATION_V1\EXT_R2B1_M15_REDUCED_PRECISION_PACKAGE\derived\EURUSD_M15_UTC_20221003_20221021_native_normalized.csv"
PIP_SIZE = 0.0001
REPLAY_START = datetime(2022, 10, 3, tzinfo=timezone.utc).date()
REPLAY_END = datetime(2022, 10, 21, tzinfo=timezone.utc).date()

# --- load dataset ---
candles = []
with open(DATASET_PATH, newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        ts, o, h, l, c = row[0], row[1], row[2], row[3], row[4]
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:00Z").replace(tzinfo=timezone.utc)
        candles.append(Candle(time=dt, open=float(o), high=float(h), low=float(l), close=float(c)))

actual_first = candles[0].time.isoformat()
actual_last = candles[-1].time.isoformat()
total_rows = len(candles)

by_day = defaultdict(list)
for c in candles:
    by_day[c.time.date()].append(c)

# all calendar days in the requested period (inclusive)
all_days = []
d = REPLAY_START
while d <= REPLAY_END:
    all_days.append(d)
    d += timedelta(days=1)

structural_ledger = []   # every raw sweep event, including AMBIGUOUS_DUAL_SIDE
occurrence_ledger = []   # every Occurrence dataclass (VALID sweeps only), with full geometry+resolution
day_summaries = []

occ_id = 0
for day in all_days:
    day_candles = sorted(by_day.get(day, []), key=lambda c: c.time)
    asian_candles = [c for c in day_candles if is_in_asian_session(c)]
    post_candles = [c for c in day_candles if not is_in_asian_session(c)]

    asian_range = build_asian_range(asian_candles)
    day_summary = {
        "date": day.isoformat(),
        "asian_candle_count": len(asian_candles),
        "post_session_candle_count": len(post_candles),
        "asian_range_available": asian_range is not None,
    }
    if asian_range is None:
        day_summary["reason"] = "NO_ASIAN_SESSION_DATA" if not asian_candles else "DEGENERATE_RANGE"
        day_summaries.append(day_summary)
        continue

    day_summary["asian_high"] = asian_range.high
    day_summary["asian_low"] = asian_range.low
    day_summary["asian_range_price"] = asian_range.range
    day_summary["asian_range_pips"] = asian_range.range / PIP_SIZE

    management_window = [c for c in post_candles if c.time.time() < MANAGEMENT_END_UTC]
    raw_events = detect_sweeps(asian_range, management_window)
    for ev in raw_events:
        structural_ledger.append({
            "date": day.isoformat(), "status": ev.status.value, "time": ev.time.isoformat(),
            "direction": ev.direction.value if ev.direction else None,
            "entry_price": ev.entry_price, "evidence": ev.evidence,
        })

    occs = generate_occurrences(asian_candles, post_candles, PIP_SIZE)
    day_summary["structural_event_count"] = len(raw_events)
    day_summary["valid_sweep_count"] = sum(1 for e in raw_events if e.status == SweepStatus.VALID)
    day_summary["dual_side_ambiguous_count"] = sum(1 for e in raw_events if e.status == SweepStatus.AMBIGUOUS_DUAL_SIDE)
    day_summary["occurrence_count"] = len(occs)
    day_summaries.append(day_summary)

    for occ in occs:
        occ_id += 1
        occurrence_ledger.append({
            "occurrence_id": f"ES_S3_{occ_id:03d}",
            "date": day.isoformat(),
            "asian_high": occ.asian_range.high,
            "asian_low": occ.asian_range.low,
            "asian_range_A": occ.asian_range.range,
            "asian_range_pips": occ.asian_range.range / PIP_SIZE,
            "direction": occ.direction.value,
            "sweep_time": occ.signal_time.isoformat(),
            "entry_price": occ.entry_price,
            "initial_stop": occ.stop_price,
            "initial_risk": occ.initial_risk,
            "tp1_opposite_boundary": occ.leg_a_target,
            "tp2_5r": occ.tp2_target,
            "occurrence_classification": occ.occurrence_classification,
            "uncertainty_reasons": occ.uncertainty_reasons,
            "resolution_state": occ.resolution.state.value,
            "resolution_reason": occ.resolution.reason,
            "resolution_events": occ.resolution.events,
        })

# --- population partitions (P8) ---
partition_A = [o for o in occurrence_ledger if o["occurrence_classification"] == "SOURCE_DETERMINISTIC"]
partition_B = [o for o in occurrence_ledger if o["occurrence_classification"] == "SOURCE_RULE_DEPENDENT_UNRESOLVED"]
partition_C_dual_side = [e for e in structural_ledger if e["status"] == "AMBIGUOUS_DUAL_SIDE"]
partition_C_intrabar = [o for o in occurrence_ledger if o["resolution_state"] == "UNRESOLVED"]
partition_D_no_valid = sum(1 for d in day_summaries if d.get("asian_range_available") and d.get("valid_sweep_count", 0) == 0)

resolution_counts = defaultdict(int)
for o in occurrence_ledger:
    resolution_counts[o["resolution_state"]] += 1

direction_counts = defaultdict(int)
for o in occurrence_ledger:
    direction_counts[o["direction"]] += 1

# --- descriptive gross R (P9), SOURCE_DETERMINISTIC + fully resolved terminal states only ---
def gross_r(o):
    state = o["resolution_state"]
    risk = o["initial_risk"]
    entry = o["entry_price"]
    direction = o["direction"]
    if state == "STOPPED_FULL_POSITION":
        return -1.0
    if state == "RUNNER_TP2":
        # 0.75 * partial_R + 0.25 * 5R  (partial_R measured to opposite boundary)
        tp1 = o["tp1_opposite_boundary"]
        partial_R = ((tp1 - entry) / risk) if direction == "LONG" else ((entry - tp1) / risk)
        return 0.75 * partial_R + 0.25 * 5.0
    if state == "RUNNER_BE_EXIT":
        tp1 = o["tp1_opposite_boundary"]
        partial_R = ((tp1 - entry) / risk) if direction == "LONG" else ((entry - tp1) / risk)
        return 0.75 * partial_R + 0.25 * 0.0
    return None  # OPEN / UNRESOLVED -> undefined, not estimated

descriptive_resolved = [(o, gross_r(o)) for o in partition_A]
descriptive_resolved_valid = [(o, r) for o, r in descriptive_resolved if r is not None]
descriptive_unresolved_count = sum(1 for o, r in descriptive_resolved if r is None)

summary = {
    "strategy_id": STRATEGY_ID, "strategy_version": VERSION, "component": COMPONENT,
    "dataset_path": DATASET_PATH,
    "dataset_hash": "b7ae5c458812107fbf3843f5f5e259b0ed14069c1906370d050330a1605af34e",
    "dataset_actual_first_timestamp": actual_first,
    "dataset_actual_last_timestamp": actual_last,
    "dataset_total_rows": total_rows,
    "replay_period_requested": f"{REPLAY_START.isoformat()}..{REPLAY_END.isoformat()}",
    "total_calendar_days_in_period": len(all_days),
    "days_with_asian_range": sum(1 for d in day_summaries if d["asian_range_available"]),
    "days_without_asian_range": sum(1 for d in day_summaries if not d["asian_range_available"]),
    "total_structural_events": len(structural_ledger),
    "total_valid_sweep_events": sum(1 for e in structural_ledger if e["status"] == "VALID"),
    "total_dual_side_ambiguous_events": len(partition_C_dual_side),
    "total_occurrences": len(occurrence_ledger),
    "partition_A_source_deterministic_count": len(partition_A),
    "partition_B_source_rule_dependent_unresolved_count": len(partition_B),
    "partition_C_dual_side_sweep_ambiguous_count": len(partition_C_dual_side),
    "partition_C_intrabar_order_unresolved_count": len(partition_C_intrabar),
    "partition_D_days_with_range_but_no_valid_sweep": partition_D_no_valid,
    "resolution_state_counts": dict(resolution_counts),
    "direction_distribution": dict(direction_counts),
    "descriptive_gross_R_subset": "SOURCE_DETERMINISTIC only, fully-resolved terminal states only (STOPPED_FULL_POSITION, RUNNER_TP2, RUNNER_BE_EXIT)",
    "descriptive_gross_R_n": len(descriptive_resolved_valid),
    "descriptive_gross_R_sum": sum(r for o, r in descriptive_resolved_valid) if descriptive_resolved_valid else None,
    "descriptive_gross_R_excluded_undefined_count": descriptive_unresolved_count,
    "label": "BENCHMARK_REPLICATION_DESCRIPTIVE_ONLY",
    "friction_status": "UNAVAILABLE_FOR_SOURCE_BENCHMARK",
    "benchmark_reference_table_opened": False,
    "benchmark_outcomes_consumed": False,
}

with open("structural_ledger.json", "w") as f:
    json.dump(structural_ledger, f, indent=2, default=str)
with open("occurrence_ledger.json", "w") as f:
    json.dump(occurrence_ledger, f, indent=2, default=str)
with open("day_summaries.json", "w") as f:
    json.dump(day_summaries, f, indent=2, default=str)
with open("replay_summary.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)

print(json.dumps(summary, indent=2, default=str))
