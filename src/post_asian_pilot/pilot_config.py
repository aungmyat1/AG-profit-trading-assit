"""Loads config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1.yaml -- the pilot-level policy
overlay (universe narrowing, risk override, execution window) that sits on top of
ST_ASIAN_SWEEP_5R_V1's own signed strategy contract without editing it. See that yaml's
own header comment for why risk_per_trade_pct lives here and not in the strategy file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import yaml

DEFAULT_PILOT_CONFIG_PATH = "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml"
DEFAULT_RELEASE_CONFIG_PATH = "config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml"
V1_0_PILOT_CONFIG_PATH = "config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1.yaml"
V1_0_RELEASE_CONFIG_PATH = "config/releases/AG_TRADE_ASSISTANT_V1_0.yaml"
V1_0_1_RELEASE_CONFIG_PATH = "config/releases/AG_TRADE_ASSISTANT_V1_0_1.yaml"


@dataclass(frozen=True)
class PilotConfig:
    pilot_id: str
    strategy_id: str
    strategy_version: str
    strategy_source_path: str
    pair_id: str
    universe: Tuple[str, ...]
    reference_session_name: str
    execution_window_start_utc: str
    execution_window_end_utc: str
    risk_per_trade_pct: float
    max_open_positions: int
    max_new_trades_per_day: int
    max_new_trades_per_symbol_per_day: int
    max_aggregate_open_risk_pct: float
    strategy_daily_loss_limit_r: float
    tie_break_priority: Tuple[str, ...]
    state_dir: Optional[str]
    raw: dict
    source_path: str


def load_pilot_config(path: str = DEFAULT_PILOT_CONFIG_PATH) -> PilotConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    risk = raw["risk"]
    window = raw["execution_window"]
    return PilotConfig(
        pilot_id=raw["pilot_id"],
        strategy_id=raw["strategy_id"],
        strategy_version=str(raw["strategy_version"]),
        strategy_source_path=raw["strategy_source_path"],
        pair_id=raw["pair_id"],
        universe=tuple(raw["universe"]),
        reference_session_name=raw["reference_session"]["name"],
        execution_window_start_utc=window["start_utc"],
        execution_window_end_utc=window["end_utc"],
        risk_per_trade_pct=float(risk["risk_per_trade_pct"]),
        max_open_positions=int(risk["max_open_positions"]),
        max_new_trades_per_day=int(risk["max_new_trades_per_day"]),
        max_new_trades_per_symbol_per_day=int(risk.get("max_new_trades_per_symbol_per_day", 1)),
        max_aggregate_open_risk_pct=float(risk.get("max_aggregate_open_risk_pct", risk["risk_per_trade_pct"])),
        strategy_daily_loss_limit_r=float(risk["strategy_daily_loss_limit_r"]),
        tie_break_priority=tuple(raw.get("tie_break_priority") or ()),
        # Optional: isolates this pilot's snapshot/decision/proposal/ledger/counter state
        # under its own journal subdirectory (see store.PilotStores.default's state_dir
        # param) so two pilot configs for the SAME strategy_id but DIFFERENT session_pairs
        # cycle (e.g. ASIAN_LONDON vs LONDON_NEWYORK) never share one DailyTradeLedger --
        # that ledger's own capacity/per-symbol-slot key is strategy_id+date only, not
        # cycle-aware (governor.py), so sharing a directory across cycles would let an
        # ASIAN_LONDON slot claim silently consume LONDON_NEWYORK's independent quota for
        # the same symbol/day, violating cycle independence. Absent -> unchanged default
        # behavior (store.DEFAULT_STATE_DIR), so existing pilot configs need no edit.
        state_dir=raw.get("state_dir"),
        raw=raw,
        source_path=path,
    )


def load_raw_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
