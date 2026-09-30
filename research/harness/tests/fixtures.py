"""Synthetic fixtures only -- no network, no real market data."""
import pandas as pd

from research.harness.costs import CostModel, SymbolCosts


def bars(start="2024-01-02T00:00:00Z", n=10, tf="15min", o=1.1000, rows=None):
    ts = pd.date_range(pd.Timestamp(start), periods=n, freq=tf)
    rows = rows or [(o, o + 0.0005, o - 0.0005, o) for _ in range(n)]
    return pd.DataFrame({"ts": ts, "open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows], "volume": 1.0})


def trade(i, symbol="EURUSD", direction="LONG", entry_time="2024-01-02T00:00:00Z",
          exit_time="2024-01-02T02:00:00Z", entry=1.1000, stop=1.0990, target=1.1020, exit_price=None,
          reason="TARGET"):
    return {"trade_id": f"T{i}", "strategy_id": "ST_SYNTH", "strategy_version": "0.0.0", "symbol": symbol,
            "direction": direction, "entry_time": entry_time, "entry_price": entry, "stop_price": stop,
            "target_price": target, "exit_time": exit_time,
            "exit_price": exit_price if exit_price is not None else (target if reason == "TARGET" else stop),
            "exit_reason": reason}


def cost_model(**kw):
    c = SymbolCosts(**kw)
    return CostModel(per_symbol={"EURUSD": c, "GBPUSD": c})
