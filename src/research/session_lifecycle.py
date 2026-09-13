"""Output-only adapter from canonical session replay records to immutable lifecycles."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Sequence


def lifecycle_record(accepted: dict, *, trade_id: str, strategy_id: str, strategy_version: str,
                     symbol: str) -> dict:
    outcome = accepted["outcome"]
    entry_time = accepted["entry_time"]
    friction_r = sum(outcome.get(k) or 0.0 for k in ("spread_cost_R", "commission_cost_R", "slippage_cost_R"))
    events = [{"time": entry_time, "event": "ENTRY", "exit_price": None,
               "gross_R_delta": 0.0, "friction_R_delta": friction_r,
               "quantity_before": 0.0, "quantity_after": 1.0}]
    source_events = outcome.get("event_sequence") or []
    gross_so_far = 0.0
    for i, raw in enumerate(source_events):
        final = i == len(source_events) - 1
        delta = raw.get("gross_R_delta")
        if delta is None:
            delta = (outcome["gross_R"] - gross_so_far) if final else 0.0
        before = raw.get("quantity_before", 1.0 if i == 0 else events[-1]["quantity_after"])
        after = raw.get("quantity_after", 0.0 if final else before)
        events.append({"time": raw["time"], "event": raw["event"], "exit_price": raw.get("exit_price"),
                       "gross_R_delta": delta, "friction_R_delta": 0.0,
                       "quantity_before": before, "quantity_after": after})
        gross_so_far += delta
    if not source_events or outcome.get("gross_R") is None or outcome.get("net_R") is None:
        raise ValueError(f"{trade_id}: unresolved lifecycle")
    times = [datetime.fromisoformat(e["time"]) for e in events]
    if times != sorted(times) or any(e["quantity_after"] < 0 or e["quantity_after"] > e["quantity_before"] for e in events[1:]):
        raise ValueError(f"{trade_id}: invalid lifecycle ordering/volume")
    record = {"trade_id": trade_id, "strategy_id": strategy_id, "strategy_version": strategy_version,
              "symbol": symbol, "direction": accepted["direction"], "entry_time": entry_time,
              "entry_price": accepted["entry_price"], "initial_stop": accepted["stop_price"],
              "initial_risk": abs(accepted["entry_price"] - accepted["stop_price"]),
              "events": events, "gross_R": outcome["gross_R"], "friction_R": friction_r,
              "net_R": outcome["net_R"], "final_state": outcome["terminal_state"],
              "resolution_time": events[-1]["time"], "remaining_quantity": events[-1]["quantity_after"]}
    if abs(sum(e["gross_R_delta"] for e in events) - record["gross_R"]) > 1e-12:
        raise ValueError(f"{trade_id}: gross R does not reconcile")
    if abs(record["gross_R"] - record["friction_R"] - record["net_R"]) > 1e-12:
        raise ValueError(f"{trade_id}: net R does not reconcile")
    return record


def population_hash(records: Sequence[dict]) -> str:
    payload = json.dumps(sorted(records, key=lambda x: x["trade_id"]), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def control_reconcile(records: Sequence[dict]) -> dict:
    return {"trade_count": len(records), "gross_R": sum(r["gross_R"] for r in records),
            "friction_R": sum(r["friction_R"] for r in records), "net_R": sum(r["net_R"] for r in records),
            "population_hash": population_hash(records),
            "volume_invariants": all(r["remaining_quantity"] == 0 for r in records)}


DETERMINISM_FIELDS = (
    "trade_id", "direction", "entry_time", "entry_price", "initial_stop",
    "resolution_time", "final_state", "gross_R", "friction_R", "net_R",
)


def compare_lifecycle_records(first: Sequence[dict], second: Sequence[dict]) -> dict:
    """Compare two ordered lifecycle populations and report the first difference."""
    first_ids = [record.get("trade_id") for record in first]
    second_ids = [record.get("trade_id") for record in second]
    first_difference = None
    if len(first) != len(second):
        first_difference = {"kind": "trade_count", "run_1": len(first), "run_2": len(second)}
    elif first_ids != second_ids:
        for index, (left, right) in enumerate(zip(first_ids, second_ids)):
            if left != right:
                first_difference = {"kind": "occurrence_id", "index": index, "run_1": left, "run_2": right}
                break
    else:
        for index, (left, right) in enumerate(zip(first, second)):
            for field in DETERMINISM_FIELDS:
                if left.get(field) != right.get(field):
                    first_difference = {
                        "kind": "field", "index": index, "field": field,
                        "trade_id": left.get("trade_id"),
                        "run_1": left.get(field), "run_2": right.get(field),
                    }
                    break
            if first_difference:
                break
    return {
        "trade_count_equal": len(first) == len(second),
        "occurrence_ids_equal": set(first_ids) == set(second_ids),
        "occurrence_order_equal": first_ids == second_ids,
        "field_level_equal": first_difference is None,
        "first_difference": first_difference,
    }


def apply_time_stop(record: dict, *, cutoff: datetime, exit_price: float) -> dict:
    """Preserve realized canonical events before cutoff; close only open quantity."""
    resolved_at = datetime.fromisoformat(record["resolution_time"])
    if resolved_at <= cutoff:
        return record
    kept = [e.copy() for e in record["events"] if datetime.fromisoformat(e["time"]) <= cutoff]
    remaining = kept[-1]["quantity_after"]
    direction = 1 if record["direction"] == "LONG" else -1
    exit_r = direction * (exit_price - record["entry_price"]) / record["initial_risk"]
    kept.append({"time": cutoff.isoformat(), "event": "TIME_STOP", "exit_price": exit_price,
                 "gross_R_delta": remaining * exit_r, "friction_R_delta": 0.0,
                 "quantity_before": remaining, "quantity_after": 0.0})
    gross = sum(e["gross_R_delta"] for e in kept)
    friction = sum(e["friction_R_delta"] for e in kept)
    return {**record, "events": kept, "gross_R": gross, "friction_R": friction,
            "net_R": gross - friction, "final_state": "RESOLVED_TIME_STOP",
            "resolution_time": cutoff.isoformat(), "remaining_quantity": 0.0}
