"""Step 3 of scripts/host/GO_LIVE.md: live candle smoke test. It is also the scheduled-task runner.

    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py                 # --mode smoke
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode fx       # Task: FX cycles
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode crypto   # Task: crypto daily
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode lsmc     # Task: daily six-symbol Large-SMC watch
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode lsmc-weekend   # legacy/manual bounded crypto probe

- smoke: pulls the last closed D1/H1/M15/M5 bars for EURUSD and GBPUSD (plus USDJPY and
  XAUUSD once host metadata is captured), classifies each as FRESH / STALE /
  MARKET_CLOSED, runs the FX ticket builder (both frozen cycles) and the Large-SMC 1.1.0
  watch once, and archives to journal/host_smoke (ARCHIVE_ONLY; never sends). It prints
  states only.
- fx / crypto / lsmc are the scheduled modes. Each is window-bounded in UTC from the frozen
  configs, which makes it DST-safe whatever the host's local time zone. Each is
  single-instance (lock file in logs/), serialized on one cross-process MT5 lock (MT5_BUSY
  after 60 s), bounded by per-call MT5 timeouts and a 120 s whole-run TIMEOUT self-exit,
  and idempotent: every FX decision (including DATA_ERROR/BLOCKED) is archived when its
  content changes. Only fresh, complete READY tickets with host metadata and a passing
  spread check create 1R paper-ledger entries. Optional message-only Telegram delivery
  covers READY tickets and OPPORTUNITY alerts, and only if the host-local override enables it.

Read-only: MT5 candles come from _host_common.host_fetch (closed bars, timestamps converted
with the owner-stated server-time rule: server midnight = New York 17:00). Crypto tickets
follow the runner config version (--crypto-config, default config/v1_tickets/
crypto_ticket_v3.yaml: VT Markets MT5 BTCUSD/ETHUSD, weekdays 09:00-12:00 America/New_York plus
Sat/Sun 21:00-23:00 UTC; version 2 (weekdays only) stays selectable;
version 1, public perp klines in the frozen 06:30-06:45 UTC window, stays selectable).
There are no order, position or account-mutation calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import (  # noqa: E402
    REPO_ROOT, AlreadyRunning, Mt5Busy, call_with_timeout, host_fetch, host_quote, import_mt5, log_line,
    mt5_access_lock, mt5_initialize, require_demo_account, single_instance, start_run_watchdog, utcnow,
)


def _argv_mode(argv: List[str]) -> str:
    for i, a in enumerate(argv):
        if a.startswith("--mode="):
            return a.split("=", 1)[1]
        if a == "--mode" and i + 1 < len(argv):
            return argv[i + 1]
    return "smoke"


if __name__ == "__main__":   # bound the whole process, including the heavy imports below (pandas: ~15 s cold)
    start_run_watchdog(f"ag_v1_{_argv_mode(sys.argv[1:])}")

from host_delivery import telegram_message as tg  # noqa: E402
from large_smc_watch import WatchTracker, evaluate_snapshot  # noqa: E402
from large_smc_watch.watch import fx_market_closed  # noqa: E402
from runtime_state.store import JsonKeyValueStore  # noqa: E402
from strategy_engine import load_strategy  # noqa: E402
from v1_tickets import fx as fx_tickets  # noqa: E402
from v1_tickets.paper import archive_paper_trade, build_paper_trade, paper_eligibility  # noqa: E402

UTC = dt.timezone.utc
# Binding objective universe: three FX majors + gold.  Never silently remove a symbol
# when metadata is missing; its scheduled cycle must emit an explicit DATA_ERROR instead.
FX_MAJORS = ("EURUSD", "GBPUSD", "USDJPY")
FX_METALS = ("XAUUSD",)
FX_TICKET_SYMBOLS = FX_MAJORS + FX_METALS
TF_MIN = {"D1": 1440, "H1": 60, "M15": 15, "M5": 5}
COUNTS = {"D1": 30, "H1": 200, "M15": 120, "M5": 300}
STALE_MIN = 15
Fetch = Callable[[str, str, int], list]
Quote = Callable[[str], Optional[tuple]]


def _reason(exc: BaseException) -> str:
    return getattr(exc, "code", None) or type(exc).__name__


def _spread(quote: Optional[Quote], broker: str) -> Optional[float]:
    try:
        q = quote(broker) if quote is not None else None
    except Exception:  # noqa: BLE001 -- no quote: the spread gate fails closed (no READY)
        return None
    return None if q is None else float(q[1]) - float(q[0])


def fx_symbols() -> List[str]:
    """The complete objective universe; unavailable symbols fail visibly per cycle."""
    return list(FX_TICKET_SYMBOLS)


def classify(symbol: str, m5: list, now: dt.datetime) -> str:
    if symbol not in ("BTCUSDT", "ETHUSDT") and fx_market_closed(now):
        return "MARKET_CLOSED"
    if not m5:
        return "NO_DATA"
    age = now - (m5[-1].time + dt.timedelta(minutes=5))
    return "STALE" if age > dt.timedelta(minutes=STALE_MIN) else "FRESH"


def _hhmm(value) -> dt.time:
    return value if isinstance(value, dt.time) else dt.time(*map(int, str(value).split(":")))


def cycle_windows(now: dt.datetime) -> Dict[str, dict]:
    """UTC windows of the frozen ST_ASIAN_SWEEP_5R_V1 session pairs (GMT in the YAML)."""
    out = {}
    day = now.astimezone(UTC).date()
    for pair in load_strategy(fx_tickets.STRATEGY_PATH).session_pairs:
        at = lambda t: dt.datetime.combine(day, _hhmm(t), tzinfo=UTC)  # noqa: E731
        out[pair.pair_id] = {"ref": (at(pair.reference_session.start_time_gmt), at(pair.reference_session.end_time_gmt)),
                             "trade": (at(pair.trade_session.start_time_gmt), at(pair.trade_session.end_time_gmt))}
    return out


def fx_ticket_for(symbol: str, cycle: str, m15: list, now: dt.datetime, data_close: Optional[dt.datetime] = None,
                  spread: Optional[float] = None) -> dict:
    w = cycle_windows(now)[cycle]
    (rs, re_), (ts, te) = w["ref"], w["trade"]
    session = [c for c in m15 if rs <= c.time < re_]
    post = [c for c in m15 if ts <= c.time < te and c.time + dt.timedelta(minutes=15) <= now]
    expected = int((re_ - rs).total_seconds() // 900)
    return fx_tickets.build_fx_ticket(symbol, cycle, rs.date(), session, expected, post,
                                      data_source="MT5_VT_MARKETS_DEMO", evaluated_at=now,
                                      data_close=data_close, spread=spread)


def _content_hash(d: dict) -> str:
    stable = {k: v for k, v in d.items() if k not in ("evaluated_at",)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


def archive_if_changed(state: JsonKeyValueStore, key: str, ticket: dict, archive: Callable[[dict], str]) -> bool:
    h = _content_hash(ticket)
    if state.get(key) == h:
        return False
    archive(ticket)
    state.put(key, h)
    return True


def _notify(kind: str, value: str, text: str, root: str) -> None:
    if tg.should_send(kind, value, root):
        try:
            tg.send_message(text)
        except tg.TelegramSendError as exc:
            log_line("telegram", f"TELEGRAM_SEND_FAILED {kind}={value} {exc}")
        else:
            log_line("telegram", f"TELEGRAM_SENT_OK {kind}={value}")


def _archive_fx_result(state: JsonKeyValueStore, journal: str, ticket: dict, now: dt.datetime) -> tuple[bool, bool, list[str]]:
    """Archive every scanner result, then project only eligible READY tickets to paper.

    Returns ``(ticket_archived, paper_opened, paper_ineligibility_reasons)``.  Archive
    failure propagates: notification and paper projection must never continue after a
    decision could not be persisted.
    """
    archive_root = os.path.join(journal, "ticket_delivery", "archive")
    key = f"fx:{ticket['symbol']}:{ticket['cycle']}:{ticket['session_date']}"
    new = archive_if_changed(state, key, ticket, lambda x: fx_tickets.archive_fx_ticket(x, archive_root))
    eligible, reasons, _ = paper_eligibility(ticket, now)
    paper_opened = False
    if new and eligible:
        paper = build_paper_trade(ticket, now)
        paper_key = f"paper:{paper['paper_trade_id']}" if paper is not None else ""
        if paper is not None and state.get(paper_key) is None:
            archive_paper_trade(paper, journal)
            state.put(paper_key, "ARCHIVED")
            paper_opened = True
    return new, paper_opened, reasons


def archive_fx_runtime_failure(now: dt.datetime, journal: str, reason: str, detail: str,
                               *, gated: bool = True, cycle_filter: Optional[str] = None) -> List[str]:
    """Persist per-symbol DATA_ERROR decisions when MT5 fails before candle acquisition."""
    lines: List[str] = []
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    for cycle, w in cycle_windows(now).items():
        if cycle_filter and cycle != cycle_filter:
            continue
        ts, te = w["trade"]
        if gated and not (ts <= now <= te + dt.timedelta(minutes=30)):
            continue
        for symbol in fx_symbols():
            ticket = fx_tickets.build_fx_error_ticket(
                symbol, cycle, ts.date(), evaluated_at=now, reason_code=reason, detail=detail,
            )
            new, _, _ = _archive_fx_result(state, journal, ticket, now)
            lines.append(f"FX {symbol} {cycle} decision=DATA_ERROR reason={reason}{' ARCHIVED' if new else ''}")
    return lines


def run_fx(fetch: Fetch, now: dt.datetime, journal: str, gated: bool, notify: bool = True,
           quote: Optional[Quote] = None, cycle_filter: Optional[str] = None) -> List[str]:
    lines = []
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    windows = cycle_windows(now)
    if cycle_filter is not None and cycle_filter not in windows:
        raise ValueError(f"unknown FX cycle {cycle_filter!r}")
    for cycle, w in windows.items():
        if cycle_filter and cycle != cycle_filter:
            continue
        ts, te = w["trade"]
        if gated and not (ts <= now <= te + dt.timedelta(minutes=30)):
            continue
        for symbol in fx_symbols():
            broker = None
            try:
                broker = fx_tickets.broker_symbol(symbol)
                m15 = fetch(broker, "M15", COUNTS["M15"])
                m5 = fetch(broker, "M5", 12)
            except Exception as exc:  # noqa: BLE001
                ticket = fx_tickets.build_fx_error_ticket(
                    symbol, cycle, ts.date(), evaluated_at=now,
                    reason_code=_reason(exc), detail=str(exc),
                )
                new, _, _ = _archive_fx_result(state, journal, ticket, now)
                lines.append(f"FX {symbol} {cycle} decision=DATA_ERROR reason={_reason(exc)}"
                             f" detail={str(exc)[:160]}{' ARCHIVED' if new else ''}")
                continue
            status = classify(symbol, m5, now)
            if gated and status == "MARKET_CLOSED":
                ticket = fx_tickets.build_fx_error_ticket(
                    symbol, cycle, ts.date(), evaluated_at=now, decision="BLOCKED",
                    reason_code="MARKET_CLOSED", detail="FX market is closed",
                )
                new, _, _ = _archive_fx_result(state, journal, ticket, now)
                lines.append(f"FX {symbol} {cycle} decision=BLOCKED reason=MARKET_CLOSED"
                             f"{' ARCHIVED' if new else ''}")
                continue
            ticket = fx_ticket_for(
                symbol, cycle, m15, now,
                data_close=m5[-1].time + dt.timedelta(minutes=5) if m5 else None,
                spread=_spread(quote, broker),
            )
            new, paper_opened, paper_reasons = _archive_fx_result(state, journal, ticket, now)
            paper_status = "OPENED" if paper_opened else (
                "ALREADY_RECORDED" if not paper_reasons
                else "INELIGIBLE:" + ",".join(paper_reasons)
            )
            lines.append(f"FX {symbol} ({broker}) {cycle} data={status} decision={ticket['decision']}"
                         f" reason={ticket['reason_code']} spread_check={ticket.get('spread_check', '-')}"
                         f" metadata={ticket['metadata_status']} paper={paper_status}"
                         f"{' ARCHIVED' if new else ''}")
            if new and notify:
                _notify("TICKET", ticket["decision"], tg.format_ticket(ticket), REPO_ROOT)
    return lines


LSMC_WEEKEND_DAYS = (6, 7)                                   # ISO Sat, Sun (UTC)
LSMC_WEEKEND_UTC = (dt.time(20, 45), dt.time(23, 15))        # start inclusive, end exclusive


def lsmc_weekend_open(now: dt.datetime) -> bool:
    u = now.astimezone(UTC)
    return u.isoweekday() in LSMC_WEEKEND_DAYS and LSMC_WEEKEND_UTC[0] <= u.time() < LSMC_WEEKEND_UTC[1]


def run_lsmc(fetch: Fetch, now: dt.datetime, journal: str, crypto_feed=None, notify: bool = True,
             fx: bool = True, window: Optional[str] = None) -> List[str]:
    tracker = WatchTracker(os.path.join(journal, "large_smc_watch", "state.json"),
                           os.path.join(journal, "ticket_delivery", "archive"))
    lines = []
    for symbol in (fx_symbols() if fx else []):
        try:
            broker = fx_tickets.broker_symbol(symbol)
            bars = {tf: fetch(broker, tf, COUNTS[tf]) for tf in ("D1", "H1", "M5")}
        except Exception as exc:  # noqa: BLE001
            lines.append(f"LSMC {symbol} DATA_ERROR {_reason(exc)}")
            continue
        lines += _watch_once(tracker, symbol, bars, now, notify)
    if crypto_feed is not None:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            try:
                b = crypto_feed.fetch_bundle(symbol, [("H1", COUNTS["H1"]), ("M5", COUNTS["M5"])])
            except Exception as exc:  # noqa: BLE001
                lines.append(f"LSMC {symbol} DATA_ERROR {type(exc).__name__}")
                continue
            lines += _watch_once(tracker, symbol, {"D1": [], **b.candles}, now, notify, source=b.source,
                                 window=window)
    return lines


def _watch_once(tracker, symbol, bars, now, notify, source="MT5_VT_MARKETS_DEMO", window=None) -> List[str]:
    snap = evaluate_snapshot(symbol, bars["D1"], bars["H1"], bars["M5"], now)
    events = tracker.poll(snap)
    out = [f"LSMC {symbol} data={classify(symbol, bars['M5'], now)} state={snap.state} source={source} "
           f"{f'window={window} ' if window else ''}alerts={[e.to_state + ':' + e.alert_level for e in events]}"]
    if notify:
        for e in events:
            price = bars["M5"][-1].close if bars["M5"] else None
            _notify("LSMC", e.alert_level, tg.format_alert(e.__dict__, price=price), REPO_ROOT)
    return out


def run_crypto(now: dt.datetime, journal: str, feed, notify: bool = True, config: Optional[dict] = None) -> List[str]:
    from v1_tickets.crypto import archive_crypto_ticket, build_crypto_ticket
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    obs = (now.astimezone(UTC) - dt.timedelta(days=1)).date()
    lines = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        t = build_crypto_ticket(symbol, obs, now, feed=feed, state_dir=os.path.join(journal, "v1_crypto"),
                                config=config)
        if t["decision"] == "BLOCKED":
            lines.append(f"CRYPTO {symbol} OUTSIDE_WINDOW ({t['window_status']})")
            continue
        window = f":{t['window']}" if t.get("window") else ""          # v3+: WEEKDAY / WEEKEND kept apart
        new = archive_if_changed(state, f"crypto:{symbol}:{obs.isoformat()}{window}", t,
                                 lambda x: archive_crypto_ticket(x, os.path.join(journal, "ticket_delivery", "archive")))
        detail = f" detail={t['detail'][:160]}" if t["decision"] == "DATA_ERROR" and t.get("detail") else ""
        lines.append(f"CRYPTO {symbol} decision={t['decision']} reason={','.join(t.get('reason_codes') or [])}"
                     f" source={t['data_source']}{f' window={window[1:]}' if window else ''}{detail}"
                     f"{' ARCHIVED' if new else ''}")
        if new and notify:
            _notify("TICKET", t["decision"], tg.format_ticket(t), REPO_ROOT)
    return lines


def lsmc_crypto_feed(config: dict, fetch: Fetch, quote: Optional[Quote] = None):
    """Large-SMC crypto watch reads the ticket venue (VT Markets MT5 BTCUSD/ETHUSD) only. The
    public perp feed is never used in scheduled runs: a non-MT5 config skips crypto (None)."""
    return crypto_feed_for(config, fetch, quote) if config["venue"]["kind"] == "MT5" else None


def crypto_feed_for(config: dict, fetch: Optional[Fetch], quote: Optional[Quote] = None):
    from v1_tickets.crypto import Mt5CryptoFeed
    venue = config["venue"]
    if venue["kind"] == "MT5":
        return Mt5CryptoFeed(fetch, venue["symbols"], venue["source_id"], quote=quote)
    from execution_runtime.public_crypto_feed import FallbackPublicCryptoFeed
    return FallbackPublicCryptoFeed()


def run_smoke(fetch: Fetch, now: dt.datetime, journal: str, crypto_config: Optional[dict] = None,
              quote: Optional[Quote] = None) -> List[str]:
    lines = []
    crypto_map = (crypto_config or {}).get("venue", {}).get("symbols", {}) if (
        (crypto_config or {}).get("venue", {}).get("kind") == "MT5") else {}
    for symbol in fx_symbols() + list(crypto_map):
        try:
            broker = crypto_map.get(symbol) or fx_tickets.broker_symbol(symbol)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"BARS {symbol} DATA_ERROR {_reason(exc)}")
            continue
        got = {}
        for tf in ("D1", "H1", "M15", "M5"):
            try:
                got[tf] = fetch(broker, tf, 3)
            except Exception as exc:  # noqa: BLE001
                got[tf] = []
                lines.append(f"BARS {symbol} {tf} DATA_ERROR {_reason(exc)}")
        last = {tf: (b[-1].time.isoformat() if b else None) for tf, b in got.items()}
        lines.append(f"BARS {symbol} ({broker}) status={classify(symbol, got['M5'], now)} last_closed={last}")
    lines += run_fx(fetch, now, journal, gated=False, notify=False, quote=quote)
    lines += run_lsmc(fetch, now, journal, crypto_feed=None, notify=False)
    if crypto_map:
        lines += run_crypto(now, journal, crypto_feed_for(crypto_config, fetch, quote), notify=False, config=crypto_config)
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("smoke", "fx", "crypto", "lsmc", "lsmc-weekend"), default="smoke")
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH", ""))
    ap.add_argument("--crypto-config", default=None, help="crypto ticket config version YAML (default: active V3)")
    ap.add_argument("--cycle", choices=fx_tickets.V1_CYCLES, default=None,
                    help="limit FX mode to one session cycle (scheduler compatibility)")
    args = ap.parse_args(argv)
    if args.cycle and args.mode != "fx":
        ap.error("--cycle is only valid with --mode fx")
    log_name = f"ag_v1_{args.mode}"
    now = utcnow()
    journal = os.path.join(REPO_ROOT, "journal", "host_smoke" if args.mode == "smoke" else "")
    from v1_tickets.crypto import ACTIVE_CONFIG, load_ticket_config
    crypto_config = load_ticket_config(args.crypto_config or ACTIVE_CONFIG, REPO_ROOT)
    try:
        with single_instance(log_name):
            if args.mode == "crypto" and crypto_config["venue"]["kind"] != "MT5":
                lines = run_crypto(now, journal, crypto_feed_for(crypto_config, None), config=crypto_config)
            elif args.mode == "lsmc-weekend" and not lsmc_weekend_open(now):
                lines = ["LSMC_WEEKEND OUTSIDE_WINDOW (Sat/Sun 20:45-23:15 UTC)"]    # no MT5 access
            elif args.mode == "lsmc-weekend" and crypto_config["venue"]["kind"] != "MT5":
                lines = ["LSMC_WEEKEND SKIPPED (crypto venue is not VT MT5; public feed not used)"]
            else:
                mt5 = import_mt5()
                if mt5 is None:
                    message = "MetaTrader5 package missing -- run scripts/host/diagnose_mt5.py"
                    lines = (archive_fx_runtime_failure(now, journal, "MT5_PACKAGE_MISSING", message,
                                                        cycle_filter=args.cycle)
                             if args.mode == "fx" else [])
                    for line in lines:
                        log_line(log_name, line)
                    print(message)
                    return 1
                with mt5_access_lock():
                    ok, err = mt5_initialize(mt5, args.terminal_path)
                    if not ok:
                        lines = (archive_fx_runtime_failure(now, journal, "MT5_INITIALIZE_FAILED", err,
                                                            cycle_filter=args.cycle)
                                 if args.mode == "fx" else [])
                        for line in lines:
                            log_line(log_name, line)
                        log_line(log_name, f"MT5_INITIALIZE_FAILED {err}")
                        return 1
                    try:
                        demo_ok, demo_status = require_demo_account(mt5)
                        if not demo_ok:
                            lines = (archive_fx_runtime_failure(now, journal, "DEMO_ACCOUNT_REQUIRED", demo_status,
                                                                cycle_filter=args.cycle)
                                     if args.mode == "fx" else [])
                            for line in lines:
                                log_line(log_name, line)
                            log_line(log_name, f"DEMO_ACCOUNT_REQUIRED {demo_status}")
                            return 1
                        fetch, quote = host_fetch(mt5), host_quote(mt5)
                        if args.mode == "crypto":
                            lines = run_crypto(now, journal, crypto_feed_for(crypto_config, fetch, quote),
                                               config=crypto_config)
                        elif args.mode == "smoke":
                            lines = run_smoke(fetch, now, journal, crypto_config, quote)
                        elif args.mode == "fx":
                            lines = run_fx(fetch, now, journal, gated=True, quote=quote,
                                           cycle_filter=args.cycle)
                        elif args.mode == "lsmc-weekend":      # BTCUSD/ETHUSD only, VT MT5 data
                            lines = run_lsmc(fetch, now, journal, crypto_feed=lsmc_crypto_feed(crypto_config, fetch, quote),
                                             fx=False, window="WEEKEND")
                        else:
                            lines = run_lsmc(fetch, now, journal, crypto_feed=lsmc_crypto_feed(crypto_config, fetch, quote))
                    finally:
                        try:
                            call_with_timeout(mt5.shutdown)
                        except Exception:  # noqa: BLE001 -- a stuck shutdown must not hold the run
                            pass
    except AlreadyRunning:
        print(f"ALREADY_RUNNING {log_name}")
        return 0
    except Mt5Busy as exc:
        if args.mode == "fx":
            for line in archive_fx_runtime_failure(now, journal, "MT5_BUSY", str(exc), cycle_filter=args.cycle):
                log_line(log_name, line)
        log_line(log_name, f"MT5_BUSY {exc}")
        return 0
    for line in lines or [f"{args.mode.upper()} NOTHING_IN_WINDOW"]:
        log_line(f"ag_v1_{args.mode}", line)
    return 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)   # hard exit: a lingering MT5/HTTP thread must not keep the task alive after main()
