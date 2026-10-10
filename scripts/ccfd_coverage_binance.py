"""AGP-LANE-B2: COVERAGE_ONLY run of ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0 on Binance-derived bars.

NON-AUTHORITATIVE. Purpose: exercise rule branches the VT recorded data (#128/#131) never hit,
so the coverage matrix shows which branches have *any* executed evidence. Nothing here feeds an
L1-L6 verdict, a ticket, the registry or logic_verified status, and no Binance pair ever
substitutes for the VT CFD (CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN). Output label: COVERAGE_ONLY.

Sources (pinned; all Binance klines as vendored in the freqtrade test suite at FREQTRADE_COMMIT):
  BINANCE_1M_DERIVED  tests/testdata/UNITTEST_BTC-1m.json -- Binance 1m klines of an alt/BTC
                      pair (freqtrade anonymises it as UNITTEST/BTC), 2017-11-04..14. M5 is
                      derived from 1m; a 1m minute without trades is absent upstream, so M5
                      buckets are built from the minutes that exist and incomplete days fail
                      closed (REFERENCE_INCOMPLETE) exactly as on VT data.
  BINANCE_BTCUSDT_5M  tests/testdata/BTC_USDT-5m.feather -- BTC/USDT spot 5m, 2025-11-24..12-04.
  BINANCE_ETHBTC_5M   tests/testdata/ETH_BTC-5m.feather  -- ETH/BTC spot 5m, 2018-01-10..30.
Binance's own endpoints (api.binance.com, data.binance.vision) are unreachable from the build
environment; these are the Binance klines that are. M15/H1/D1 (and M5 from 1m) are derived with
the existing deterministic resampler edge_discovery.replay_c001._resample (UTC buckets; D1 = UTC
day, not the VT server day). Each source is evaluated under the BTCUSD/ETHUSD contract symbol
only because evaluate() accepts no other symbol. Raw files are GPL-licensed upstream and are NOT
committed: they are downloaded to a cache outside the repository and verified by sha256.

    python scripts/ccfd_coverage_binance.py [--cache DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import scripts.ccfd_sweep_retest_replay as R  # noqa: E402
from edge_discovery.replay_c001 import _resample  # noqa: E402
from strategy_engine.session import Candle  # noqa: E402
from v1_tickets import crypto_cfd  # noqa: E402

FREQTRADE_COMMIT = "9a2f03a6bf8408f155591304c78aab20ca5c44cc"
SOURCES = (
    {"id": "BINANCE_1M_DERIVED", "file": "UNITTEST_BTC-1m.json", "interval": "1m", "pair": "UNITTEST/BTC (alt/BTC)",
     "contract_symbol": "BTCUSD",
     "sha256": "8471f9f9bb972f9398c3183d7b7cfe43773b717b54a3ce19194b55918b5615e4"},
    {"id": "BINANCE_BTCUSDT_5M", "file": "BTC_USDT-5m.feather", "interval": "5m", "pair": "BTC/USDT",
     "contract_symbol": "BTCUSD",
     "sha256": "38f89dd1e8a116e5f451e24f7022e1213ab17336da98ef9abc1c38f9bf1850cc"},
    {"id": "BINANCE_ETHBTC_5M", "file": "ETH_BTC-5m.feather", "interval": "5m", "pair": "ETH/BTC",
     "contract_symbol": "ETHUSD",
     "sha256": "f9c807156e870d73d57fa48493ebe38a1a9afc0cc379893888eb7dd07c0c5667"},
)
CACHE = Path.home() / ".cache/ag_ccfd_coverage_only"
OUT = R.OUT_DIR / "coverage_only_binance.json"
COUNTS = {"D1": 50, "H1": 100, "M15": 96, "M5": 576}     # the live cycle's fetch counts (replay report)
UTC = dt.timezone.utc


def url(src: dict) -> str:
    return (f"https://api.github.com/repos/freqtrade/freqtrade/contents/tests/testdata/{src['file']}"
            f"?ref={FREQTRADE_COMMIT}")


def fetch(src: dict, cache: Path) -> Path:
    path = cache / src["file"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url(src), headers={"Accept": "application/vnd.github.raw"})
        with urllib.request.urlopen(req, timeout=60) as resp:   # read-only public file
            path.write_bytes(resp.read())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != src["sha256"]:
        raise SystemExit(f"COVERAGE_SOURCE_SHA256_MISMATCH {src['id']} {digest}")
    return path


def load(src: dict, path: Path) -> Dict[str, object]:
    if src["interval"] == "1m":
        rows = json.loads(path.read_text(encoding="utf-8"))
        m1 = [Candle(dt.datetime.fromtimestamp(r[0] / 1000, UTC), *map(float, r[1:5])) for r in rows]
        m5 = _resample(m1, 5, m1[-1].time + dt.timedelta(minutes=1))
    else:
        import pandas as pd

        frame = pd.read_feather(path)
        m5 = [Candle(t.to_pydatetime().astimezone(UTC), float(o), float(h), float(lo), float(c))
              for t, o, h, lo, c in frame[["date", "open", "high", "low", "close"]].itertuples(index=False)]
        if any(b.time - a.time != R.M5 for a, b in zip(m5, m5[1:])):
            raise SystemExit(f"COVERAGE_SOURCE_NOT_CONTIGUOUS {src['id']}")
    end = m5[-1].time + R.M5
    bars = {"M5": m5, "M15": _resample(m5, 15, end), "H1": _resample(m5, 60, end), "D1": _resample(m5, 1440, end)}
    return {"bars": bars, "times": {tf: [c.time for c in rows] for tf, rows in bars.items()}, "spread": {}}


def scan(src: dict, data: dict, cfg, windows, hits: Counter) -> dict:
    per_day = Counter(c.time.date() for c in data["bars"]["M5"])
    days = sorted(d for d in per_day if per_day[d] == 288)          # whole UTC days only
    local, results = Counter(), Counter()
    for day in days:
        day0 = dt.datetime.combine(day, dt.time(), tzinfo=UTC)
        for k in range(288):
            now = day0 + k * R.M5
            x = R.closed_inputs(data, now, COUNTS)
            r = R.engine(src["contract_symbol"], now, x, cfg)
            results[r["result"]] += 1
            win = "IN_WINDOW" if crypto_cfd._window(now, windows) else "OUT_OF_WINDOW"
            events = R.rule_events(r, x, now)
            if k == 287 and r["result"] in ("WAITING_MSS", "WAITING_RETEST"):
                events.add(("signal_expiry_contract.rule_2",
                            "LONG" if r["evidence"]["context"]["direction_permission"] == "LONG_ALLOWED" else "SHORT"))
            local.update((rule, d, win) for rule, d in events)
    hits.update(local)
    return {"id": src["id"], "venue": "BINANCE_SPOT", "pair": src["pair"], "interval": src["interval"],
            "contract_symbol_used": src["contract_symbol"], "url": url(src), "sha256": src["sha256"],
            "first_bar_utc": data["bars"]["M5"][0].time.isoformat(),
            "last_bar_utc": data["bars"]["M5"][-1].time.isoformat(),
            "days_scanned": [d.isoformat() for d in days], "scans": sum(results.values()),
            "scan_results": dict(sorted(results.items())),
            "exercised_cells": len([1 for v in local.values() if v])}


def run(cache: Path = CACHE) -> dict:
    cfg = R.load_market_structure_config()
    _, windows = crypto_cfd._config()
    hits: Counter = Counter()
    sources = [scan(src, load(src, fetch(src, cache)), cfg, windows, hits) for src in SOURCES]
    matrix = R.coverage_matrix(hits)
    return {
        "label": "COVERAGE_ONLY", "authoritative": False,
        "feeds_logic_verdict": False, "feeds_registry": False, "feeds_tickets": False,
        "instrument_note": "Binance spot pairs evaluated under a contract symbol only to run the rules; never a "
                           "substitute for VT BTCUSD/ETHUSD CFD evidence",
        "interval_note": "requested Binance 1m: one 1m-derived source; Binance endpoints unreachable, the other "
                         "sources are the finest reachable Binance klines (5m)",
        "derivation": "edge_discovery.replay_c001._resample (UTC buckets; D1 = UTC day)",
        "freqtrade_commit": FREQTRADE_COMMIT, "raw_data_committed": False,
        "sources": sources, "scans": sum(s["scans"] for s in sources),
        "rule_coverage": matrix, "not_exercised": R.coverage_gaps(matrix), "ORDER_API_CALLS": 0,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", type=Path, default=CACHE)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)
    report = run(args.cache)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    for s in report["sources"]:
        print(s["id"], s["scans"], s["scan_results"])
    print("not_exercised", len(report["not_exercised"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
