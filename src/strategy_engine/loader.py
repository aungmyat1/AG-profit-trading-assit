"""Parse a strategies/*.yaml file into a StrategyConfig.

This is the bridge that was missing: previously strategies/*.yaml was documentation only,
with nothing reading it into the executable session-box code. Fails loudly (KeyError /
ValueError) on a malformed or incomplete file rather than silently defaulting -- a
strategy config with a missing field should not be able to run with a made-up value.
"""
from __future__ import annotations

import yaml

from .models import RiskConfig, SessionPair, SessionWindow, StrategyConfig, TargetLeg


def load_strategy(path: str) -> StrategyConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    session_pairs = tuple(
        SessionPair(
            pair_id=pair["pair_id"],
            reference_session=_window(pair["reference_session"]),
            trade_session=_window(pair["trade_session"]),
            max_entries_per_session=pair["trade_session"]["max_entries_per_session"],
        )
        for pair in raw["session_pairs"]
    )

    risk_raw = raw["risk_and_money_management"]
    risk = RiskConfig(
        risk_mode=risk_raw["risk_mode"],
        stop_loss_mode=risk_raw["stop_loss_mode"],
        stop_loss_range_pct=risk_raw["stop_loss_range_pct"],
        max_spread_allowed_pips=risk_raw["max_spread_allowed_pips"],
        slippage_limit_points=risk_raw["slippage_limit_points"],
    )

    targets_raw = raw["position_split_and_targets"]
    legs = tuple(
        TargetLeg(
            leg_id=leg["leg_id"],
            volume_pct=leg["volume_pct"],
            target_type=leg["target_type"],
            action_on_fill=leg.get("action_on_fill"),
            fixed_r_multiple=leg.get("fixed_r_multiple"),
            trailing_rule=leg.get("trailing_rule"),
        )
        for leg in targets_raw["legs"]
    )

    invalidation_raw = raw["invalidation_rules"]

    entry_raw = raw["entry_rules"]
    long_type = entry_raw["long_setup"]["entry_order_type"]
    short_type = entry_raw["short_setup"]["entry_order_type"]
    if long_type != short_type:
        raise ValueError(
            f"{path}: long_setup.entry_order_type ({long_type!r}) != short_setup.entry_order_type "
            f"({short_type!r}) -- refusing to guess which side is authoritative"
        )

    return StrategyConfig(
        strategy_id=raw["strategy_id"],
        strategy_name=raw["strategy_name"],
        strategy_family=raw["strategy_family"],
        version=raw["version"],
        status=raw["status"],
        instruments=tuple(raw["instruments"]),
        timeframe=raw["timeframe"],
        magic_number=raw["magic_number"],
        session_pairs=session_pairs,
        risk=risk,
        entry_order_type=long_type,
        total_target_r=targets_raw["total_target_r"],
        legs=legs,
        max_range_pips_eurusd=raw["regime_classification"]["range_session_check"]["max_range_pips_eurusd"],
        time_invalidation=invalidation_raw["time_invalidation"],
        structural_invalidation=invalidation_raw["structural_invalidation"],
        source_path=path,
    )


def _window(section: dict) -> SessionWindow:
    return SessionWindow(
        name=section["name"],
        start_time_gmt=section["start_time_gmt"],
        end_time_gmt=section["end_time_gmt"],
    )
