"""AGP-C24 D-LSMC-6 evidence on the recorded 60d VT FX replay (read-only, evidence only).

D-LSMC-6: POI max age is counted in distinct New York 17:00 trading dates (weekends excluded), not
calendar days (contract rules.poi.max_age_unit DISTINCT_NY1700_TRADING_DATES, max_age_trading_days 5,
expiry_instant START_OF_THE_TRADING_DATE_AFTER_THE_LAST_VALID_TRADING_DATE).

Independent of the engine: from the replay's signal events (`<root>/<SYM>/shard_NN/signal_events.jsonl`)
and the recorded H1 bars, for every POI the engine EXPIRED, re-derive the expiry instant from the
POI's origin time (the start of the trading date after the 6th distinct observed weekday trading date,
origin included) and require that the first event listing the POI as expired is at/after that instant
and that no event before it lists the POI as expired. A POI shown as the active POI at/after its
expiry instant is also a FAIL. Weekend-spanning POIs (calendar age > trading age) are counted.

    python scripts/lsmc_v113_dlsmc6_evidence.py --root <replay root> --out <report.json>
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

FX = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
DATA = Path(__file__).resolve().parents[1] / "tests/fixtures/vt_recorded_60d_fx"
NY = ZoneInfo("America/New_York")
MAX_AGE = 5


def trading_date(at: dt.datetime) -> dt.date:
    return (at.astimezone(NY) + dt.timedelta(hours=7)).date()


def date_start(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day - dt.timedelta(days=1), dt.time(17), tzinfo=NY).astimezone(dt.timezone.utc)


def expected_expiry(origin: dt.datetime, h1_times: list) -> dt.datetime:
    dates = sorted({trading_date(t) for t in h1_times if t >= origin} | {trading_date(origin)})
    dates = [d for d in dates if d.weekday() < 5]
    last_valid = dates[MAX_AGE] if len(dates) > MAX_AGE else None
    if last_valid is None:
        return None
    nxt = last_valid + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return date_start(nxt)


def check(root: Path) -> dict:
    out = {"schema": "AGP_C24_LSMC_V113_D_LSMC_6_V1", "max_age_trading_days": MAX_AGE, "symbols": {}}
    for symbol in FX:
        files = sorted((root / symbol).glob("shard_*/signal_events.jsonl"))
        if not files:
            out["symbols"][symbol] = {"verdict": "NOT_RUN"}
            continue
        with (DATA / f"{symbol}_h1.csv").open() as stream:
            h1 = [dt.datetime.fromisoformat(r["timestamp_utc"]) for r in csv.DictReader(stream)]
        events = [json.loads(line) for f in files for line in f.open()]
        events.sort(key=lambda e: e["evaluated_at_utc"])
        first_expired, last_active = {}, {}
        for e in events:
            at = dt.datetime.fromisoformat(e["evaluated_at_utc"])
            for poi_id in e["snapshot"].get("expired_poi_ids") or []:
                first_expired.setdefault(poi_id, at)
            poi = e["snapshot"].get("poi")
            if poi:
                last_active[poi["poi_id"]] = at
        cases, fails, weekend = [], [], 0
        for poi_id, seen in sorted(first_expired.items()):
            origin = dt.datetime.fromisoformat(poi_id.split(":", 4)[4])
            expiry = expected_expiry(origin, h1)
            calendar_days = (trading_date(seen) - trading_date(origin)).days
            spans_weekend = calendar_days > MAX_AGE + 1
            weekend += spans_weekend
            active_after = last_active.get(poi_id)
            ok = expiry is not None and seen >= expiry and not (active_after and active_after >= expiry)
            row = {"poi_id": poi_id, "origin_utc": origin.isoformat(),
                   "expected_expiry_utc": expiry.isoformat() if expiry else None,
                   "first_expired_event_utc": seen.isoformat(), "spans_weekend": spans_weekend,
                   "last_active_event_utc": active_after.isoformat() if active_after else None,
                   "verdict": "PASS" if ok else "FAIL"}
            cases.append(row)
            if not ok:
                fails.append(row)
        out["symbols"][symbol] = {
            "verdict": "FAIL" if fails else ("PASS" if cases else "INSUFFICIENT"),
            "expired_pois": len(cases), "weekend_spanning_expired_pois": weekend,
            "fail_cases": fails, "sample_weekend_cases": [c for c in cases if c["spans_weekend"]][:5]}
    verdicts = [v["verdict"] for v in out["symbols"].values()]
    out["verdict"] = "FAIL" if "FAIL" in verdicts else "PASS" if all(v == "PASS" for v in verdicts) else "INCOMPLETE"
    out["method_note"] = ("Signal events are written on state changes only, so the first expired listing is an upper "
                          "bound on the engine's expiry instant; the check is that it is never earlier than the "
                          "independently derived instant and that the POI is never active at/after it.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    report = check(Path(args.root))
    Path(args.out).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({s: {k: v.get(k) for k in ("verdict", "expired_pois", "weekend_spanning_expired_pois")}
                      for s, v in report["symbols"].items()}))
    return 1 if report["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
