"""Parses strategies/ST_SESSION_SWEEP_RETEST_V1.yaml into a SweepRetestStrategyConfig.

Deliberately a SEPARATE small loader from strategy_engine.loader.load_strategy /
StrategyConfig, not an extension of it. strategy_engine.models.StrategyConfig's own
docstring says its fields "mirror strategies/*.yaml structurally" for the session-box
family (session_pairs + EMA_50 regime_classification + PERCENT_OF_SESSION_RANGE stop
mode) -- ST_ASIAN_SWEEP_5R_V1's exact shape. This strategy's parameters (H1 structural
trend instead of EMA, M5 sweep/MSS/retest instead of a session-box sweep, an entry TTL in
bars, a pip-based SL buffer, a daily R circuit breaker, and global position concurrency)
have no home in that dataclass without adding a pile of Optional fields that would be
meaningless for ST_ASIAN_SWEEP_5R_V1 -- judged fundamentally incompatible rather than a
minimal extension, per the task's own guidance to use judgment here. StrategyConfig/
TradeSignal/load_strategy are therefore untouched by this change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

import yaml


@dataclass(frozen=True)
class ExecutionWindow:
    name: str
    start_time_gmt: str  # "HH:MM"
    end_time_gmt: str  # "HH:MM"


@dataclass(frozen=True)
class SweepRetestStrategyConfig:
    strategy_id: str
    strategy_name: str
    strategy_family: str
    version: str
    status: str
    instruments: Sequence[str]
    magic_number: int

    asian_reference_start_gmt: str
    asian_reference_end_gmt: str
    execution_windows: Tuple[ExecutionWindow, ...]

    sl_buffer_pips: float
    min_tp2_r_multiple: float
    tp1_volume_pct: float
    entry_ttl_m5_bars: int

    risk_percent: float
    max_open_strategy_positions: int
    daily_loss_circuit_r: float

    source_path: str


def load_sweep_retest_strategy(path: str) -> SweepRetestStrategyConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    windows = tuple(
        ExecutionWindow(name=w["name"], start_time_gmt=w["start_time_gmt"], end_time_gmt=w["end_time_gmt"])
        for w in raw["execution_windows"]
    )

    risk_raw = raw["risk_and_money_management"]
    targets_raw = raw["position_split_and_targets"]
    entry_raw = raw["entry_rules"]
    guards_raw = raw["global_guards"]

    return SweepRetestStrategyConfig(
        strategy_id=raw["strategy_id"],
        strategy_name=raw["strategy_name"],
        strategy_family=raw["strategy_family"],
        version=raw["version"],
        status=raw["status"],
        instruments=tuple(raw["instruments"]),
        magic_number=raw["magic_number"],
        asian_reference_start_gmt=raw["asian_reference_session"]["start_time_gmt"],
        asian_reference_end_gmt=raw["asian_reference_session"]["end_time_gmt"],
        execution_windows=windows,
        sl_buffer_pips=risk_raw["sl_buffer_pips"],
        min_tp2_r_multiple=targets_raw["min_tp2_r_multiple"],
        tp1_volume_pct=targets_raw["tp1_volume_pct"],
        entry_ttl_m5_bars=entry_raw["entry_ttl_m5_bars"],
        risk_percent=risk_raw["risk_percent"],
        max_open_strategy_positions=guards_raw["max_open_strategy_positions"],
        daily_loss_circuit_r=guards_raw["daily_loss_circuit_r"],
        source_path=path,
    )
