"""One read-only EURUSD FX Opportunity evaluation against the running MT5 terminal.

    PYTHONPATH=src python scripts/run_fx_opportunity_once.py --cycle POST_LONDON

Attaches to an already-running, logged-in terminal via MetaTrader5.initialize() with
no credentials (read-only market data only). Broker-mutation APIs are replaced with
blocking counters for the whole run and their counts are printed. Prints one JSON
summary; never forms a proposal or ticket and never sends/checks an order.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "src"))
os.chdir(_REPO)

import MetaTrader5  # noqa: E402

_BLOCKED = ("order_send", "order_check", "positions_get", "positions_total", "orders_get",
            "orders_total", "trade_buy", "trade_sell", "trade_close", "trade_modify", "trade_cancel")
_calls = {name: 0 for name in _BLOCKED}


def _block(name):
    def _handler(*_a, **_k):
        _calls[name] += 1
        raise RuntimeError(f"MetaTrader5.{name} is blocked in the FX Opportunity slice")
    return _handler


for _name in _BLOCKED:
    setattr(MetaTrader5, _name, _block(_name))

from fx_opportunity import CYCLES, evaluate_fx_opportunity  # noqa: E402
from mt5.market_data import get_candles  # noqa: E402
from opportunity.candidate_store import CandidateStore  # noqa: E402
from opportunity.registry_binding import resolve_strategy_binding  # noqa: E402
from post_asian_pilot.pilot_config import load_pilot_config  # noqa: E402
from strategy_engine.loader import load_strategy  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", choices=sorted(CYCLES), required=True)
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--store", default="journal/fx_opportunity/candidates.json")
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH") or None,
                    help="attach to this running terminal (no credentials are ever passed)")
    args = ap.parse_args()

    if os.path.abspath(MetaTrader5.__file__).startswith(os.path.abspath(_REPO) + os.sep):
        print(json.dumps({"error": "MT5_REAL_PACKAGE_UNAVAILABLE", "module": MetaTrader5.__file__}))
        return 2
    attach = {"path": args.terminal_path} if args.terminal_path else {}
    if not MetaTrader5.initialize(**attach):
        print(json.dumps({"error": "MT5_INITIALIZE_FAILED", "last_error": list(MetaTrader5.last_error())}))
        return 2
    try:
        pilot = load_pilot_config(CYCLES[args.cycle])
        strategy = load_strategy(pilot.strategy_source_path)
        binding = resolve_strategy_binding(pilot.strategy_id)
        now = dt.datetime.now(dt.timezone.utc)
        terminal = MetaTrader5.terminal_info()
        result = evaluate_fx_opportunity(
            cycle=args.cycle, symbol=args.symbol, trading_date=now.date(), now=now,
            pilot=pilot, strategy=strategy, binding=binding, fetch_candles=get_candles,
            market_data_mode="REAL", source="mt5.market_data.get_candles",
            store=CandidateStore(args.store),
        )
        out = result.summary()
        out["provenance"]["terminal_company"] = getattr(terminal, "company", None)
        out["broker_mutation_calls"] = dict(_calls)
        print(json.dumps(out, indent=2, default=str))
        return 0
    finally:
        MetaTrader5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
