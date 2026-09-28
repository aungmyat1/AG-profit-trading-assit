"""One read-only FX Opportunity scan (EURUSD/GBPUSD/USDJPY) against the running MT5 terminal.

    python scripts/run_fx_opportunity_once.py --cycle POST_ASIAN --symbol EURUSD
    python scripts/run_fx_opportunity_once.py --cycle POST_LONDON --symbol ALL

Attaches to an already-running, logged-in terminal via MetaTrader5.initialize() with
no credentials (read-only market data only; never logs in). Broker-mutation APIs are
replaced with blocking counters for the whole run and their counts are printed. Every
requested symbol gets one explicit state (see fx_opportunity.scanner); an unavailable
real package or an unauthorized terminal is reported per symbol (fail closed) and no
market data is read. Never forms a proposal or ticket and never sends/checks an order.

MT5 calls made: initialize/shutdown/terminal_info/account_info (server name and Demo/Live
trade mode only; the login/account number is never read into output), last_error,
symbol_info, symbol_info_tick, copy_rates_range, and symbol_select (Market Watch visibility
only, via mt5.market_data). Refuses a non-Demo account and a server not listed for the
selected broker (default VTMARKETS -> VTMarkets-Demo).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

import MetaTrader5  # noqa: E402

_BLOCKED = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
            "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel")
_calls = {name: 0 for name in _BLOCKED}
_AUTH_FAILED = -6  # MT5 RES_E_AUTH_FAILED: "Terminal: Authorization failed"


def _block(name):
    def _handler(*_a, **_k):
        _calls[name] += 1
        raise RuntimeError(f"MetaTrader5.{name} is blocked in the FX Opportunity platform")
    return _handler


for _name in _BLOCKED:
    setattr(MetaTrader5, _name, _block(_name))

from fx_opportunity import scanner  # noqa: E402
from fx_opportunity.instruments import check_broker_spec, get_broker, get_instrument, load_brokers, load_instruments  # noqa: E402
from fx_opportunity.runner import CYCLES  # noqa: E402
from mt5.market_data import MarketDataError, get_candles, get_tick, server_time_provenance  # noqa: E402
from opportunity.candidate_store import CandidateStore  # noqa: E402


def is_stub(module) -> bool:
    """The repo-root MetaTrader5.py stub shadows the real package on some sys.paths."""
    path = os.path.abspath(getattr(module, "__file__", "") or "")
    return path.startswith(os.path.abspath(_REPO) + os.sep) or hasattr(module, "MT5StubOperationAttempted")


def _application_lineage() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return head + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _emit(cycle, now, lineage, scans, exit_code, identity=None):
    print(json.dumps({
        "cycle": cycle,
        "evaluated_at": now.isoformat(),
        "market_data_mode": "REAL",
        "mode": "LIVE",
        "source": "MT5_REAL",
        **(identity or {}),
        "application_lineage": lineage,
        "results": [s.summary() for s in scans],
        "proposal_authority": "NONE",
        "trade_ticket": "NOT_CREATED",
        "broker_mutation_calls": dict(_calls),
    }, indent=2, default=str))
    return exit_code


def main() -> int:
    symbols_known = sorted(load_instruments())
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", choices=sorted(CYCLES), required=True)
    ap.add_argument("--symbol", default="EURUSD", choices=symbols_known + ["ALL"])
    ap.add_argument("--broker", default="VTMARKETS", choices=sorted(load_brokers()),
                    help="broker key in the instrument contract (the connected server must be listed for it)")
    ap.add_argument("--store", default="journal/fx_opportunity/candidates.json")
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH") or None,
                    help="attach to this running terminal (no credentials are ever passed)")
    args = ap.parse_args()
    symbols = symbols_known if args.symbol == "ALL" else [args.symbol]
    now = dt.datetime.now(dt.timezone.utc)
    lineage = _application_lineage()

    if is_stub(MetaTrader5):
        return _emit(args.cycle, now, lineage, scanner.blocked(
            args.cycle, symbols, scanner.MT5_REAL_PACKAGE_UNAVAILABLE, ("MT5_STUB_MODULE",)), 2)
    attach = {"path": args.terminal_path} if args.terminal_path else {}
    if not MetaTrader5.initialize(**attach):
        code, _message = MetaTrader5.last_error()
        status = scanner.LIVE_MT5_AUTH_BLOCKED if code == _AUTH_FAILED else scanner.DATA_UNAVAILABLE
        return _emit(args.cycle, now, lineage, scanner.blocked(
            args.cycle, symbols, status, (f"MT5_INITIALIZE_FAILED:{code}",)), 2)
    try:
        account = MetaTrader5.account_info()
        if account is None:
            return _emit(args.cycle, now, lineage, scanner.blocked(
                args.cycle, symbols, scanner.LIVE_MT5_AUTH_BLOCKED, ("MT5_NO_AUTHORIZED_ACCOUNT",)), 2)
        # Non-secret identity only: never the login/account number.
        broker = get_broker(args.broker)
        server = str(getattr(account, "server", "") or "")
        demo = getattr(account, "trade_mode", None) == getattr(MetaTrader5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        identity = {"broker": broker.canonical_name, "server": server,
                    "account_environment": "DEMO" if demo else "NOT_VERIFIED_DEMO"}
        if not demo:
            return _emit(args.cycle, now, lineage, scanner.blocked(
                args.cycle, symbols, scanner.ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO, ("ACCOUNT_NOT_DEMO",)), 2, identity)
        if server not in broker.servers:
            return _emit(args.cycle, now, lineage, scanner.blocked(
                args.cycle, symbols, scanner.BROKER_SERVER_MISMATCH, (f"SERVER_NOT_LISTED_FOR_{args.broker}",)), 2, identity)
        ctx = scanner.load_cycle_context(args.cycle)
        span_start, span_end = scanner.cycle_span(ctx, now.date())
        span_end = max(span_start, min(now, span_end))
        store = CandidateStore(args.store)
        scans = []
        for symbol in symbols:
            instrument = get_instrument(symbol)
            broker_symbol = instrument.broker_symbol(args.broker).symbol
            mismatch = check_broker_spec(instrument, MetaTrader5.symbol_info(broker_symbol))
            if mismatch:
                scans.append(scanner.SymbolScan(args.cycle, symbol, scanner.INSTRUMENT_SPEC_MISMATCH, mismatch))
                continue
            try:
                server_clock = server_time_provenance(broker_symbol, span_start, span_end)
            except MarketDataError as exc:
                scans.append(scanner.SymbolScan(args.cycle, symbol, scanner.DATA_UNAVAILABLE, (exc.reason_code,)))
                continue
            try:
                tick = get_tick(broker_symbol)
                spread, spread_src = round(tick.ask - tick.bid, instrument.digits), "mt5.symbol_info_tick"
            except MarketDataError:
                spread, spread_src = None, None

            def fetch(_symbol, timeframe, start, end, _b=broker_symbol):
                return get_candles(_b, timeframe, start, end)

            scans.append(scanner.scan_symbol(
                ctx, symbol, trading_date=now.date(), now=now, fetch_candles=fetch,
                market_data_mode="REAL",
                source=f"mt5.market_data.get_candles:{broker.canonical_name}:{server}:{broker_symbol}",
                store=store, spread_price=spread, spread_source=spread_src, application_lineage=lineage,
                server_clock=server_clock,
            ))
        return _emit(args.cycle, now, lineage, scans, 0, identity)
    finally:
        MetaTrader5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
