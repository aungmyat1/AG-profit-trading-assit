"""Minimal fee/slippage/funding cost model for BTC USDT-M perpetual research proposals
(spec section 23). Audited before adding: grep across strategy_engine/sweep_retest/ and
execution/ found no existing fee/maker/taker/funding model anywhere in the repo -- this is
genuinely new, kept deliberately minimal (spec: "keep it minimal and explicitly
documented"), and every assumed number below carries its source/version/date rather than
being presented as a fetched fact.

Nothing here is a live-fetched rate. A future addition COULD call Binance's public
GET /fapi/v1/fundingRate (funding-rate history) for a live figure -- not done in this
task; ASSUMED_FUNDING_RATE_PER_INTERVAL below is explicitly a placeholder, not a live
observation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# Binance USDT-M Futures standard (non-VIP0 base tier, no BNB fee discount applied) public
# fee schedule -- source: Binance's published USDT-Margined Futures trading fee rate
# table (fapi trading fee page), checked 2026-09-02. These are the STANDARD tier rates;
# an account's actual negotiated/VIP rate may differ and is out of scope for this
# research-only model.
MAKER_FEE_RATE = 0.0002  # 0.0200%
TAKER_FEE_RATE = 0.0005  # 0.0500%

# Documented assumption, not a measured statistic: both entry (retest trigger) and exit
# (SL/TP1/TP2) legs are modeled as TAKER fills (market-order-equivalent), the conservative
# (higher-cost) case, since this strategy's entry/exit rules do not specify a resting
# limit order.
DEFAULT_FEE_RATE = TAKER_FEE_RATE

# Slippage: a documented, deliberately simple assumption of N ticks adverse execution per
# leg (entry AND each exit leg) -- not derived from any measured order-book/impact study.
# tick_size comes from the caller's own BinanceSymbolMeta/crypto_symbol_meta (BTCUSDT:
# 0.1 USDT) so this stays in real price units.
DEFAULT_SLIPPAGE_TICKS = 2.0

# Binance funds USDT-M perpetuals every 8h at 00:00/08:00/16:00 UTC -- same fact recorded
# in execution_runtime/binance_usdtm_feed.py::FUNDING_INTERVAL_HOURS (Binance's public
# funding-fee documentation, checked 2026-09-02); duplicated here as a plain constant
# rather than importing across the exchange-adapter/cost-model boundary, matching this
# repo's convention of small independent copies for cross-cutting facts (see
# strategy_engine/sweep_retest/trend.py's own docstring for the same convention).
FUNDING_INTERVAL_HOURS = 8

# Placeholder estimate of the funding rate PER 8h interval -- order-of-magnitude typical
# for BTCUSDT perpetual funding (Binance's publicly observable historical funding rates
# for BTCUSDT have long-run averaged in the low single-digit basis points per 8h),
# explicitly NOT a live-fetched figure. Applied only as a rough cost placeholder, never
# presented as a forecast.
ASSUMED_FUNDING_RATE_PER_INTERVAL = 0.0001  # 0.0100% per 8h interval

# This strategy's own contract (strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml) has no
# time-based exit rule, so the ACTUAL holding period of a future real position is unknown
# at proposal-generation time. This is a documented placeholder used ONLY to decide
# whether the cost estimate should include a funding crossing -- never a claim about how
# long the strategy holds. Chosen as one funding interval (8h) -- roughly "the position
# survives to the next scheduled funding settlement" -- the minimal assumption that makes
# the "only apply funding when a holding period would cross a funding timestamp" rule
# (spec section 23) actually exercisable at proposal time.
DEFAULT_ASSUMED_HOLD_HOURS = 8.0


@dataclass(frozen=True)
class CostEstimate:
    """A proposal's estimated_fees / funding_assumption fields (spec section 24). All
    figures are USDT (BTCUSDT is USDT-margined). Nothing here is a guaranteed real cost --
    every field is an ESTIMATE per this module's documented assumptions."""

    entry_notional: float
    exit_notional: float
    fee_rate_assumed: float
    fees_estimate: float
    slippage_ticks_assumed: float
    slippage_estimate: float
    funding_interval_hours: int
    assumed_hold_hours: float
    funding_rate_per_interval_assumed: float
    funding_crossings: int
    funding_cost_estimate: float
    total_estimated_cost: float
    source_note: str


def funding_timestamps_between(start: datetime, end: datetime) -> List[datetime]:
    """Every 00:00/08:00/16:00 UTC boundary in [start, end) -- the strict boundary set a
    holding period would "cross" if it spans one. start/end must be UTC-aware."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("funding_timestamps_between requires UTC-aware datetimes")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if end <= start:
        return []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    boundaries = []
    while day <= end:
        for hour in (0, 8, 16):
            ts = day.replace(hour=hour)
            if start <= ts < end:
                boundaries.append(ts)
        day += timedelta(days=1)
    return boundaries


def estimate_costs(
    entry_time: datetime,
    entry_price: float,
    exit_price: float,
    volume: float,
    tick_size: float,
    contract_size: float = 1.0,
    fee_rate: float = DEFAULT_FEE_RATE,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    assumed_hold_hours: float = DEFAULT_ASSUMED_HOLD_HOURS,
    funding_rate_per_interval: float = ASSUMED_FUNDING_RATE_PER_INTERVAL,
) -> CostEstimate:
    """entry_price/exit_price: the two legs fees are charged on (e.g. entry and TP2, or
    entry and stop_loss for a worst-case estimate -- caller's choice which exit price to
    pass; this function does not itself decide worst-case vs. target-case, it only prices
    whichever two legs it is given).
    """
    if volume <= 0:
        raise ValueError("volume must be positive")
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")

    entry_notional = entry_price * volume * contract_size
    exit_notional = exit_price * volume * contract_size
    fees_estimate = (entry_notional + exit_notional) * fee_rate

    slippage_price_distance = slippage_ticks * tick_size
    # Slippage priced on notional-equivalent terms for both legs (entry + exit), same
    # convention as the fee calc above.
    slippage_estimate = slippage_price_distance * volume * contract_size * 2

    hold_end = entry_time + timedelta(hours=assumed_hold_hours)
    crossings = funding_timestamps_between(entry_time, hold_end)
    funding_crossings = len(crossings)
    # Funding is charged on the position's notional at each crossing -- approximated here
    # using entry_notional for every crossing (documented simplification: does not attempt
    # to model TP1's 50% partial-close reducing notional mid-hold).
    funding_cost_estimate = funding_crossings * entry_notional * funding_rate_per_interval

    total = fees_estimate + slippage_estimate + funding_cost_estimate

    return CostEstimate(
        entry_notional=entry_notional, exit_notional=exit_notional,
        fee_rate_assumed=fee_rate, fees_estimate=fees_estimate,
        slippage_ticks_assumed=slippage_ticks, slippage_estimate=slippage_estimate,
        funding_interval_hours=FUNDING_INTERVAL_HOURS, assumed_hold_hours=assumed_hold_hours,
        funding_rate_per_interval_assumed=funding_rate_per_interval,
        funding_crossings=funding_crossings, funding_cost_estimate=funding_cost_estimate,
        total_estimated_cost=total,
        source_note=(
            "fees: Binance USDT-M standard fee schedule checked 2026-09-02; "
            "slippage: documented placeholder assumption, not measured; "
            "funding: placeholder rate, not live-fetched -- see costs.py module docstring"
        ),
    )
