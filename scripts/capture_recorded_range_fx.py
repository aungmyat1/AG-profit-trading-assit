"""AGP-D1-VT-60D-FX-EXPORT-R2: continuous-range M5/H1/D1 capture for FX (read-only).

Range-mode wrapper around scripts/capture_recorded_ccfd_tfs.py: reuses its read-only
`Terminal`, double-read `stable`, price formatting and output schema (OHLC csv,
`_meta` spread csv, per-symbol provenance json, manifest.json). It drops the PR #128
day-set and M1 cross-check, which do not exist for FX; `m1_check` is NOT_EVALUATED.

Allowed MetaTrader5 calls: initialize, copy_rates_range, symbol_info, account_info,
shutdown. tests/test_capture_recorded_range_fx.py enforces this statically.

- The account pin (config/account_pin.yaml: server, login suffix, DEMO) is confirmed with
  account_info before any rates are read; a mismatch stops the run with no output.
- Window: the latest `--days` calendar days ending at the close of the last D1 bar
  closed at capture time (D1 = broker day, server midnight = 17:00 America/New_York).
- Server time -> UTC with server_utc_offset = New York UTC offset + 7 h (host metadata rule).
- Every timeframe is read twice; differing reads stop the symbol. Bars closing after the
  window end are dropped. Missing grid slots are listed as runs, never filled; runs inside
  the Fri 17:00 - Sun 17:00 New York close are labelled MARKET_CLOSED.
- Warm-up: WARMUP_TRADING_DATES D1 bars before the window start are stored in the same files;
  provenance and manifest record warmup_end_utc (= window start) so evaluation uses only the
  window. 10 = POI max_age_trading_days 5 + a D1 SW-A fractal of 2k+1 = 5 bars (k = 2); this
  also covers ATR14 M5/H1 and sweep_to_choch_window_m5_bars 12 (ST_LARGE_SMC_V1_1_1_2.yaml).
- One symbol per run (resource policy); manifest.json is rebuilt from the folder each run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_recorded_ccfd_tfs import OHLC_HEADER, STEP, Terminal, sha256, stable  # noqa: E402
from capture_recorded_m15 import fmt_price, peak_working_set_mb, redact_host_path  # noqa: E402

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
TFS = ("M5", "H1", "D1")  # strategies/ST_LARGE_SMC_V1_1_1_2.yaml `timeframes:`
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WARMUP_TRADING_DATES = 10
WARMUP_DERIVATION = ("rules.poi.max_age_trading_days 5 + D1 SW-A fractal 2k+1 = 5 bars (rules.swings.k 2); "
                     "covers ATR14 M5/H1 and sweep_to_choch_window_m5_bars 12")
PIN = {"server": "VTMarkets-Demo", "login_suffix": "999", "trade_mode": 0}  # 0 = DEMO


def server_offset_s(utc_ts: int) -> int:
    ny = datetime.fromtimestamp(utc_ts, UTC).astimezone(NY).utcoffset()
    return int(ny.total_seconds()) + 7 * 3600


def to_utc(server_ts: int) -> int:
    guess = server_ts - 3 * 3600
    return server_ts - server_offset_s(server_ts - server_offset_s(guess))


def to_server(utc_ts: int) -> int:
    return utc_ts + server_offset_s(utc_ts)


def market_closed(utc_ts: int) -> bool:
    """Fri 17:00 through Sun 17:00 New York."""
    ny = datetime.fromtimestamp(utc_ts, UTC).astimezone(NY)
    wd, hm = ny.weekday(), ny.hour * 60 + ny.minute
    return (wd == 4 and hm >= 17 * 60) or wd == 5 or (wd == 6 and hm < 17 * 60)


def gap_runs(times: list[int], step: int, lo: int, hi: int) -> list[dict]:
    """Runs of missing grid slots in [lo, hi) for a sorted UTC open-time list."""
    have, runs, cur = set(times), [], None
    for t in range(lo, hi, step):
        if t in have:
            cur = None
            continue
        closed = market_closed(t)
        if cur is None or cur["closed"] != closed:  # a run never mixes closed and open slots
            cur = {"from_utc": t, "to_utc": t, "missing": 0, "closed": closed}
            runs.append(cur)
        cur["to_utc"], cur["missing"] = t, cur["missing"] + 1
    return [{"from_utc": iso(r["from_utc"]), "to_utc": iso(r["to_utc"]), "missing": r["missing"],
             "kind": "MARKET_CLOSED" if r["closed"] else "GAP"} for r in runs]


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def check_pin(acct) -> None:
    if acct is None or acct.server != PIN["server"] or str(acct.login)[-3:] != PIN["login_suffix"] \
            or acct.trade_mode != PIN["trade_mode"]:
        raise SystemExit("ACCOUNT_PIN_MISMATCH: terminal is not the pinned VTMarkets-Demo ...999 DEMO account")


def last_closed_d1_end(term: Terminal, broker: str, now_utc: int) -> int:
    lo = to_server(now_utc - 10 * 86400)
    bars = term.rates(broker, "D1", lo, to_server(now_utc))
    closes = [to_utc(b[0]) + 86400 for b in bars if to_utc(b[0]) + 86400 <= now_utc]
    if not closes:
        raise SystemExit(f"{broker}: no closed D1 bar in the last 10 days")
    return max(closes)


def warmup_start(term: Terminal, broker: str, start: int) -> int:
    bars = term.rates(broker, "D1", to_server(start - 40 * 86400), to_server(start) - 86400)
    opens = sorted(t for t in (to_utc(b[0]) for b in bars) if t < start)
    if len(opens) < WARMUP_TRADING_DATES:
        raise SystemExit(f"{broker}: fewer than {WARMUP_TRADING_DATES} D1 bars before the window")
    return opens[-WARMUP_TRADING_DATES]


def capture(term: Terminal, canonical: str, meta_rec: dict, days: int, now: datetime) -> tuple:
    broker = meta_rec["broker_symbol"]
    point = float(meta_rec["fields"]["point"])
    digits, live_point = term.info(broker)
    now_utc = int(now.timestamp())
    end = last_closed_d1_end(term, broker, now_utc)
    start = end - days * 86400
    w0 = warmup_start(term, broker, start)
    out, meta, tf_rep = {}, {}, {}
    for tf in TFS:
        step = STEP[tf]
        bars = stable(term, broker, tf, to_server(w0), to_server(end) - step)
        if bars is None:
            raise SystemExit(f"{broker} {tf}: unstable read (two reads differ)")
        rows = sorted((to_utc(b[0]),) + b[1:] + (b[0],) for b in bars)
        rows = [r for r in rows if w0 <= r[0] and r[0] + step <= end]
        out[tf] = [",".join([iso(r[0])] + [fmt_price(x, digits) for x in r[1:5]]) for r in rows]
        meta[tf] = [",".join([iso(r[0]), str(r[5]), fmt_price(r[5] * point, digits), "NOT_EVALUATED"]
                             + ([datetime.fromtimestamp(r[6], UTC).strftime("%Y-%m-%d")] if tf == "D1" else []))
                    for r in rows]
        # D1 opens at 17:00 New York, so its grid starts at the warm-up start itself.
        runs = gap_runs([r[0] for r in rows], step, w0, end)
        tf_rep[tf] = {"bars": len(rows), "warmup_bars": sum(r[0] < start for r in rows),
                      "window_bars": sum(r[0] >= start for r in rows), "first_bar_utc": iso(rows[0][0]) if rows else None,
                      "last_bar_utc": iso(rows[-1][0]) if rows else None,
                      "gaps": [g for g in runs if g["kind"] == "GAP"],
                      "market_closed_runs": sum(g["kind"] == "MARKET_CLOSED" for g in runs)}
    rep = {"source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-D1-VT-60D-FX-EXPORT-R2",
           "symbol": canonical, "broker_symbol": broker, "recorded": True,
           "captured_at_utc": now.isoformat(), "digits": digits, "point_host": point,
           "point_live": live_point, "window_start_utc": iso(start), "window_end_utc": iso(end),
           "window_days": days, "warmup_start_utc": iso(w0), "warmup_end_utc": iso(start),
           "warmup_trading_dates": WARMUP_TRADING_DATES, "warmup_derivation": WARMUP_DERIVATION, "server_utc_offset_rule": meta_rec.get("server_utc_offset_rule"),
           "spread_source": "MqlRates spread (points) x host_captured point", "timeframes": tf_rep}
    return out, meta, rep


def write_manifest(out_dir: str, warmup_end_utc: str, window_end_utc: str) -> str:
    files = {n: sha256(os.path.join(out_dir, n)) for n in sorted(os.listdir(out_dir))
             if n != "manifest.json" and os.path.isfile(os.path.join(out_dir, n))}
    path = os.path.join(out_dir, "manifest.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"source": "MT5_VT_MARKETS_DEMO", "mission": "AGP-D1-VT-60D-FX-EXPORT-R2",
                            "warmup_end_utc": warmup_end_utc, "window_end_utc": window_end_utc,
                            "evaluate_from_utc": warmup_end_utc, "sha256": files}, indent=1, sort_keys=True) + "\n")
    return sha256(path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--symbol", required=True, help="canonical symbol, e.g. USDJPY")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--metadata-dir", default=os.path.join(ROOT, "config", "symbol_metadata", "host_captured"))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH"))
    args = p.parse_args(argv)
    with open(os.path.join(args.metadata_dir, f"{args.symbol}.json"), encoding="utf-8") as f:
        meta_rec = json.load(f)
    now = datetime.now(UTC)
    term = Terminal(args.terminal_path)
    try:
        acct = term.mt5.account_info()
        check_pin(acct)
        out, meta, rep = capture(term, args.symbol, meta_rec, args.days, now)
        rep["server"], rep["login_suffix"] = acct.server, PIN["login_suffix"]
    finally:
        term.close()
    os.makedirs(args.out_dir, exist_ok=True)
    files = {}
    for tf in TFS:
        path = os.path.join(args.out_dir, f"{args.symbol}_{tf.lower()}.csv")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(OHLC_HEADER + "".join(r + "\n" for r in out[tf]))
        files[os.path.basename(path)] = sha256(path)
        path = os.path.join(args.out_dir, f"{args.symbol}_{tf.lower()}_meta.csv")
        head = "timestamp_utc,spread_points,spread_price,m1_check" + (",server_date" if tf == "D1" else "")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(head + "\n" + "".join(r + "\n" for r in meta[tf]))
        files[os.path.basename(path)] = sha256(path)
    rep["files"] = files
    rep["terminal"] = redact_host_path(args.terminal_path)
    rep["peak_working_set_mb"] = peak_working_set_mb()
    with open(os.path.join(args.out_dir, f"{args.symbol}_provenance.json"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(args.symbol, rep["broker_symbol"], rep["warmup_start_utc"], "|", rep["window_start_utc"], "->", rep["window_end_utc"])
    for tf, r in rep["timeframes"].items():
        print(" ", tf, r["bars"], "warmup", r["warmup_bars"], r["first_bar_utc"], r["last_bar_utc"], "gaps", len(r["gaps"]),
              "closed_runs", r["market_closed_runs"])
    print("MANIFEST_SHA256", write_manifest(args.out_dir, rep["warmup_end_utc"], rep["window_end_utc"]), "PEAK_WORKING_SET_MB", rep["peak_working_set_mb"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
