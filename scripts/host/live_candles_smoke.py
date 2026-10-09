"""Step 3 of scripts/host/GO_LIVE.md: live candle smoke test. It is also the scheduled-task runner.

    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py                 # --mode smoke
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode fx --canonical # scheduled canonical FX cycles
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode fx       # legacy/manual compatibility path
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode crypto   # Task: crypto daily
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode lsmc     # Task: daily six-symbol Large-SMC watch
    .venv\\Scripts\\python.exe scripts\\host\\live_candles_smoke.py --mode lsmc-weekend   # legacy/manual bounded crypto probe

- smoke: pulls the last closed D1/H1/M15/M5 bars for EURUSD and GBPUSD (plus USDJPY and
  XAUUSD once host metadata is captured), classifies each as FRESH / STALE /
  MARKET_CLOSED, runs the FX ticket builder (both frozen cycles) and the Large-SMC 1.1.0
  watch once, and archives to journal/host_smoke (ARCHIVE_ONLY; never sends). It prints
  states only.
- The installed FX task uses `--mode fx --canonical`: it preserves `run_manual_jobs`, then
  evaluates only the active frozen FX cycle through `daily_evaluator`, appends canonical results
  to TICKET_STORE_V1, and uses the separate durable delivery/session journal. `--mode fx`
  without `--canonical` remains the unscheduled legacy compatibility path. Crypto/LSMC scheduled
  modes remain separate. All are UTC-window-bounded, single-instance, serialized on the shared
  MT5 lock, per-call time-bounded, and bounded by the 120 s whole-run TIMEOUT. Canonical Telegram
  delivery is off unless local recipient authorization and the environment enable/allowlist agree.

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
from canonical_fx_delivery import (  # noqa: E402
    active_cycles, build_sender, failure_provider,
    process_due_session_summaries, run_canonical_fx_cycle,
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
from host_delivery.lsmc_alert_dedup import AlertLedger, DELIVERY_UNCERTAIN, deliver_once  # noqa: E402
from large_smc_watch import WatchTracker, evaluate_snapshot  # noqa: E402
from large_smc_watch.watch import fx_market_closed  # noqa: E402
from runtime_state.store import JsonKeyValueStore  # noqa: E402
from strategy_engine import load_strategy  # noqa: E402
from v1_tickets import fx as fx_tickets  # noqa: E402
from mt5.symbol_resolver import SymbolMeta  # noqa: E402
from v1_tickets import manual_ticket  # noqa: E402
from v1_tickets.code_identity import code_sha  # noqa: E402
from v1_tickets.paper import archive_paper_trade, build_paper_trade, paper_eligibility  # noqa: E402
from v1_tickets.scan_record import (  # noqa: E402
    adapterless_scan_records, append_jsonl, build_scan_record, classify_fx_ticket, write_scan_record,
)

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


def cycle_windows(now: dt.datetime) -> Dict[str, dict]:
    """UTC windows of the frozen ST_ASIAN_SWEEP_5R_V1 session pairs (GMT in the YAML)."""
    return fx_tickets.session_windows_utc(now.astimezone(UTC).date())


def _fx_inputs(cycle: str, m15: list, now: dt.datetime):
    w = cycle_windows(now)[cycle]
    (rs, re_), (ts, te) = w["ref"], w["trade"]
    session = [c for c in m15 if rs <= c.time < re_]
    post = [c for c in m15 if ts <= c.time < te and c.time + dt.timedelta(minutes=15) <= now]
    return rs.date(), session, int((re_ - rs).total_seconds() // 900), post


def fx_ticket_for(symbol: str, cycle: str, m15: list, now: dt.datetime, data_close: Optional[dt.datetime] = None,
                  spread: Optional[float] = None) -> dict:
    day, session, expected, post = _fx_inputs(cycle, m15, now)
    return fx_tickets.build_fx_ticket(symbol, cycle, day, session, expected, post,
                                      data_source="MT5_VT_MARKETS_DEMO", evaluated_at=now,
                                      data_close=data_close, spread=spread)


def manual_ticket_for(symbol: str, cycle: str, m15: list, now: dt.datetime, data_close: Optional[dt.datetime],
                      spread: Optional[float], balance: Optional[float], live_meta: Optional[SymbolMeta] = None) -> dict:
    """Manual Trade Ticket V1: same inputs as fx_ticket_for, plus owner risk, read-only balance and
    sizing metadata (live symbol_info first, captured snapshot only as a stamped fallback)."""
    day, session, expected, post = _fx_inputs(cycle, m15, now)
    meta, provenance = manual_ticket.resolve_symbol_meta(symbol, live_meta, now)
    return manual_ticket.build_manual_ticket(
        symbol, cycle, day, session, expected, post, now=now, data_close=data_close, spread=spread,
        owner=manual_ticket.load_owner_config(), balance=balance, meta=meta, meta_provenance=provenance)


def live_symbol_meta(mt5, broker: str) -> Optional[SymbolMeta]:
    """Read-only symbol_info(broker) -> SymbolMeta; None on any failure (caller falls back/fails closed)."""
    try:
        i = call_with_timeout(mt5.symbol_info, broker)
        if i is None:
            return None
        return SymbolMeta(symbol=broker, tick_size=float(i.trade_tick_size), tick_value=float(i.trade_tick_value),
                          contract_size=float(i.trade_contract_size), volume_min=float(i.volume_min),
                          volume_max=float(i.volume_max), volume_step=float(i.volume_step), digits=int(i.digits),
                          point=float(i.point), trade_stops_level=int(i.trade_stops_level),
                          trade_freeze_level=int(i.trade_freeze_level))
    except Exception:  # noqa: BLE001
        return None


def account_balance(mt5) -> Optional[float]:
    """Read-only account_info().balance; None on any failure (sizing then fails closed)."""
    try:
        info = call_with_timeout(mt5.account_info)
        return float(info.balance) if info is not None and info.balance is not None else None
    except Exception:  # noqa: BLE001
        return None


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


DELIVERY_DIR = os.path.join("ticket_delivery", "delivery_status")


def _notify(kind: str, value: str, text: str, root: str, journal: Optional[str] = None,
            ref: Optional[str] = None, now: Optional[dt.datetime] = None) -> str:
    """Best-effort Telegram delivery (TELEGRAM_DELIVERY_TRACE_R1). Callers persist the scan /
    ticket record first; this never raises, so a Telegram or policy failure cannot hide a scan
    record or stop the remaining symbols. The status is persisted separately (append-only JSONL,
    when a journal is given). Only sanitized fields are kept: no token, chat id, URL or text.

    Returns the legacy journal status, except that an ambiguous transport outcome (timeout,
    5xx, unknown) is returned as DELIVERY_UNCERTAIN: the durable row keeps its frozen FAILED /
    ERROR vocabulary, but a deduplicating caller must never treat the send as a known failure
    that may be retried."""
    error = None
    # The persisted journal keeps its frozen status vocabulary (SENT / NOT_SENT_POLICY / FAILED /
    # ERROR); the conservative typed transport outcome is reported in the telegram log only, so
    # an ambiguous 5xx/timeout is distinguishable from a definite rejection without changing the
    # durable row schema.
    typed = None
    try:
        if not tg.should_send(kind, value, root):
            status = "NOT_SENT_POLICY"
        else:
            tg.send_message(text)
            status = "SENT"
    except tg.TelegramSendError as exc:
        status, error, typed = "FAILED", str(exc), exc.delivery_state  # message is sanitized
    except Exception as exc:  # noqa: BLE001 -- unknown transport outcome is conservatively ambiguous
        status, error, typed = "ERROR", type(exc).__name__, "DELIVERY_UNCERTAIN"
    if status != "NOT_SENT_POLICY":
        log_line("telegram", f"TELEGRAM_{'SENT_OK' if status == 'SENT' else 'SEND_' + typed} {kind}={value}"
                             f"{' ' + error if error else ''}")
    if journal:
        at = (now or dt.datetime.now(UTC)).astimezone(UTC)
        try:
            append_jsonl(os.path.join(journal, DELIVERY_DIR, f"{at.date().isoformat()}.jsonl"),
                         {"channel": "telegram", "kind": kind, "value": value, "ref": ref, "status": status,
                          "error": error, "recorded_at": at.isoformat(), "code_sha": code_sha()})
        except OSError as exc:
            log_line("telegram", f"DELIVERY_STATUS_WRITE_FAILED {kind}={value} {type(exc).__name__}")
    return DELIVERY_UNCERTAIN if typed == DELIVERY_UNCERTAIN else status


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


def fx_run_id(now: dt.datetime) -> str:
    return f"fx:{now.astimezone(UTC):%Y%m%dT%H%M%SZ}"


def _scan_fx(journal: str, run_id: str, cycle: str, window: dict, ticket: dict, now: dt.datetime,
             data_close: Optional[dt.datetime] = None) -> str:
    """Manual Trade Ticket V1 Phase 3: one scan record per symbol per run, even with nothing found."""
    state, stage, reason = classify_fx_ticket(ticket, now=now, window_end=window["trade"][1])
    write_scan_record(journal, build_scan_record(
        run_id=run_id, session=cycle, symbol=ticket["symbol"], strategy_id=ticket["strategy_id"],
        strategy_version=ticket["strategy_version"], window=window["trade"], data_close=data_close,
        state=state, stage=stage, stop_reason=reason, now=now))
    return state


def _scan_adapterless(journal: str, run_id: str, cycle: str, window: dict, now: dt.datetime) -> None:
    for rec in adapterless_scan_records(run_id=run_id, cycle=cycle, now=now, window=window["trade"]):
        write_scan_record(journal, rec)


def archive_fx_runtime_failure(now: dt.datetime, journal: str, reason: str, detail: str,
                               *, gated: bool = True, cycle_filter: Optional[str] = None) -> List[str]:
    """Persist per-symbol DATA_ERROR decisions when MT5 fails before candle acquisition."""
    lines: List[str] = []
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    run_id = fx_run_id(now)
    for cycle, w in cycle_windows(now).items():
        if cycle_filter and cycle != cycle_filter:
            continue
        ts, te = w["trade"]
        if gated and not (ts <= now <= te + dt.timedelta(minutes=30)):
            continue
        _scan_adapterless(journal, run_id, cycle, w, now)
        for symbol in fx_symbols():
            ticket = fx_tickets.build_fx_error_ticket(
                symbol, cycle, ts.date(), evaluated_at=now, reason_code=reason, detail=detail,
            )
            new, _, _ = _archive_fx_result(state, journal, ticket, now)
            _scan_fx(journal, run_id, cycle, w, ticket, now)
            lines.append(f"FX {symbol} {cycle} decision=DATA_ERROR reason={reason}{' ARCHIVED' if new else ''}")
    return lines


def run_fx(fetch: Fetch, now: dt.datetime, journal: str, gated: bool, notify: bool = True,
           quote: Optional[Quote] = None, cycle_filter: Optional[str] = None,
           balance: Optional[Callable[[], Optional[float]]] = None,
           symbol_meta: Optional[Callable[[str], Optional[SymbolMeta]]] = None) -> List[str]:
    lines = []
    balance_value: List[Optional[float]] = []
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    windows = cycle_windows(now)
    run_id = fx_run_id(now)
    if cycle_filter is not None and cycle_filter not in windows:
        raise ValueError(f"unknown FX cycle {cycle_filter!r}")
    for cycle, w in windows.items():
        if cycle_filter and cycle != cycle_filter:
            continue
        ts, te = w["trade"]
        if gated and not (ts <= now <= te + dt.timedelta(minutes=30)):
            continue
        _scan_adapterless(journal, run_id, cycle, w, now)
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
                _scan_fx(journal, run_id, cycle, w, ticket, now)
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
                _scan_fx(journal, run_id, cycle, w, ticket, now)
                lines.append(f"FX {symbol} {cycle} decision=BLOCKED reason=MARKET_CLOSED"
                             f"{' ARCHIVED' if new else ''}")
                continue
            data_close = m5[-1].time + dt.timedelta(minutes=5) if m5 else None
            spread = _spread(quote, broker)
            ticket = fx_ticket_for(symbol, cycle, m15, now, data_close=data_close, spread=spread)
            new, paper_opened, paper_reasons = _archive_fx_result(state, journal, ticket, now)
            if not balance_value:
                balance_value.append(balance() if balance is not None else None)
            manual = manual_ticket_for(symbol, cycle, m15, now, data_close, spread, balance_value[0],
                                       symbol_meta(broker) if symbol_meta is not None else None)
            manual_new = archive_if_changed(state, f"manual:{manual['ticket_id']}", manual,
                                            lambda x: manual_ticket.archive_manual_ticket(journal, x))
            write_scan_record(journal, build_scan_record(
                run_id=run_id, session=cycle, symbol=symbol, strategy_id=manual["strategy_id"],
                strategy_version=manual["strategy_version"], window=w["trade"], data_close=data_close,
                state=manual["state"], stage=manual["stage_reached"], stop_reason=manual["stop_reason"],
                now=now, ticket_id=manual["ticket_id"] if manual.get("direction") else None,
                block_reasons=manual["block_reasons"], warnings=manual.get("warnings", ())))
            if manual_new and notify and manual["state"] == "TICKET_READY":
                _notify(tg.MANUAL_TICKET, tg.MANUAL_TICKET_READY, manual_ticket.render_text(manual), REPO_ROOT,
                        journal=journal, ref=f"manual:{manual['ticket_id']}", now=now)
            paper_status = "OPENED" if paper_opened else (
                "ALREADY_RECORDED" if not paper_reasons
                else "INELIGIBLE:" + ",".join(paper_reasons)
            )
            lines.append(f"FX {symbol} ({broker}) {cycle} data={status} decision={ticket['decision']}"
                         f" reason={ticket['reason_code']} spread_check={ticket.get('spread_check', '-')}"
                         f" metadata={ticket['metadata_status']} paper={paper_status}"
                         f"{' ARCHIVED' if new else ''}")
            if new and notify:
                _notify("TICKET", ticket["decision"], tg.format_ticket(ticket), REPO_ROOT, journal=journal,
                        ref=f"fx:{symbol}:{cycle}:{ticket['session_date']}", now=now)
    return lines


MANUAL_LOOKBACK_DAYS = 7
MANUAL_RESOLVER_M5_BARS = 2400          # ~8 days of M5, enough for the look-back plus a weekend


def run_manual_jobs(fetch: Fetch, now: dt.datetime, journal: str) -> List[str]:
    """Manual Trade Ticket V1 daily jobs on the existing FX task (no parallel scheduler):
    auto-EXPIRED owner decisions every run; the VIRTUAL_FORWARD outcome resolver once per UTC day
    (first FX run of the day, i.e. before the 07:00 UTC window). Read-only bars; no order path."""
    from v1_tickets.outcome import resolve_day
    from v1_tickets.owner_decision import expire_undecided
    from v1_tickets.scan_record import read_jsonl

    lines: List[str] = []
    state = JsonKeyValueStore(os.path.join(journal, "v1_host_state.json"))
    days = [now.date() - dt.timedelta(days=i) for i in range(MANUAL_LOOKBACK_DAYS + 1)]
    for day in days:
        rows = read_jsonl(manual_ticket.ticket_path(journal, day))
        for e in expire_undecided(journal, rows, now):
            lines.append(f"MANUAL {e['symbol']} {e['session']} {e['ticket_id']} decision=EXPIRED (auto)")
    key = f"manual_resolver:{now.date().isoformat()}"
    if state.get(key) is None:
        cache: Dict[str, list] = {}

        def bars(symbol: str) -> list:
            if symbol not in cache:
                cache[symbol] = fetch(fx_tickets.broker_symbol(symbol), "M5", MANUAL_RESOLVER_M5_BARS)
            return cache[symbol]
        for day in days[1:]:
            try:
                summary = resolve_day(journal, day, bars, now=now)
            except Exception as exc:  # noqa: BLE001 -- data failure leaves tickets pending for the next day
                lines.append(f"MANUAL_RESOLVER {day} ERROR {_reason(exc)}")
                continue
            if summary["resolved"] or summary["pending"]:
                lines.append(f"MANUAL_RESOLVER {day} resolved={len(summary['resolved'])} "
                             f"pending={len(summary['pending'])} tag=VIRTUAL_FORWARD")
        state.put(key, "DONE")
    report_key = f"manual_report:{now.date().isoformat()}"
    if now >= manual_report_after_utc(now) and state.get(report_key) is None:
        from post_asian_pilot.report_archive import write_report
        from v1_tickets.manual_report import REPORT_TYPE, build_report
        report = build_report(journal, now.date(), now=now, expected=manual_expected())
        path = write_report(REPORT_TYPE, now.date(), report, root=os.path.join(journal, "reports"))
        state.put(report_key, path)
        lines.append(f"MANUAL_REPORT {now.date()} tickets_ready={report['tickets_ready']} "
                     f"missing_records={len(report['system_health']['missing_records'])} archived")
    return lines


def manual_report_after_utc(now: dt.datetime) -> dt.datetime:
    """After the last frozen session window closes, plus the FX task's 30 min grace."""
    return max(w["trade"][1] for w in cycle_windows(now).values()) + dt.timedelta(minutes=30)


def manual_expected() -> Dict[tuple, List[str]]:
    from v1_tickets.scan_record import adapterless_scan_records
    strategy = load_strategy(fx_tickets.STRATEGY_PATH)
    out: Dict[tuple, List[str]] = {(f"{strategy.strategy_id}@{strategy.version}", c): fx_symbols()
                                   for c in fx_tickets.V1_CYCLES}
    for cycle in fx_tickets.V1_CYCLES:
        recs = adapterless_scan_records(run_id="expected", cycle=cycle, now=utcnow())
        if recs:
            out[(recs[0].strategy, cycle)] = [r.symbol for r in recs]
    return out


LSMC_WEEKEND_DAYS = (6, 7)                                   # ISO Sat, Sun (UTC)
LSMC_WEEKEND_UTC = (dt.time(20, 45), dt.time(23, 15))        # start inclusive, end exclusive


def lsmc_weekend_open(now: dt.datetime) -> bool:
    u = now.astimezone(UTC)
    return u.isoweekday() in LSMC_WEEKEND_DAYS and LSMC_WEEKEND_UTC[0] <= u.time() < LSMC_WEEKEND_UTC[1]


def run_lsmc(fetch: Fetch, now: dt.datetime, journal: str, crypto_feed=None, notify: bool = True,
             fx: bool = True, window: Optional[str] = None) -> List[str]:
    tracker = WatchTracker(os.path.join(journal, "large_smc_watch", "state.json"),
                           os.path.join(journal, "ticket_delivery", "archive"))
    ledger = AlertLedger(os.path.join(journal, "large_smc_watch", "delivered_confirmations.json"))
    lines = []
    for symbol in (fx_symbols() if fx else []):
        try:
            broker = fx_tickets.broker_symbol(symbol)
            bars = {tf: fetch(broker, tf, COUNTS[tf]) for tf in ("D1", "H1", "M5")}
        except Exception as exc:  # noqa: BLE001
            lines.append(f"LSMC {symbol} DATA_ERROR {_reason(exc)}")
            continue
        lines += _watch_once(tracker, symbol, bars, now, notify, ledger=ledger, journal=journal,
                             display_broker_symbol=broker)
    if crypto_feed is not None:
        for symbol in ("BTCUSDT", "ETHUSDT"):
            try:
                b = crypto_feed.fetch_bundle(symbol, [("H1", COUNTS["H1"]), ("M5", COUNTS["M5"])])
            except Exception as exc:  # noqa: BLE001
                lines.append(f"LSMC {symbol} DATA_ERROR {type(exc).__name__}")
                continue
            broker = getattr(crypto_feed, "symbols", {}).get(symbol)
            lines += _watch_once(tracker, symbol, {"D1": [], **b.candles}, now, notify, source=b.source,
                                 window=window, ledger=ledger, journal=journal,
                                 display_broker_symbol=broker)
    return lines


def _watch_once(tracker, symbol, bars, now, notify, source="MT5_VT_MARKETS_DEMO", window=None,
                ledger=None, journal=None, display_broker_symbol=None) -> List[str]:
    snap = evaluate_snapshot(symbol, bars["D1"], bars["H1"], bars["M5"], now)
    events = tracker.poll(snap)
    out = [f"LSMC {symbol} data={classify(symbol, bars['M5'], now)} state={snap.state} source={source} "
           f"{f'window={window} ' if window else ''}alerts={[e.to_state + ':' + e.alert_level for e in events]}"]
    if notify:
        for event in events:
            price = bars["M5"][-1].close if bars["M5"] else None
            payload = dict(event.__dict__)
            if display_broker_symbol:
                payload["display_broker_symbol"] = display_broker_symbol
            text = tg.format_alert(payload, price=price)
            status = deliver_once(
                event.__dict__, ledger,
                lambda e=event, message=text: _notify(
                    "LSMC", e.alert_level, message, REPO_ROOT, journal=journal,
                    ref=e.reference_id, now=now),
            )
            if status not in ("SENT", "NOT_SENT_POLICY"):
                out.append(f"LSMC_DELIVERY {symbol} {status} reference={event.reference_id}")
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
            _notify("TICKET", t["decision"], tg.format_ticket(t), REPO_ROOT, journal=journal,
                    ref=f"crypto:{symbol}:{obs.isoformat()}{window}", now=now)
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
    ap.add_argument("--canonical", action="store_true",
                    help="use the canonical FX evaluator/TICKET_STORE/delivery path (scheduled FX mode)")
    args = ap.parse_args(argv)
    if args.cycle and args.mode != "fx":
        ap.error("--cycle is only valid with --mode fx")
    if args.canonical and args.mode != "fx":
        ap.error("--canonical is only valid with --mode fx")
    log_name = f"ag_v1_{args.mode}"
    now = utcnow()
    journal = os.path.join(REPO_ROOT, "journal", "host_smoke" if args.mode == "smoke" else "")
    canonical_sender = (build_sender(journal, root=REPO_ROOT)
                        if args.mode == "fx" and args.canonical else None)
    from v1_tickets.crypto import ACTIVE_CONFIG, load_ticket_config, window_status
    crypto_config = load_ticket_config(args.crypto_config or ACTIVE_CONFIG, REPO_ROOT)

    # MT5-backed crypto jobs must be window-gated before either the runner lock or the
    # host-wide MT5 lock. The ticket evaluator applies the same config window later, but
    # evaluating it only after attach needlessly starts MT5 outside the authorized window.
    if args.mode == "crypto" and crypto_config["venue"]["kind"] == "MT5":
        status = window_status(crypto_config, now.date(), now)
        if status != "IN_WINDOW":
            line = f"CRYPTO OUTSIDE_WINDOW ({status})"
            log_line(log_name, line)
            return 0

    def canonical_failure_lines(reason: str) -> List[str]:
        if canonical_sender is None:
            return []
        details = {
            "MT5_PACKAGE_MISSING": "MetaTrader5 package unavailable",
            "MT5_INITIALIZE_FAILED": "MT5 initialization failed",
            "DEMO_ACCOUNT_REQUIRED": "verified Demo account not confirmed",
            "MT5_BUSY": "host-wide MT5 data lock unavailable",
        }
        _, failures = run_canonical_fx_cycle(
            failure_provider(reason, details.get(reason, "host prerequisite unavailable")),
            now=now, journal=journal, sender=canonical_sender,
            cycles=active_cycles(now, args.cycle), cycle_filter=args.cycle,
            ticket_source="REPLAY", fx_data_source="NONE", policy_root=REPO_ROOT)
        return failures + process_due_session_summaries(now, journal=journal, sender=canonical_sender)

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
                    lines = (canonical_failure_lines("MT5_PACKAGE_MISSING") if args.canonical else
                             archive_fx_runtime_failure(now, journal, "MT5_PACKAGE_MISSING", message,
                                                        cycle_filter=args.cycle)) if args.mode == "fx" else []
                    for line in lines:
                        log_line(log_name, line)
                    print(message)
                    return 1
                with mt5_access_lock():
                    ok, err = mt5_initialize(mt5, args.terminal_path)
                    if not ok:
                        lines = (canonical_failure_lines("MT5_INITIALIZE_FAILED") if args.canonical else
                                 archive_fx_runtime_failure(now, journal, "MT5_INITIALIZE_FAILED", err,
                                                            cycle_filter=args.cycle)) if args.mode == "fx" else []
                        for line in lines:
                            log_line(log_name, line)
                        log_line(log_name, f"MT5_INITIALIZE_FAILED {err}")
                        return 1
                    try:
                        demo_ok, demo_status = require_demo_account(mt5)
                        if not demo_ok:
                            lines = (canonical_failure_lines("DEMO_ACCOUNT_REQUIRED") if args.canonical else
                                     archive_fx_runtime_failure(now, journal, "DEMO_ACCOUNT_REQUIRED", demo_status,
                                                                cycle_filter=args.cycle)) if args.mode == "fx" else []
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
                            manual_lines = run_manual_jobs(fetch, now, journal)
                            if args.canonical:
                                from live_eval_smoke import GuardedMT5, snapshot_provider
                                provider = snapshot_provider(GuardedMT5(mt5))
                                _, canonical_lines = run_canonical_fx_cycle(
                                    provider, now=now, journal=journal, sender=canonical_sender,
                                    cycles=active_cycles(now, args.cycle), cycle_filter=args.cycle,
                                    ticket_source="LIVE", fx_data_source="MT5_VT_MARKETS_DEMO",
                                    policy_root=REPO_ROOT)
                                summary_lines = process_due_session_summaries(
                                    now, journal=journal, sender=canonical_sender)
                                lines = manual_lines + canonical_lines + summary_lines
                            else:
                                lines = manual_lines + run_fx(
                                    fetch, now, journal, gated=True, quote=quote, cycle_filter=args.cycle,
                                    balance=lambda: account_balance(mt5),
                                    symbol_meta=lambda broker: live_symbol_meta(mt5, broker))
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
            failure_lines = (canonical_failure_lines("MT5_BUSY") if args.canonical else
                             archive_fx_runtime_failure(now, journal, "MT5_BUSY", str(exc), cycle_filter=args.cycle))
            for line in failure_lines:
                log_line(log_name, line)
        log_line(log_name, f"MT5_BUSY {exc}")
        return 0
    for line in lines or [f"{args.mode.upper()} NOTHING_IN_WINDOW"]:
        log_line(f"ag_v1_{args.mode}", line)
    return 0


def flush_std_streams() -> None:
    """sys.stdout / sys.stderr are None under pythonw.exe (windowless scheduled runs)."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()


if __name__ == "__main__":
    rc = main()
    flush_std_streams()
    os._exit(rc)   # hard exit: a lingering MT5/HTTP thread must not keep the task alive after main()
