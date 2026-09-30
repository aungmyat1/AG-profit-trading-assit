"""Parses strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml into a SweepRetestStrategyConfig
holding one MarketProfile per asset class (Forex, Crypto) plus the rules shared across
both (risk, TTL, guards).

Deliberately a SEPARATE small loader from strategy_engine.loader.load_strategy /
StrategyConfig, not an extension of it -- see this module's original docstring reasoning
(unchanged by the crypto generalization): strategy_engine.models.StrategyConfig's fields
mirror the EMA/session-box regime family (ST_ASIAN_SWEEP_5R_V1's exact shape), which has
no natural home for H1 structural trend, M5 MSS/retest, a multi-profile symbol->reference
mapping, or the pip/tick buffer split this strategy needs. StrategyConfig/TradeSignal/
load_strategy remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Sequence, Tuple

import yaml

from .profile import (
    BUFFER_PIP,
    BUFFER_TICK,
    REFERENCE_ASIAN_SESSION,
    REFERENCE_PREVIOUS_DAY,
    MarketProfile,
)

_REFERENCE_KIND_MAP = {"ASIAN_SESSION": REFERENCE_ASIAN_SESSION, "PREVIOUS_DAY": REFERENCE_PREVIOUS_DAY}
_BUFFER_KIND_MAP = {"PIP": BUFFER_PIP, "TICK": BUFFER_TICK}


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


@dataclass(frozen=True)
class ProfileConfig:
    profile: MarketProfile
    reference_start_gmt: str = ""  # ASIAN_SESSION only
    reference_end_gmt: str = ""  # ASIAN_SESSION only
    buffer_pips: float = 0.0  # BUFFER_PIP only
    buffer_ticks: float = 0.0  # BUFFER_TICK only


@dataclass(frozen=True)
class SweepRetestStrategyConfig:
    strategy_id: str
    strategy_name: str
    strategy_family: str
    version: str
    status: str
    magic_number: int

    profiles: Tuple[ProfileConfig, ...]

    entry_ttl_m5_bars: int
    min_tp2_r_multiple: float
    tp1_volume_pct: float
    risk_percent: float
    max_open_strategy_positions: int
    daily_loss_circuit_r: float

    source_path: str

    @property
    def instruments(self) -> Tuple[str, ...]:
        return tuple(sym for p in self.profiles for sym in p.profile.symbols)

    def profile_config_for_symbol(self, symbol: str) -> "ProfileConfig | None":
        return next((p for p in self.profiles if symbol in p.profile.symbols), None)


def load_sweep_retest_strategy(path: str) -> SweepRetestStrategyConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    profiles = tuple(_parse_profile(p) for p in raw["profiles"])

    entry_raw = raw["entry_rules"]
    targets_raw = raw["position_split_and_targets"]
    risk_raw = raw["risk_and_money_management"]
    guards_raw = raw["global_guards"]

    return SweepRetestStrategyConfig(
        strategy_id=raw["strategy_id"],
        strategy_name=raw["strategy_name"],
        strategy_family=raw["strategy_family"],
        version=raw["version"],
        status=raw["status"],
        magic_number=raw["magic_number"],
        profiles=profiles,
        entry_ttl_m5_bars=entry_raw["entry_ttl_m5_bars"],
        min_tp2_r_multiple=targets_raw["min_tp2_r_multiple"],
        tp1_volume_pct=targets_raw["tp1_volume_pct"],
        risk_percent=risk_raw["risk_percent"],
        max_open_strategy_positions=guards_raw["max_open_strategy_positions"],
        daily_loss_circuit_r=guards_raw["daily_loss_circuit_r"],
        source_path=path,
    )


def _parse_profile(raw: dict) -> ProfileConfig:
    reference = raw["reference"]
    reference_kind = _REFERENCE_KIND_MAP[reference["kind"]]
    windows = tuple(
        (_parse_hhmm(w["start_time_gmt"]), _parse_hhmm(w["end_time_gmt"])) for w in raw["execution_windows"]
    )
    stop_buffer = raw["stop_buffer"]
    buffer_kind = _BUFFER_KIND_MAP[stop_buffer["kind"]]

    profile = MarketProfile(
        profile_id=raw["profile_id"],
        symbols=tuple(raw["instruments"]),
        reference_kind=reference_kind,
        reference_label=reference["label"],
        buffer_kind=buffer_kind,
        execution_windows=windows,
    )
    return ProfileConfig(
        profile=profile,
        reference_start_gmt=reference.get("start_time_gmt", ""),
        reference_end_gmt=reference.get("end_time_gmt", ""),
        buffer_pips=stop_buffer.get("pips", 0.0),
        buffer_ticks=stop_buffer.get("ticks", 0.0),
    )
