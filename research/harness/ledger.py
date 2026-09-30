"""Canonical engine-ledger intake. The harness never generates signals or re-implements a
strategy rule: every entry/stop/target comes from the engine's own ledger rows. Rows missing
engine identity or trade geometry are rejected rather than inferred.
"""
from __future__ import annotations

import json

import pandas as pd

REQUIRED = ("trade_id", "strategy_id", "strategy_version", "symbol", "direction", "entry_time",
            "entry_price", "stop_price", "target_price", "exit_time", "exit_price", "exit_reason")
TIME_COLS = ("entry_time", "exit_time", "signal_time")
DIRECTIONS = {"LONG": 1, "SHORT": -1}


def load_engine_ledger(src) -> pd.DataFrame:
    """Accept a DataFrame, a list of dicts, or a path to .jsonl/.parquet/.csv produced by an engine."""
    if isinstance(src, pd.DataFrame):
        df = src.copy()
    elif isinstance(src, (list, tuple)):
        df = pd.DataFrame(list(src))
    elif str(src).endswith(".jsonl"):
        with open(src, encoding="utf-8") as fh:
            df = pd.DataFrame([json.loads(l) for l in fh if l.strip()])
    elif str(src).endswith(".parquet"):
        df = pd.read_parquet(src)
    elif str(src).endswith(".csv"):
        df = pd.read_csv(src)
    else:
        raise ValueError(f"unsupported ledger source: {src!r}")
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"engine ledger missing required columns: {missing}")
    for c in TIME_COLS:
        if c in df.columns:
            t = pd.to_datetime(df[c])
            if t.dt.tz is None:
                raise ValueError(f"{c}: naive timestamps rejected (UTC required)")
            df[c] = t.dt.tz_convert("UTC")
    bad = ~df["direction"].isin(DIRECTIONS)
    if bad.any():
        raise ValueError(f"unknown direction values: {sorted(df.loc[bad, 'direction'].unique())}")
    if df["trade_id"].duplicated().any():
        raise ValueError("duplicate trade_id in engine ledger")
    sign = df["direction"].map(DIRECTIONS)
    risk = (df["entry_price"] - df["stop_price"]) * sign
    if (risk <= 0).any():
        raise ValueError("stop_price must be on the loss side of entry_price for every trade")
    df["risk_price"] = risk
    return df.sort_values(["exit_time", "trade_id"], kind="stable").reset_index(drop=True)
