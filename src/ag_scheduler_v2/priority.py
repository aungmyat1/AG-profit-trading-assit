"""Rolling-expectancy priority ranking (spec sections 19-24), advisory only during
OFFLINE_RESEARCH ("WOULD_PRIORITIZE", never EXECUTE). All candidates are retained in
shadow evidence regardless of rank -- ranking only decides a hypothetical ordering.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional, Sequence

from ag_scheduler_v2.config_loader import load_config

STATUS_INSUFFICIENT_ROLLING_SAMPLE = "INSUFFICIENT_ROLLING_SAMPLE"
STATUS_SCORED = "SCORED"

WOULD_PRIORITIZE = "WOULD_PRIORITIZE"


@dataclass(frozen=True)
class PriorityConfig:
    rolling_sample_trades: int
    deterministic_symbol_fallback_order: tuple

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "PriorityConfig":
        raw = load_config(path).get("priority") or {}
        if "rolling_sample_trades" not in raw:
            raise ValueError("SCHEDULER_CONFIG_CONFLICT: priority.rolling_sample_trades is required")
        fallback = tuple(raw.get("deterministic_symbol_fallback_order") or ())
        return cls(rolling_sample_trades=int(raw["rolling_sample_trades"]), deterministic_symbol_fallback_order=fallback)


@dataclass(frozen=True)
class ResolvedTradeOutcome:
    """One past, resolved trade outcome known strictly before the ranking instant --
    callers must never include same-cycle or future-dated outcomes here (spec 23)."""

    resolved_at_utc: dt.datetime
    r_multiple: float  # NET R after modeled/known trading costs


@dataclass(frozen=True)
class Candidate:
    symbol: str
    setup_type: str
    current_spread: float
    baseline_spread: float
    news_eligible: bool = True  # False if a risk/news/economic constraint disqualifies it
    campaign_risk_eligible: bool = True
    friction_burden: float = 0.0  # lower is better tie-break input; caller-supplied


@dataclass(frozen=True)
class PriorityResult:
    symbol: str
    setup_type: str
    priority_status: str  # STATUS_SCORED | STATUS_INSUFFICIENT_ROLLING_SAMPLE
    expectancy_sample_end_utc: Optional[dt.datetime]
    expectancy_sample_n: int
    expectancy_value: Optional[float]
    spread_ratio: float
    priority_score: Optional[float]


def compute_priority(
    candidate: Candidate,
    *,
    history_before_t: Sequence[ResolvedTradeOutcome],
    as_of_utc: dt.datetime,
    config: PriorityConfig,
) -> PriorityResult:
    """`history_before_t` must already be filtered by the caller to outcomes resolved
    strictly before `as_of_utc` -- this function does not itself re-check timestamps
    against a live clock, it only asserts the ordering invariant so a caller mistake
    fails loudly instead of silently leaking future data."""
    for outcome in history_before_t:
        if outcome.resolved_at_utc >= as_of_utc:
            raise ValueError(
                f"RANKING_LOOKAHEAD: outcome resolved at {outcome.resolved_at_utc} is not strictly "
                f"before ranking instant {as_of_utc}"
            )

    spread_ratio = candidate.current_spread / candidate.baseline_spread if candidate.baseline_spread else float("inf")
    n = len(history_before_t)

    if n < config.rolling_sample_trades:
        return PriorityResult(
            symbol=candidate.symbol, setup_type=candidate.setup_type,
            priority_status=STATUS_INSUFFICIENT_ROLLING_SAMPLE,
            expectancy_sample_end_utc=None, expectancy_sample_n=n, expectancy_value=None,
            spread_ratio=spread_ratio, priority_score=None,
        )

    sample = sorted(history_before_t, key=lambda o: o.resolved_at_utc)[-config.rolling_sample_trades:]
    wins = [o.r_multiple for o in sample if o.r_multiple > 0]
    losses = [o.r_multiple for o in sample if o.r_multiple <= 0]
    win_rate = len(wins) / len(sample)
    loss_rate = len(losses) / len(sample)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    e_roll = win_rate * avg_win - loss_rate * avg_loss
    priority_score = e_roll / spread_ratio if spread_ratio else None

    return PriorityResult(
        symbol=candidate.symbol, setup_type=candidate.setup_type, priority_status=STATUS_SCORED,
        expectancy_sample_end_utc=sample[-1].resolved_at_utc, expectancy_sample_n=len(sample),
        expectancy_value=e_roll, spread_ratio=spread_ratio, priority_score=priority_score,
    )


@dataclass(frozen=True)
class RankedCandidate:
    candidate: Candidate
    priority_result: PriorityResult
    rank: int
    action: str  # always WOULD_PRIORITIZE during OFFLINE_RESEARCH -- never EXECUTE


def rank_candidates(
    candidates: Sequence[Candidate],
    priority_results: Sequence[PriorityResult],
    *,
    config: PriorityConfig,
) -> tuple:
    """Deterministic tie-break sequence (spec section 22):
    1. valid economic/risk eligibility
    2. adequate rolling expectancy score (STATUS_SCORED beats INSUFFICIENT_ROLLING_SAMPLE)
    3. higher priority score
    4. lower friction burden
    5. deterministic symbol preference (config fallback order, then alphabetical)
    6. deterministic setup/campaign identity (setup_type, then symbol, as a final tiebreak)
    All candidates are retained in the output regardless of eligibility/rank -- ranking
    never discards a candidate (spec section 19).
    """
    paired = list(zip(candidates, priority_results))

    def symbol_rank(symbol: str) -> int:
        try:
            return config.deterministic_symbol_fallback_order.index(symbol)
        except ValueError:
            return len(config.deterministic_symbol_fallback_order)

    def sort_key(pair):
        cand, res = pair
        eligible = cand.news_eligible and cand.campaign_risk_eligible
        has_score = res.priority_status == STATUS_SCORED
        score = res.priority_score if res.priority_score is not None else float("-inf")
        return (
            0 if eligible else 1,
            0 if has_score else 1,
            -score,
            cand.friction_burden,
            symbol_rank(cand.symbol),
            cand.symbol,
            cand.setup_type,
        )

    ordered = sorted(paired, key=sort_key)
    ranked = []
    for idx, (cand, res) in enumerate(ordered, start=1):
        ranked.append(RankedCandidate(candidate=cand, priority_result=res, rank=idx, action=WOULD_PRIORITIZE))
    return tuple(ranked)
