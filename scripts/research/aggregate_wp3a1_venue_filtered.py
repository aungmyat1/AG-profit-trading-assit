"""Venue-aware, read-only WP3A.1 aggregation (LSMC_EURUSD_FRICTION_WP3A1_V1).

    python scripts/research/aggregate_wp3a1_venue_filtered.py [--sessions-dir DIR] [--write]

The frozen campaign manifest names one broker server (VantageMarkets-Demo). The
sessions/ directory also holds later VTMarkets-Demo rows written by the same scheduled
tasks after the terminal was switched. The original aggregator
(scripts/aggregate_eurusd_friction_campaign.py) globs every session and is left untouched;
this wrapper selects rows by the frozen venue instead. Source evidence is only read.

Row eligibility (every exclusion is counted with its reason, never silently dropped):
    broker_server == manifest broker                -> ELIGIBLE
    broker_server present but different             -> BROKER_SERVER_MISMATCH
    broker_server missing / empty                   -> BROKER_IDENTITY_MISSING (fail closed)
    campaign_id / symbol differ from the manifest   -> CAMPAIGN_ID_MISMATCH / SYMBOL_MISMATCH
A session containing any BROKER_SERVER_MISMATCH row is excluded whole (MIXED_OR_FOREIGN_VENUE).
A day is complete when every manifest window has >= samples_per_window_minimum eligible
rows carrying a spread. Statistics use eligible rows of complete days only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CAMPAIGN_DIR = REPO / "artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1"
OUT_DIR = REPO / "artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1"


def classify_row(row: Dict, broker: str, campaign_id: str, symbol: str) -> str:
    server = row.get("broker_server")
    if not server:
        return "BROKER_IDENTITY_MISSING"
    if server != broker:
        return "BROKER_SERVER_MISMATCH"
    if row.get("campaign_id") != campaign_id:
        return "CAMPAIGN_ID_MISMATCH"
    if row.get("symbol") != symbol:
        return "SYMBOL_MISMATCH"
    return "ELIGIBLE"


def _stats(xs: List[float]) -> Dict:
    if not xs:
        return {"N": 0}
    a = np.asarray(xs, dtype=float)
    q = lambda p: float(np.percentile(a, p, method="linear"))  # noqa: E731
    return {"N": len(xs), "min": float(a.min()), "median": q(50), "mean": float(a.mean()), "p75": q(75),
            "p90": q(90), "p95": q(95), "p99": q(99), "max": float(a.max()),
            "zero_fraction": float((a == 0).mean())}


def aggregate(campaign_dir: Path = CAMPAIGN_DIR, sessions_dir: Optional[Path] = None) -> Dict:
    manifest = json.loads((campaign_dir / "campaign_manifest.json").read_text(encoding="utf-8"))
    frozen_hash = json.loads((campaign_dir / "campaign_manifest_hash.json").read_text(encoding="utf-8"))
    recomputed = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if recomputed != frozen_hash["campaign_manifest_hash"]:
        raise ValueError("campaign manifest hash mismatch: frozen campaign voided or altered")
    broker, cid, symbol = manifest["broker"], manifest["campaign_id"], manifest["symbol"]
    per_window_min = manifest["samples_per_window_minimum"]
    windows = [w["window_id"] for w in manifest["windows"]]
    sessions_dir = sessions_dir or campaign_dir / "sessions"

    sessions, row_reasons = [], Counter()
    for raw_path in sorted(sessions_dir.glob("*_raw.jsonl")):
        data = raw_path.read_bytes()
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
        reasons = [classify_row(r, broker, cid, symbol) for r in rows]
        name = raw_path.name
        day, window = name[:10], name[11:].replace("_raw.jsonl", "")
        mixed = "BROKER_SERVER_MISMATCH" in reasons
        eligible = [] if mixed else [r for r, why in zip(rows, reasons) if why == "ELIGIBLE"]
        spreads = [r["spread_pips"] for r in eligible if r.get("spread_pips") is not None and not r.get("missing_reason")]
        row_reasons.update(reasons)
        sessions.append({
            "file": name, "sha256": hashlib.sha256(data).hexdigest(), "day": day, "window_id": window,
            "rows": len(rows), "row_reasons": dict(Counter(reasons)),
            "servers": dict(Counter(str(r.get("broker_server")) for r in rows)),
            "session_status": "EXCLUDED_MIXED_OR_FOREIGN_VENUE" if mixed
            else "EXCLUDED_NO_ELIGIBLE_ROWS" if not eligible else "ELIGIBLE",
            "eligible_rows": len(eligible), "eligible_spread_rows": len(spreads), "_spreads": spreads,
        })

    by_day = defaultdict(dict)
    for s in sessions:
        if s["session_status"] == "ELIGIBLE" and s["window_id"] in windows:
            by_day[s["day"]][s["window_id"]] = s
    complete = sorted(d for d, ws in by_day.items()
                      if all(w in ws and ws[w]["eligible_spread_rows"] >= per_window_min for w in windows))
    incomplete = {d: {w: (ws[w]["eligible_spread_rows"] if w in ws else "ABSENT") for w in windows}
                  for d, ws in sorted(by_day.items()) if d not in complete}
    pooled, per_window = [], defaultdict(list)
    for d in complete:
        for w in windows:
            pooled += by_day[d][w]["_spreads"]
            per_window[w] += by_day[d][w]["_spreads"]
    excluded_sessions = [s for s in sessions if s["session_status"] != "ELIGIBLE"]
    for s in sessions:
        s.pop("_spreads")
    return {
        "schema": "AG_WP3A1_VENUE_FILTERED_AGGREGATE_V1",
        "campaign_id": cid, "campaign_manifest_hash": recomputed, "manifest_hash_verified": True,
        "VENUE_FILTER": f"broker_server == {broker!r} (frozen campaign manifest)",
        "sessions_dir": str(sessions_dir),
        "day_rule": f"every manifest window has >= {per_window_min} eligible spread rows",
        "WP3A1_VANTAGE_VALID_DAYS": complete,
        "WP3A1_VANTAGE_VALID_OBSERVATIONS": len(pooled),
        "minimum_population": manifest["required_minimum_population"],
        "minimum_met": len(complete) >= manifest["minimum_trading_days"]
        and len(pooled) >= manifest["required_minimum_population"]["total_minimum_observations"],
        "incomplete_days": incomplete,
        "row_exclusions": {k: v for k, v in sorted(row_reasons.items()) if k != "ELIGIBLE"},
        "VT_ROWS_EXCLUDED_FROM_WP3A1": sum(s["rows"] for s in excluded_sessions
                                           if any("VTMarkets" in k for k in s["servers"])),
        "excluded_sessions": [{"file": s["file"], "status": s["session_status"], "servers": s["servers"]}
                              for s in excluded_sessions],
        "spread_pips_complete_days": _stats(pooled),
        "spread_pips_by_window": {w: _stats(per_window[w]) for w in windows},
        "sessions": sessions,
        "note": "read-only; source evidence not moved or edited; statistics are descriptive, not a friction policy",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", type=Path, default=None)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    report = aggregate(sessions_dir=args.sessions_dir)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text)
    if args.write:
        path = OUT_DIR / ("WP3A1_VENUE_FILTERED_AGGREGATE_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        with open(path, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
