import json
from datetime import datetime, timedelta, timezone

BLIND_PATH = r"D:\ddev\AG profit trading\artifacts\validation\EXTERNAL_SOURCE_ES_S1S\ES_S3_BLIND_REPLAY\occurrence_ledger.json"
DAY_SUMMARIES_PATH = r"D:\ddev\AG profit trading\artifacts\validation\EXTERNAL_SOURCE_ES_S1S\ES_S3_BLIND_REPLAY\day_summaries.json"
REF_PATH = r"D:\ddev\AG profit trading\artifacts\validation\EXTERNAL_SOURCE_ES_S1S\ES_S4_COMPARISON\reference_table.json"

blind = json.load(open(BLIND_PATH))
day_summaries = {d["date"]: d for d in json.load(open(DAY_SUMMARIES_PATH))}
ref_base = json.load(open(REF_PATH))["events"]

TIME_TOLERANCE_EXACT_MIN = 30
TIME_TOLERANCE_PROBABLE_MIN = 90
EXACT_ENTRY_PIP_TOL = 2.0

blind_by_date = {}
for o in blind:
    blind_by_date.setdefault(o["date"], []).append(o)


def ref_utc_time(ev, offset_hours):
    if ev["broker_time"] is None:
        return None
    hh, mm = map(int, ev["broker_time"].split(":"))
    dt = datetime.strptime(ev["date"], "%Y-%m-%d").replace(hour=hh, minute=mm, tzinfo=timezone.utc)
    return dt - timedelta(hours=offset_hours)


def run_model(offset_hours, label):
    ref = json.loads(json.dumps(ref_base))  # deep copy, never mutate shared base
    rows = []
    matched_blind_ids = set()

    for ev in ref:
        rt = ref_utc_time(ev, offset_hours)
        ev["utc_time_normalized"] = rt.isoformat() if rt else None
        ev["utc_date_normalized"] = rt.date().isoformat() if rt else ev["date"]

        candidates = []
        if ev["direction"] != "NEUTRAL" and ev["utc_date_normalized"] in blind_by_date:
            for o in blind_by_date[ev["utc_date_normalized"]]:
                if o["direction"] != ev["direction"]:
                    continue
                o_time = datetime.fromisoformat(o["sweep_time"])
                delta_min = abs((o_time - rt).total_seconds()) / 60
                candidates.append((delta_min, o))
        candidates.sort(key=lambda x: x[0])

        row = {"ref_id": ev["ref_id"], "date": ev["date"], "direction": ev["direction"],
               "utc_time_normalized": ev["utc_time_normalized"], "utc_date_normalized": ev["utc_date_normalized"]}

        day_summary = day_summaries.get(ev["utc_date_normalized"], {})
        asian_range_available = day_summary.get("asian_range_available", False)
        pre_asian_close = rt is not None and rt.time() < datetime.strptime("07:00", "%H:%M").time()
        row["falls_before_asian_close_utc"] = pre_asian_close

        if ev["direction"] == "NEUTRAL":
            row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        elif not asian_range_available:
            row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        elif not candidates:
            row["mapping_status"] = "REFERENCE_ONLY_NO_BLIND_MATCH"
        else:
            best_delta, best = candidates[0]
            entry_diff = round(abs(best["entry_price"] - ev["entry"]) / 0.0001, 2) if ev["entry"] else None
            row["mapped_occurrence_id"] = best["occurrence_id"]
            row["time_delta_minutes"] = best_delta
            row["entry_diff_pips"] = entry_diff
            row["sl_diff_pips"] = round(abs(best["initial_stop"] - ev["sl"]) / 0.0001, 2) if ev["sl"] else None
            row["tp_diff_pips"] = round(abs(best["tp2_5r"] - ev["tp"]) / 0.0001, 2) if ev["tp"] else None

            if best_delta <= TIME_TOLERANCE_EXACT_MIN and entry_diff is not None and entry_diff < EXACT_ENTRY_PIP_TOL:
                row["mapping_status"] = "EXACT_EVENT_MATCH"
            elif best_delta <= TIME_TOLERANCE_PROBABLE_MIN:
                row["mapping_status"] = "PROBABLE_EVENT_MATCH"
            else:
                row["mapping_status"] = "AMBIGUOUS_EVENT_MAPPING"
            matched_blind_ids.add(best["occurrence_id"])

        rows.append(row)

    exact = sum(1 for r in rows if r["mapping_status"] == "EXACT_EVENT_MATCH")
    probable = sum(1 for r in rows if r["mapping_status"] == "PROBABLE_EVENT_MATCH")
    ambiguous = sum(1 for r in rows if r["mapping_status"] == "AMBIGUOUS_EVENT_MAPPING")
    ref_only = sum(1 for r in rows if r["mapping_status"] == "REFERENCE_ONLY_NO_BLIND_MATCH")
    pre_asian_count = sum(1 for r in rows if r.get("falls_before_asian_close_utc"))
    deltas = [r["time_delta_minutes"] for r in rows if "time_delta_minutes" in r]
    entry_diffs = [r["entry_diff_pips"] for r in rows if r.get("entry_diff_pips") is not None]

    return {
        "label": label, "offset_hours": offset_hours, "rows": rows,
        "summary": {
            "exact_mappings": exact, "probable_mappings": probable, "ambiguous_mappings": ambiguous,
            "reference_only_events": ref_only, "mapped_total": exact + probable,
            "events_falling_before_07_00_utc_asian_close": pre_asian_count,
            "mean_time_delta_minutes": round(sum(deltas) / len(deltas), 1) if deltas else None,
            "median_time_delta_minutes": sorted(deltas)[len(deltas) // 2] if deltas else None,
            "mean_entry_diff_pips": round(sum(entry_diffs) / len(entry_diffs), 2) if entry_diffs else None,
        },
    }


m0 = run_model(3, "M0_MINUS_3H_BROKER_LOCAL")   # ES-S4's original assumption
m1 = run_model(0, "M1_AS_IS_UTC")                # ES-S5's H1 hypothesis

print("M0:", json.dumps(m0["summary"], indent=2))
print("M1:", json.dumps(m1["summary"], indent=2))

json.dump({"M0": m0, "M1": m1}, open("clock_sensitivity_result.json", "w"), indent=2, default=str)

# Per-event delta table
delta_table = []
for r0, r1 in zip(m0["rows"], m1["rows"]):
    delta_table.append({
        "ref_id": r0["ref_id"], "date": r0["date"], "direction": r0["direction"],
        "M0_status": r0["mapping_status"], "M0_time_delta_min": r0.get("time_delta_minutes"),
        "M0_entry_diff_pips": r0.get("entry_diff_pips"), "M0_pre_asian_close": r0["falls_before_asian_close_utc"],
        "M1_status": r1["mapping_status"], "M1_time_delta_min": r1.get("time_delta_minutes"),
        "M1_entry_diff_pips": r1.get("entry_diff_pips"), "M1_pre_asian_close": r1["falls_before_asian_close_utc"],
    })
json.dump(delta_table, open("per_event_delta_table.json", "w"), indent=2, default=str)
for d in delta_table:
    print(d["ref_id"], d["date"], d["direction"], "| M0:", d["M0_status"], d["M0_time_delta_min"], d["M0_entry_diff_pips"],
          "| M1:", d["M1_status"], d["M1_time_delta_min"], d["M1_entry_diff_pips"])
