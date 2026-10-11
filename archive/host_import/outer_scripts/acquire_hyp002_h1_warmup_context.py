"""AG SSC HYP_002 -- pre-2026-08-01 EURUSD H1 WARMUP-CONTEXT acquisition.

READ-ONLY export of H1 candles strictly BEFORE the frozen GEN_002 decision window
(2026-08-01T00:00:00Z), for use ONLY as structure/bias state-initialization context --
never as a source of occurrences, trades, or economic outcomes. Owner-approved this
session (explicit decision: "acquire and use pre-2026-08-01 EURUSD H1 history strictly
as WARMUP/STATE-INITIALIZATION CONTEXT... does NOT expand the GEN_002 decision/economic
evaluation interval").

Mirrors the acquisition discipline already used for GEN_002 itself (read-only MT5
export, no trading function called, immutable raw file + hash + gap/integrity report).

No trading function is called (no order_send/order_check/symbol_select).
"""
import csv
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

PACKAGE_ID = "SSC_HYP002_H1_WARMUP_CONTEXT_20260528_20260731"
PKG_ROOT = os.path.join("data", "research", "ssc_fresh_dev", PACKAGE_ID)
RAW_DIR = os.path.join(PKG_ROOT, "raw")

SYMBOL = "EURUSD"
# Strictly before the frozen GEN_002 decision window start -- verified after pull that
# the LAST bar's open time is < 2026-08-01T00:00:00Z (never overlapping the decision
# interval). Start chosen to clear STRUCTURE_WARMUP_H1_BARS=1000 with a ~13% safety
# margin using actual closed bar count, not elapsed calendar hours.
PULL_START = datetime(2026, 5, 28, 0, 0, 0)
PULL_END = datetime(2026, 7, 31, 23, 59, 59)
DECISION_WINDOW_START = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
REQUIRED_H1_BARS = 1000

os.makedirs(RAW_DIR, exist_ok=True)

if not mt5.initialize():
    raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")

ai = mt5.account_info()
ti = mt5.terminal_info()
print("=" * 70)
print(f"MetaTrader5 package version : {mt5.__version__}")
print(f"broker/server               : {ai.server}")
print(f"terminal build              : {ti.build}")
print("=" * 70)

rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_H1, PULL_START, PULL_END)
if rates is None or len(rates) == 0:
    raise SystemExit(f"NO_DATA: {SYMBOL} H1 {PULL_START} -> {PULL_END}")

rows = []
for r in rates:
    ts = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
    if ts >= DECISION_WINDOW_START:
        raise SystemExit(f"WARMUP_OVERLAPS_DECISION_WINDOW: bar at {ts} is >= {DECISION_WINDOW_START}")
    rows.append((ts, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                 int(r["tick_volume"]), int(r["spread"]), int(r["real_volume"])))

rows.sort(key=lambda row: row[0])

raw_path = os.path.join(RAW_DIR, f"{SYMBOL}_H1.csv")
with open(raw_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["timestamp_utc", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])
    for ts, o, h, l, c, tv, sp, rv in rows:
        w.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), o, h, l, c, tv, sp, rv])

# Integrity: strictly increasing, valid OHLC, gap classification (weekend = expected).
times = [r[0] for r in rows]
dup = sum(1 for i in range(1, len(times)) if times[i] == times[i - 1])
non_mono = sum(1 for i in range(1, len(times)) if times[i] < times[i - 1])
bad_ohlc = sum(1 for _, o, h, l, c, *_ in rows if not (h >= max(o, c) and l <= min(o, c) and h >= l))

expected_gaps, unexpected_gaps, gap_details = 0, 0, []
for i in range(1, len(times)):
    delta = (times[i] - times[i - 1]).total_seconds()
    if delta <= 3600:
        continue
    probe = times[i - 1] + timedelta(hours=1)
    weekend = False
    while probe <= times[i]:
        if probe.weekday() == 5:
            weekend = True
            break
        probe += timedelta(hours=1)
    if weekend:
        expected_gaps += 1
    else:
        unexpected_gaps += 1
        gap_details.append({"from": str(times[i - 1]), "to": str(times[i]), "missing_seconds": int(delta - 3600)})

if dup or non_mono or bad_ohlc or unexpected_gaps:
    raise SystemExit(f"INTEGRITY_FAIL: dup={dup} non_mono={non_mono} bad_ohlc={bad_ohlc} "
                      f"unexpected_gaps={unexpected_gaps} details={gap_details[:5]}")

h = hashlib.sha256()
with open(raw_path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
raw_sha256 = h.hexdigest()

closed_bar_count = len(rows)
if closed_bar_count < REQUIRED_H1_BARS:
    raise SystemExit(f"INSUFFICIENT_WARMUP_BARS: {closed_bar_count} < {REQUIRED_H1_BARS}")

manifest = {
    "package_id": PACKAGE_ID,
    "role": "WARMUP_CONTEXT_ONLY",
    "symbol": SYMBOL,
    "timeframe": "H1",
    "source": {
        "broker": ai.server,
        "environment": "DEMO",
        "source_platform": "MT5",
        "source_transport": "MetaTrader5_Python_DIRECT",
        "terminal_build": ti.build,
        "metatrader5_package_version": mt5.__version__,
        "trading_function_called": False,
    },
    "first_timestamp": times[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
    "last_timestamp": times[-1].strftime("%Y-%m-%dT%H:%M:%SZ"),
    "closed_bar_count": closed_bar_count,
    "raw_file": raw_path.replace("\\", "/"),
    "raw_file_sha256": raw_sha256,
    "dataset_fingerprint": f"sha256:{raw_sha256}",
    "decision_window_start": DECISION_WINDOW_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "strategy_warmup_requirement": {
        "constant": "STRUCTURE_WARMUP_H1_BARS", "value": REQUIRED_H1_BARS,
        "unit": "ACTUAL_CLOSED_H1_BARS_NOT_CALENDAR_HOURS",
        "margin": closed_bar_count - REQUIRED_H1_BARS,
    },
    "integrity": {
        "duplicates": dup, "non_monotonic": non_mono, "invalid_ohlc": bad_ohlc,
        "expected_weekend_gaps": expected_gaps, "unexpected_gaps": unexpected_gaps,
        "bars_at_or_after_decision_window_start": 0,
    },
    "usage_restrictions": [
        "CONTEXT_ONLY -- H1 structure/bias state initialization only",
        "MUST NOT create occurrences before decision_window_start",
        "MUST NOT create trades before decision_window_start",
        "MUST NOT contribute economic outcomes",
        "MUST NOT be used to initialize state for any decision using bars at/after that decision's own timestamp",
    ],
}
manifest_path = os.path.join(PKG_ROOT, "warmup_context_manifest.json")
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)

print(json.dumps(manifest, indent=2, sort_keys=True))
print(f"\nWARMUP_ACQUISITION_STATUS = PASS, closed_bar_count={closed_bar_count}, margin={closed_bar_count - REQUIRED_H1_BARS}")
