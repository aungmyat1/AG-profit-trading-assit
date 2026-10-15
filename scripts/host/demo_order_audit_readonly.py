"""Read-only audit of every order/deal on the pinned DEMO account (AGP-DEMO-ORDER-AUDIT).

Reads account/terminal identity, open positions, pending orders and the full order/deal history
through the process-wide read-only guard (src/mt5/readonly_guard.py): order_send/order_check and
every other order_* mutation entry point are refused before they reach MT5. Output is redacted at
capture time: login and ticket suffixes only, no balance/equity, terminal path as <HOST_TERMINAL>.

Attribution: an AG Profit Trading order is one carrying the S1 contract magic (resolved from the
registered strategy contract) or the canonical adapter's comment format "AG <16 hex>". Every other
record is FOREIGN and is labelled from config/demo_execution_host_magics.yaml where known. MT5
history holds only orders the trade server accepted; a request refused client-side (order_send
returning a retcode without a server order) or an order_check never appears here, so local journals
are the only source for those and are reported separately by the caller.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

AG_COMMENT_RE = re.compile(r"^AG [0-9a-f]{16}( |$)")
HISTORY_FROM = dt.datetime(2000, 1, 1)

DEAL_TYPES = {0: "BUY", 1: "SELL", 2: "BALANCE", 3: "CREDIT", 4: "CHARGE", 5: "CORRECTION",
              6: "BONUS", 7: "COMMISSION"}
DEAL_ENTRIES = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}
DEAL_REASONS = {0: "CLIENT", 1: "MOBILE", 2: "WEB", 3: "EXPERT", 4: "SL", 5: "TP", 6: "SO",
                7: "ROLLOVER", 8: "VMARGIN", 9: "SPLIT"}
ORDER_TYPES = {0: "BUY", 1: "SELL", 2: "BUY_LIMIT", 3: "SELL_LIMIT", 4: "BUY_STOP", 5: "SELL_STOP",
               6: "BUY_STOP_LIMIT", 7: "SELL_STOP_LIMIT", 8: "CLOSE_BY"}
ORDER_STATES = {0: "STARTED", 1: "PLACED", 2: "CANCELED", 3: "PARTIAL", 4: "FILLED", 5: "REJECTED",
                6: "EXPIRED", 7: "REQUEST_ADD", 8: "REQUEST_MODIFY", 9: "REQUEST_CANCEL"}
UNCERTAIN_ORDER_STATES = {"STARTED", "REQUEST_ADD", "REQUEST_MODIFY", "REQUEST_CANCEL"}
TRADE_DEAL_TYPES = {"BUY", "SELL"}


def _suffix(value: Any) -> str:
    return str(value)[-4:]


def _server_iso(epoch: Optional[int], offset_s: Optional[int]) -> Dict[str, Optional[str]]:
    """MT5 history times are server wall-clock seconds; UTC is derived with the observed offset."""
    if not epoch:
        return {"server": None, "utc": None}
    server = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc).replace(tzinfo=None)
    utc = (server - dt.timedelta(seconds=offset_s)).isoformat() + "Z" if offset_s is not None else None
    return {"server": server.isoformat(), "utc": utc}


def attribute(magic: Any, comment: Any, s1_magic: int, host_magics: Mapping[int, str]) -> Dict[str, Any]:
    comment = comment or ""
    by_magic = magic == s1_magic
    by_comment = bool(AG_COMMENT_RE.match(comment))
    if by_magic or by_comment:
        return {"owner": "AG_PROFIT_TRADING", "by_magic": by_magic, "by_comment": by_comment}
    return {"owner": "FOREIGN", "foreign_source": host_magics.get(magic, "UNREGISTERED_MAGIC")}


def _row(r: Any, fields: Iterable[str]) -> Dict[str, Any]:
    return {f: getattr(r, f, None) for f in fields}


def classify(*, positions: List[Any], orders: List[Any], hist_orders: List[Any], hist_deals: List[Any],
             s1_magic: int, host_magics: Mapping[int, str], offset_s: Optional[int]) -> Dict[str, Any]:
    """Pure classification of raw MT5 rows into the audit sections (no MT5 access)."""
    def own(r):
        return attribute(getattr(r, "magic", None), getattr(r, "comment", ""), s1_magic, host_magics)

    open_positions = [{"ticket_suffix": _suffix(p.ticket), "symbol": p.symbol,
                       "side": "BUY" if p.type == 0 else "SELL", "volume": p.volume, "magic": p.magic,
                       "opened": _server_iso(p.time, offset_s), **own(p)} for p in positions]
    pending = [{"ticket_suffix": _suffix(o.ticket), "symbol": o.symbol,
                "type": ORDER_TYPES.get(o.type, o.type), "volume": o.volume_current, "magic": o.magic,
                "setup": _server_iso(o.time_setup, offset_s), **own(o)} for o in orders]

    trade_deals = [d for d in hist_deals if DEAL_TYPES.get(d.type) in TRADE_DEAL_TYPES]
    non_trade = Counter(DEAL_TYPES.get(d.type, str(d.type)) for d in hist_deals
                        if DEAL_TYPES.get(d.type) not in TRADE_DEAL_TYPES)
    executed = [{"deal_suffix": _suffix(d.ticket), "order_suffix": _suffix(d.order),
                 "position_suffix": _suffix(d.position_id), "symbol": d.symbol,
                 "side": DEAL_TYPES.get(d.type), "entry": DEAL_ENTRIES.get(d.entry, d.entry),
                 "reason": DEAL_REASONS.get(d.reason, d.reason), "volume": d.volume, "price": d.price,
                 "profit": d.profit, "magic": d.magic, "time": _server_iso(d.time, offset_s), **own(d)}
                for d in trade_deals]

    by_position: Dict[Any, List[Any]] = defaultdict(list)
    for d in trade_deals:
        by_position[d.position_id].append(d)
    open_ids = {p.ticket for p in positions}
    closed = []
    for pid, deals in by_position.items():
        ins = [d for d in deals if DEAL_ENTRIES.get(d.entry) == "IN"]
        outs = [d for d in deals if DEAL_ENTRIES.get(d.entry) in ("OUT", "OUT_BY", "INOUT")]
        if not ins or not outs or pid in open_ids:
            continue
        first = min(ins, key=lambda d: d.time)
        closed.append({"position_suffix": _suffix(pid), "symbol": first.symbol,
                       "side": DEAL_TYPES.get(first.type), "volume_in": sum(d.volume for d in ins),
                       "opened": _server_iso(first.time, offset_s),
                       "closed": _server_iso(max(d.time for d in outs), offset_s),
                       "exit_reasons": sorted({DEAL_REASONS.get(d.reason, str(d.reason)) for d in outs}),
                       "net_profit": round(sum(d.profit + d.commission + d.swap for d in deals), 2),
                       "magic": first.magic, **own(first)})

    states = Counter(ORDER_STATES.get(o.state, str(o.state)) for o in hist_orders)
    rejected = [{"order_suffix": _suffix(o.ticket), "symbol": o.symbol,
                 "type": ORDER_TYPES.get(o.type, o.type), "magic": o.magic,
                 "setup": _server_iso(o.time_setup, offset_s), **own(o)}
                for o in hist_orders if ORDER_STATES.get(o.state) == "REJECTED"]
    uncertain = [{"order_suffix": _suffix(o.ticket), "symbol": o.symbol,
                  "state": ORDER_STATES.get(o.state, o.state), "magic": o.magic,
                  "setup": _server_iso(o.time_setup, offset_s), **own(o)}
                 for o in hist_orders if ORDER_STATES.get(o.state, "UNKNOWN_STATE") in UNCERTAIN_ORDER_STATES
                 or o.state not in ORDER_STATES]
    # A filled history order with no trade deal is an unreconciled outcome, not a clean fill.
    deal_orders = {d.order for d in trade_deals}
    uncertain += [{"order_suffix": _suffix(o.ticket), "symbol": o.symbol, "state": "FILLED_WITHOUT_DEAL",
                   "magic": o.magic, "setup": _server_iso(o.time_setup, offset_s), **own(o)}
                  for o in hist_orders if ORDER_STATES.get(o.state) == "FILLED" and o.ticket not in deal_orders]

    confirmed = [o for o in hist_orders if ORDER_STATES.get(o.state) in ("FILLED", "PARTIAL", "PLACED",
                                                                        "CANCELED", "EXPIRED")]
    confirmed_times = sorted(o.time_setup for o in confirmed if o.time_setup)
    ag = {k: [r for r in v if r["owner"] == "AG_PROFIT_TRADING"]
          for k, v in (("open_positions", open_positions), ("pending_orders", pending),
                       ("executed_deals", executed), ("closed_trades", closed),
                       ("rejected_orders", rejected), ("uncertain", uncertain))}
    ag_confirmed = sorted(o.time_setup for o in confirmed
                          if own(o)["owner"] == "AG_PROFIT_TRADING" and o.time_setup)
    return {
        "counts": {"open_positions": len(open_positions), "pending_orders": len(pending),
                   "history_orders": len(hist_orders), "history_order_states": dict(states),
                   "history_deals": len(hist_deals), "trade_deals": len(trade_deals),
                   "non_trade_deals": dict(non_trade), "closed_trades": len(closed),
                   "rejected_orders": len(rejected), "uncertain": len(uncertain)},
        "magics_seen": dict(Counter(str(getattr(r, "magic", None))
                                    for r in [*hist_orders, *trade_deals, *positions, *orders])),
        "broker_confirmed_any": {"first": _server_iso(confirmed_times[0], offset_s) if confirmed_times else None,
                                 "latest": _server_iso(confirmed_times[-1], offset_s) if confirmed_times else None},
        "ag_profit_trading": {"counts": {k: len(v) for k, v in ag.items()},
                              "first_broker_confirmed": _server_iso(ag_confirmed[0], offset_s) if ag_confirmed else None,
                              "latest_broker_confirmed": _server_iso(ag_confirmed[-1], offset_s) if ag_confirmed else None,
                              **ag},
        "open_positions": open_positions, "pending_orders": pending, "executed_deals": executed,
        "closed_trades": closed, "rejected_orders": rejected, "uncertain": uncertain,
    }


def history_range(hist_orders: List[Any], hist_deals: List[Any], offset_s: Optional[int]) -> Dict[str, Any]:
    times = sorted([o.time_setup for o in hist_orders if o.time_setup] + [d.time for d in hist_deals if d.time])
    return {"earliest_record": _server_iso(times[0], offset_s) if times else None,
            "latest_record": _server_iso(times[-1], offset_s) if times else None}


def verdict(result: Dict[str, Any], history_complete: bool) -> str:
    if not history_complete:
        return "HISTORY_INCOMPLETE"
    ag = result["ag_profit_trading"]["counts"]
    return "DEMO_ORDERS_FOUND" if any(ag.values()) else "NO_DEMO_ORDERS_CONFIRMED"


def load_s1_magic() -> int:
    import yaml
    contract = yaml.safe_load((ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml").read_text())
    return int(contract["magic_number"])


def load_host_magics() -> Dict[int, str]:
    import yaml
    raw = yaml.safe_load((ROOT / "config" / "demo_execution_host_magics.yaml").read_text())
    return {int(m["magic"]): str(m["source"]) for m in raw.get("magics_in_use_on_host", [])}


def server_offset_seconds(mt5: Any, symbol: str = "GBPUSD-VIP") -> Optional[int]:
    """Server-minus-UTC offset from a fresh tick, rounded to the hour; None if no recent tick."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not getattr(tick, "time", 0):
        return None
    diff = int(tick.time) - int(dt.datetime.now(dt.timezone.utc).timestamp())
    hours = round(diff / 3600)
    return hours * 3600 if abs(diff - hours * 3600) < 600 else None


def main(argv=None):
    from _host_common import import_mt5, mt5_access_lock, mt5_initialize, require_pinned_demo_account, single_instance
    from mt5.readonly_guard import counters_of, install

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terminal-path", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    real = import_mt5()
    if real is None:
        raise RuntimeError("REAL_MT5_PACKAGE_REQUIRED")
    run_id = "demo-order-audit-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mt5 = install(real, run_id)
    s1_magic, host_magics = load_s1_magic(), load_host_magics()
    with single_instance("demo_order_audit_readonly"), mt5_access_lock():
        ok, init_detail = mt5_initialize(mt5, args.terminal_path)
        if not ok:
            raise RuntimeError(f"MT5_INITIALIZE_FAILED {init_detail}")
        try:
            capture: Dict[str, Any] = {}
            pinned, pin_detail = require_pinned_demo_account(mt5, root=str(ROOT), terminal_path=args.terminal_path,
                                                            capture=capture)
            account, terminal = capture.get("account"), mt5.terminal_info()
            if not pinned or account is None or terminal is None:
                raise RuntimeError(f"ACCOUNT_PIN_MISMATCH {pin_detail}")
            offset = server_offset_seconds(mt5)
            now_server = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(seconds=offset or 0)
            hist_to = now_server + dt.timedelta(days=2)
            positions = list(mt5.positions_get() or [])
            orders = list(mt5.orders_get() or [])
            raw_ho, raw_hd = mt5.history_orders_get(HISTORY_FROM, hist_to), mt5.history_deals_get(HISTORY_FROM, hist_to)
            history_complete = raw_ho is not None and raw_hd is not None
            last_error = mt5.last_error()
            hist_orders, hist_deals = list(raw_ho or []), list(raw_hd or [])
            result = classify(positions=positions, orders=orders, hist_orders=hist_orders, hist_deals=hist_deals,
                              s1_magic=s1_magic, host_magics=host_magics, offset_s=offset)
            report = {
                "schema": "AGP_DEMO_ORDER_AUDIT_V1", "run_id": run_id,
                "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "account": {"server": account.server, "login_suffix": str(account.login)[-3:],
                            "trade_mode": account.trade_mode, "trade_mode_name": "DEMO" if account.trade_mode == 0
                            else "NOT_DEMO", "trade_allowed": bool(account.trade_allowed),
                            "trade_expert": bool(account.trade_expert), "currency": account.currency,
                            "margin_mode": account.margin_mode, "pin": pin_detail},
                "terminal": {"path": "<HOST_TERMINAL>", "path_pin_matches": True, "name": terminal.name,
                             "build": terminal.build, "connected": bool(terminal.connected),
                             "algo_trading_allowed": bool(terminal.trade_allowed),
                             "tradeapi_disabled": bool(getattr(terminal, "tradeapi_disabled", False))},
                "server_utc_offset_s": offset,
                "history_query": {"from_server": HISTORY_FROM.isoformat(), "to_server": hist_to.isoformat(),
                                  "orders_returned_none": raw_ho is None, "deals_returned_none": raw_hd is None,
                                  "last_error": list(last_error) if last_error else None,
                                  **history_range(hist_orders, hist_deals, offset)},
                "attribution": {"s1_magic": s1_magic, "ag_comment_pattern": AG_COMMENT_RE.pattern,
                                "host_magic_registry": "config/demo_execution_host_magics.yaml"},
                **result,
                "verdict": verdict(result, history_complete),
            }
        finally:
            mt5.shutdown()
    guard = counters_of(mt5).as_dict()
    report["guard"] = guard
    if guard["PROHIBITED_ORDER_API_ATTEMPTS"] or guard["BROKER_MUTATION_REQUESTS_FORWARDED"]:
        report["verdict"] = "GUARD_VIOLATION"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"verdict": report["verdict"], "counts": report["counts"],
                      "ag": report["ag_profit_trading"]["counts"], "range": report["history_query"],
                      "guard": counters_of(mt5).summary_line()}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
