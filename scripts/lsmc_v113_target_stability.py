"""AGP-C24 independent C11 target-stability check for ST_LARGE_SMC_V1@1.1.3 (read-only, evidence only).

Independent of the replay runner's in-loop check: reads only the per-scan rows the runner wrote
(`<root>/<SYMBOL>/shard_NN/scans.csv`), groups them by opportunity id across ALL shards, and requires that
the C11 target recorded when the watch is created (its first scan) equals the target on every later scan
while the watch is present (until it closes or expires). Any change in the target price, its source, or the
full target-selection hash is DRIFT -> FAIL with the case listed. Missing shards are reported, never PASS.

    python scripts/lsmc_v113_target_stability.py --root <replay root> --out <report.json>
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SYMBOLS = ("BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
SHARDS = 6  # every symbol's recorded window is 6 shards of <= 10 days (audit.json `shard_count` when present)


def check(root: Path) -> dict:
    out = {"schema": "AGP_C24_LSMC_V113_TARGET_STABILITY_V1", "symbols": {}}
    for symbol in SYMBOLS:
        rows, missing = [], []
        if not (root / symbol).is_dir():
            out["symbols"][symbol] = {"verdict": "NOT_RUN", "missing_shards": list(range(SHARDS)), "watches": 0,
                                      "watch_scans": 0, "multi_scan_watches": 0, "drift_cases": []}
            continue
        audits = sorted((root / symbol).glob("shard_*/audit.json"))
        shards = json.loads(audits[0].read_text()).get("shard_count", SHARDS) if audits else SHARDS
        for shard in range(shards):
            path = root / symbol / f"shard_{shard:02d}" / "scans.csv"
            if not path.is_file():
                missing.append(shard)
                continue
            with path.open(newline="") as stream:
                rows += [r for r in csv.DictReader(stream) if r["opp_id"]]
        rows.sort(key=lambda r: (r["closed_at_utc"], int(r["m5_row"])))
        created, scans, drift = {}, {}, []
        for r in rows:
            fields = (r["target"], r["c11_source"], r["creation_target_sha256"])
            first = created.setdefault(r["opp_id"], {"m5_row": int(r["m5_row"]), "at": r["closed_at_utc"],
                                                     "target": r["target"], "c11_source": r["c11_source"],
                                                     "creation_target_sha256": r["creation_target_sha256"]})
            scans[r["opp_id"]] = scans.get(r["opp_id"], 0) + 1
            if fields != (first["target"], first["c11_source"], first["creation_target_sha256"]):
                drift.append({"opp_id": r["opp_id"], "created": first,
                              "drifted": {"m5_row": int(r["m5_row"]), "at": r["closed_at_utc"], "target": r["target"],
                                          "c11_source": r["c11_source"],
                                          "creation_target_sha256": r["creation_target_sha256"]}})
        verdict = "FAIL" if drift else ("INCOMPLETE" if missing else ("PASS" if created else "INSUFFICIENT"))
        out["symbols"][symbol] = {"verdict": verdict, "missing_shards": missing, "watches": len(created),
                                  "watch_scans": sum(scans.values()),
                                  "multi_scan_watches": sum(1 for n in scans.values() if n > 1),
                                  "drift_cases": drift}
    out["verdict"] = ("FAIL" if any(v["verdict"] == "FAIL" for v in out["symbols"].values()) else
                      "PASS" if all(v["verdict"] == "PASS" for v in out["symbols"].values()) else "INCOMPLETE")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    report = check(Path(args.root))
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({s: {k: v[k] for k in ("verdict", "watches", "multi_scan_watches")}
                      for s, v in report["symbols"].items()}))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
