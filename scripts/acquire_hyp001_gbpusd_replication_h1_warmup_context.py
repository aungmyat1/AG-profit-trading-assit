"""AG SSC HYP_001_GBPUSD_REPLICATION_R1 -- pre-2026-08-03 GBPUSD H1 WARMUP-CONTEXT
acquisition.

READ-ONLY export of H1 candles strictly BEFORE the frozen GBPUSD replication decision
window (2026-08-03T00:00:00Z), for use ONLY as structure/bias state-initialization
context -- never as a source of occurrences, trades, or economic outcomes.

Mirrors scripts/acquire_hyp002_h1_warmup_context.py's acquisition discipline exactly
(read-only MT5 export, no trading function called, immutable raw file + hash +
gap/integrity report), substituting GBPUSD for EURUSD and the GBPUSD replication
lane's own decision-window start (2026-08-03T00:00:00Z, matching
SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914's GBPUSD admission, whose first admitted
bar is 2026-08-03 00:00:00 -- one calendar day later than the EURUSD side).

No trading function is called (no order_send/order_check/symbol_select).
"""
import csv
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5

PACKAGE_ID = "SSC_HYP001_GBPUSD_R1_H1_WARMUP_CONTEXT_20260528_20260802"
PKG_ROOT = os.path.join("data", "research", "ssc_fresh_dev", PACKAGE_ID)
RAW_DIR = os.path.join(PKG_ROOT, "raw")

SYMBOL = "GBPUSD"
PULL_START = datetime(2026, 5, 28, 0, 0, 0)
PULL_END = datetime(2026, 8, 2, 23, 59, 59)
DECISION_WINDOW_START = datetime(2026, 8, 3, 0, 0, 0, tzinfo=timezone.utc)
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

if len(rows) < REQUIRED_H1_BARS:
    raise SystemExit(f"INSUFFICIENT_WARMUP: {len(rows)} bars < required {REQUIRED_H1_BARS}")

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

admission_report = {
    "package_id": PACKAGE_ID,
    "symbol": SYMBOL,
    "role": "WARMUP_CONTEXT_ONLY",
    "broker_server": ai.server,
    "pull_start_server_naive": str(PULL_START),
    "pull_end_server_naive": str(PULL_END),
    "decision_window_start_utc": str(DECISION_WINDOW_START),
    "first_bar": str(times[0]),
    "last_bar": str(times[-1]),
    "bars": len(rows),
    "required_h1_bars": REQUIRED_H1_BARS,
    "duplicates": dup,
    "non_monotonic": non_mono,
    "invalid_ohlc": bad_ohlc,
    "expected_weekend_gaps": expected_gaps,
    "unexpected_gaps": unexpected_gaps,
    "raw_sha256": raw_sha256,
    "no_bar_overlaps_decision_window": True,
    "economic_contribution": 0,
}
report_path = os.path.join(PKG_ROOT, "warmup_admission_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(admission_report, f, indent=2, sort_keys=True)

print(json.dumps(admission_report, indent=2))
mt5.shutdown()
