import json
from datetime import datetime, timedelta, timezone

BLIND_PATH = r"D:\ddev\AG profit trading\artifacts\validation\EXTERNAL_SOURCE_ES_S1S\ES_S3_BLIND_REPLAY\occurrence_ledger.json"
DAY_SUMMARIES_PATH = r"D:\ddev\AG profit trading\artifacts\validation\EXTERNAL_SOURCE_ES_S1S\ES_S3_BLIND_REPLAY\day_summaries.json"
REF_PATH = "reference_table.json"

blind = json.load(open(BLIND_PATH))
day_summaries = {d["date"]: d for d in json.load(open(DAY_SUMMARIES_PATH))}
ref = json.load(open(REF_PATH))["events"]

# P3: comparison-only normalization -- broker time (Eightcap/VT/Vantage GMT+3 summer
# convention, INFERRED tier per ES-S0/S1S) converted to UTC for comparison ONLY.
# Neither side's actual data is altered.
BROKER_TO_UTC_OFFSET_HOURS = 3

def ref_utc_time(ev):
    if ev["broker_time"] is None:
        return None
    hh, mm = map(int, ev["broker_time"].split(":"))
    dt = datetime.strptime(ev["date"], "%Y-%m-%d").replace(hour=hh, minute=mm, tzinfo=timezone.utc)
    return dt - timedelta(hours=BROKER_TO_UTC_OFFSET_HOURS)

for ev in ref:
    ev["utc_time_normalized"] = ref_utc_time(ev).isoformat() if ev["broker_time"] else None
    ev["utc_date_normalized"] = (ref_utc_time(ev).date().isoformat() if ev["broker_time"] else ev["date"])

blind_by_date = {}
for o in blind:
    blind_by_date.setdefault(o["date"], []).append(o)

TIME_TOLERANCE_MIN = 30  # comparison-only matching tolerance, not a rule change

mapping_rows = []
matched_blind_ids = set()

for ev in ref:
    candidates = []
    if ev["utc_date_normalized"] in blind_by_date:
        for o in blind_by_date[ev["utc_date_normalized"]]:
            if ev["direction"] == "NEUTRAL":
                continue
            if o["direction"] != ev["direction"]:
                continue
            o_time = datetime.fromisoformat(o["sweep_time"])
            ref_time = datetime.fromisoformat(ev["utc_time_normalized"]) if ev["utc_time_normalized"] else None
            if ref_time is None:
                continue
            delta_min = abs((o_time - ref_time).total_seconds()) / 60
            candidates.append((delta_min, o))
    candidates.sort(key=lambda x: x[0])

    row = {"ref_id": ev["ref_id"], "date": ev["date"], "direction": ev["direction"], "label": ev["label"],
           "ref_entry": ev["entry"], "ref_sl": ev["sl"], "ref_tp": ev["tp"], "ref_result": ev["result"],
           "utc_time_normalized": ev["utc_time_normalized"]}

    day_summary = day_summaries.get(ev["utc_date_normalized"], {})
    asian_range_available = day_summary.get("asian_range_available", False)

    if ev["direction"] == "NEUTRAL":
        row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        row["notes"] = "Reference event itself has no direction/entry (filtered/neutral row) -- structurally not comparable to a directional occurrence."
        row["root_cause"] = ["OTHER_EVIDENCE_SUPPORTED"]
    elif not asian_range_available:
        row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        row["notes"] = f"No Asian range was constructible for {ev['utc_date_normalized']} in the blind replay (weekend/no data)."
        row["root_cause"] = ["DATA_FEED_DIFFERENCE"]
    elif not candidates:
        row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        row["notes"] = "No blind occurrence of matching direction exists on this UTC date at all."
        row["root_cause"] = ["TIME_ALIGNMENT_DIFFERENCE"] if ev["utc_time_normalized"] and (
            ref_utc_time(ev).time() < datetime.strptime("07:00", "%H:%M").time()
        ) else ["ENTRY_SEMANTIC_DIFFERENCE", "BENCHMARK_INFORMATION_INSUFFICIENT"]
    else:
        best_delta, best = candidates[0]
        row["mapped_occurrence_id"] = best["occurrence_id"]
        row["mapped_blind_time"] = best["sweep_time"]
        row["time_delta_minutes"] = best_delta
        row["entry_diff_pips"] = round(abs(best["entry_price"] - ev["entry"]) / 0.0001, 2) if ev["entry"] else None
        row["sl_diff_pips"] = round(abs(best["initial_stop"] - ev["sl"]) / 0.0001, 2) if ev["sl"] else None
        row["tp_diff_pips"] = round(abs(best["tp2_5r"] - ev["tp"]) / 0.0001, 2) if ev["tp"] else None
        row["blind_uncertainty_flags"] = best.get("uncertainty_reasons", [])
        row["blind_resolution_state"] = best["resolution_state"]

        if best_delta <= TIME_TOLERANCE_MIN and row["entry_diff_pips"] is not None and row["entry_diff_pips"] < 2.0:
            row["mapping_status"] = "EXACT_EVENT_MATCH"
        elif best_delta <= 90:
            row["mapping_status"] = "PROBABLE_EVENT_MATCH"
        else:
            row["mapping_status"] = "AMBIGUOUS_EVENT_MAPPING"

        matched_blind_ids.add(best["occurrence_id"])

        # Layer classifications
        row["detection_parity"] = "DETECTION_MATCH" if row["mapping_status"] != "AMBIGUOUS_EVENT_MAPPING" else "DETECTION_UNRESOLVED"
        row["direction_parity"] = "DIRECTION_MATCH"  # guaranteed by construction of candidate filter
        row["geometry_notes"] = {
            "sl_diff_pips": row["sl_diff_pips"], "tp_diff_pips": row["tp_diff_pips"],
        }
        root_causes = []
        if row["time_delta_minutes"] > 0:
            root_causes.append("TIME_ALIGNMENT_DIFFERENCE")
        if row["sl_diff_pips"] is not None and row["sl_diff_pips"] > 1.0:
            root_causes.append("STOP_GEOMETRY_DIFFERENCE")
        if row["tp_diff_pips"] is not None and row["tp_diff_pips"] > 1.0:
            root_causes.append("TARGET_GEOMETRY_DIFFERENCE")
        if best.get("uncertainty_reasons"):
            root_causes.append("SOURCE_RULE_AMBIGUITY")
        if best["resolution_state"] == "UNRESOLVED":
            root_causes.append("M15_INTRABAR_PRECISION_LIMIT")
        row["root_cause"] = root_causes or ["OTHER_EVIDENCE_SUPPORTED"]

    mapping_rows.append(row)

blind_extra = []
for o in blind:
    if o["occurrence_id"] not in matched_blind_ids:
        blind_extra.append({
            "occurrence_id": o["occurrence_id"], "date": o["date"], "direction": o["direction"],
            "sweep_time": o["sweep_time"], "entry_price": o["entry_price"],
            "occurrence_classification": o["occurrence_classification"],
            "uncertainty_reasons": o["uncertainty_reasons"], "resolution_state": o["resolution_state"],
            "mapping_status": "BLIND_ONLY_EXTRA_EVENT",
        })

exact = sum(1 for r in mapping_rows if r["mapping_status"] == "EXACT_EVENT_MATCH")
probable = sum(1 for r in mapping_rows if r["mapping_status"] == "PROBABLE_EVENT_MATCH")
ambiguous = sum(1 for r in mapping_rows if r["mapping_status"] == "AMBIGUOUS_EVENT_MAPPING")
ref_only = sum(1 for r in mapping_rows if r["mapping_status"] == "REFERENCE_ONLY_NO_BLIND_MATCH")

summary = {
    "reference_event_count": 18,
    "reference_events_mapped": exact + probable,
    "exact_mappings": exact,
    "probable_mappings": probable,
    "ambiguous_mappings": ambiguous,
    "reference_only_events": ref_only,
    "blind_only_events": len(blind_extra),
    "total_blind_occurrences": len(blind),
}

json.dump(mapping_rows, open("mapping_ledger.json", "w"), indent=2, default=str)
json.dump(blind_extra, open("blind_extra_ledger.json", "w"), indent=2, default=str)
json.dump(summary, open("aggregate_summary.json", "w"), indent=2, default=str)
json.dump(ref, open("reference_table_normalized.json", "w"), indent=2, default=str)

print(json.dumps(summary, indent=2))
for r in mapping_rows:
    print(r["ref_id"], r["date"], r["direction"], r["mapping_status"], r.get("mapped_occurrence_id"), r.get("root_cause"))
