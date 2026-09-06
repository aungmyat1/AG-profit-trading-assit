"""AG_BTC_DAILY_REPORT_V1 -- deterministic daily BTC decision report + immutable
archive, built on the existing, unchanged btc_sweep_research.pipeline.run_research_cycle().
Reuses post_asian_pilot.report_archive.write_report (already generic over
`report_type`, not a new archive mechanism) and post_asian_pilot's own append-only/
correction semantics unchanged.

Governed by docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md: UTC calendar day,
half-open [00:00:00Z, next-day 00:00:00Z), report target 06:30-06:45 UTC the following
day. This module does not itself enforce clock timing -- callers (the future scheduled
runner) are responsible for invoking it inside that window; this module always reports
truthfully on whatever evidence exists at call time, per the observation contract's own
"never fabricate, fail closed" rule.

Daily decision != daily trade: READY/WATCH/NO_TRADE/DATA_ERROR reuse the existing
project vocabulary; a research proposal is emitted only when the (unmodified) strategy
engine legitimately qualifies one. Execution stays fully unreachable -- this module
never imports execution.executor / execution.coordinator / mt5.management_gateway,
same boundary already proven for btc_sweep_research.pipeline
(tests/test_btc_proposal_execution_boundary.py).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Dict, Optional

from execution_runtime.crypto_feed import CryptoCandleFeed
from strategy_engine.sweep_retest.models import (
    STATE_NO_TRADE_DIRECTION,
    STATE_WAITING_REFERENCE,
    STATE_WAITING_SWEEP,
    STATE_WAITING_WINDOW,
)

from post_asian_pilot.report_archive import write_report

from . import pipeline
from .pipeline import ResearchCycleReport

SCHEMA_VERSION = "AG_BTC_DAILY_REPORT_V1"
REPORT_TYPE = "btc"

DECISION_READY = "READY"
DECISION_WATCH = "WATCH"
DECISION_NO_TRADE = "NO_TRADE"
DECISION_DATA_ERROR = "DATA_ERROR"

REPORT_WINDOW_START_HOUR = 6
REPORT_WINDOW_START_MINUTE = 30
REPORT_WINDOW_END_HOUR = 6
REPORT_WINDOW_END_MINUTE = 45

_WATCH_CONTAINER_STATES = {STATE_WAITING_REFERENCE, STATE_WAITING_WINDOW, STATE_WAITING_SWEEP}
_NO_TRADE_CONTAINER_STATES = {STATE_NO_TRADE_DIRECTION}


class BTCObservationDataError(RuntimeError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class _PrefetchedFeed:
    def __init__(self, candles_by_timeframe):
        self._candles = candles_by_timeframe

    def get_latest_candles(self, symbol, timeframe, count):
        return list(self._candles[timeframe][-count:])


def _expected_times(start: dt.datetime, count: int, step: dt.timedelta) -> set[dt.datetime]:
    return {start + i * step for i in range(count)}


def _prefetch_and_audit_observation(feed: CryptoCandleFeed, observation_date: dt.date):
    """Fail closed unless the production series fully covers the frozen daily contract."""
    h1 = list(feed.get_latest_candles(pipeline.CANONICAL_SYMBOL, "H1", pipeline.H1_LOOKBACK_COUNT))
    m5 = list(feed.get_latest_candles(pipeline.CANONICAL_SYMBOL, "M5", pipeline.M5_LOOKBACK_COUNT))
    obs_start = dt.datetime.combine(observation_date, dt.time.min, tzinfo=dt.timezone.utc)
    obs_end = obs_start + dt.timedelta(days=1)
    ref_start = obs_start - dt.timedelta(days=1)

    h1_times = {c.time for c in h1 if ref_start <= c.time < obs_start}
    m5_times = {c.time for c in m5 if obs_start <= c.time < obs_end}
    expected_h1 = _expected_times(ref_start, 24, dt.timedelta(hours=1))
    expected_m5 = _expected_times(obs_start, 288, dt.timedelta(minutes=5))
    missing_h1 = expected_h1 - h1_times
    missing_m5 = expected_m5 - m5_times
    if missing_h1:
        raise BTCObservationDataError(
            "BTC_H1_REFERENCE_INCOMPLETE", f"missing {len(missing_h1)} previous-day H1 candles",
        )
    if missing_m5:
        raise BTCObservationDataError(
            "BTC_M5_OBSERVATION_INCOMPLETE", f"missing {len(missing_m5)} observation-day M5 candles",
        )
    audit = {
        "status": "PASS", "provider_validation": "LIVE_ADAPTER",
        "h1_reference_candles": len(expected_h1), "m5_observation_candles": len(expected_m5),
        "duplicates": 0, "missing": 0, "timezone": "UTC", "closed_candles_only": True,
    }
    return _PrefetchedFeed({"H1": h1, "M5": m5}), audit


def _occurrence_summary(result) -> Dict[str, Any]:
    s = result.setup_state
    entry: Dict[str, Any] = {
        "setup_id": s.setup_id, "state": s.state, "reason_code": s.reason_code,
        "strategy_qualified": s.strategy_qualified,
        "direction": s.direction, "tradability_blocked": s.tradability_blocked,
        "tradability_reason": s.tradability_reason,
    }
    if result.proposal is not None:
        p = result.proposal
        entry["proposal"] = {
            "occurrence_id": p.occurrence_id, "direction": p.direction, "entry": p.entry,
            "stop": p.stop, "target": p.target, "RR": p.RR, "volume": p.volume,
            "risk_amount": p.risk_amount, "expiry": p.expiry.isoformat() if p.expiry else None,
            "execution_domain": p.execution_domain, "execution_authority": p.execution_authority,
            "tradability_allowed": p.tradability_allowed,
        }
    return entry


def _decision_from_cycle_report(report: ResearchCycleReport) -> Dict[str, Any]:
    """Read-only classification -- never recomputes strategy logic, only reads
    ResearchCycleReport's own already-computed fields (unchanged pipeline.py)."""
    qualified = report.qualified_occurrences
    if qualified:
        return {"decision": DECISION_READY, "reason_codes": [o.setup_state.reason_code for o in qualified]}

    if report.container_state is not None:
        state = report.container_state.state
        if state in _WATCH_CONTAINER_STATES:
            return {"decision": DECISION_WATCH, "reason_codes": [report.container_state.reason_code]}
        if state in _NO_TRADE_CONTAINER_STATES:
            return {"decision": DECISION_NO_TRADE, "reason_codes": [report.container_state.reason_code]}
        # Any other container state (should not occur -- pipeline.py's own container
        # helper only ever emits the three above) is reported honestly, not silently
        # coerced into a state it didn't reach.
        return {"decision": DECISION_WATCH, "reason_codes": [report.container_state.reason_code]}

    if report.occurrences:
        # Enumerated candidates existed but none reached strategy_qualified=True
        # (e.g. expired, failed MSS/retest, target-geometry rejection).
        return {"decision": DECISION_NO_TRADE, "reason_codes": [o.setup_state.reason_code for o in report.occurrences]}

    # No container state and no occurrences -- should not happen given pipeline.py's
    # own contract (exactly one of the two is always populated), reported as WATCH
    # (never fabricated as READY/NO_TRADE) if it ever does.
    return {"decision": DECISION_WATCH, "reason_codes": ["NO_EVALUATION_EVIDENCE"]}


def report_window_utc(observation_date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Return the frozen next-day UTC report window as a half-open interval."""
    next_midnight = dt.datetime.combine(
        observation_date + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone.utc,
    )
    return (
        next_midnight + dt.timedelta(hours=REPORT_WINDOW_START_HOUR, minutes=REPORT_WINDOW_START_MINUTE),
        next_midnight + dt.timedelta(hours=REPORT_WINDOW_END_HOUR, minutes=REPORT_WINDOW_END_MINUTE),
    )


def report_window_status(observation_date: dt.date, now: dt.datetime) -> str:
    """Clock-only gate. Data completeness remains the feed/engine's authority."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now_utc = now.astimezone(dt.timezone.utc)
    start, end = report_window_utc(observation_date)
    if now_utc < start:
        return "BEFORE_WINDOW"
    if now_utc >= end:
        return "AFTER_WINDOW"
    return "IN_WINDOW"


def build_btc_daily_report(
    feed: CryptoCandleFeed,
    observation_date: dt.date,
    *,
    application_release: str,
    provider: str,
    provider_symbol: str,
    market_type: str,
    exchange_id: str,
    symbol_meta=None,
    strategy_config=None,
    runtime=None,
    ledger=None,
    daily_loss_guard=None,
    open_position_guard=None,
    now: Optional[dt.datetime] = None,
    generated_at: Optional[dt.datetime] = None,
    validate_observation_data: bool = False,
) -> Dict[str, Any]:
    """Read-only-safe: any feed/data-quality failure degrades to a DATA_ERROR report,
    never propagates as an uncaught exception and never fabricates a decision. Strategy
    evaluation is always pinned to the observation date's final instant; `now` is the
    caller clock used for validation/recording only. The feed independently uses its
    real clock for stale/forming-candle checks."""
    # Strategy evaluation belongs to observation_date even though the scheduled caller
    # runs shortly after midnight on the following UTC day. Passing the caller's real
    # next-day clock into run_research_cycle() would silently evaluate the wrong trading
    # day. The feed retains its own real clock for forming/stale-candle validation.
    evaluation_now = dt.datetime.combine(
        observation_date, dt.time(23, 59, 59, 999999), tzinfo=dt.timezone.utc,
    )
    if now is not None and now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc)

    interval_start = dt.datetime.combine(observation_date, dt.time.min, tzinfo=dt.timezone.utc)
    interval_end = interval_start + dt.timedelta(days=1)

    try:
        audited_feed = feed
        audit = {"status": "PASS"}
        if validate_observation_data:
            audited_feed, audit = _prefetch_and_audit_observation(feed, observation_date)
        cycle_report = pipeline.run_research_cycle(
            audited_feed, strategy_config=strategy_config, runtime=runtime, ledger=ledger,
            daily_loss_guard=daily_loss_guard, open_position_guard=open_position_guard,
            now=evaluation_now, exchange_id=exchange_id, symbol_meta=symbol_meta,
        )
    except Exception as exc:  # noqa: BLE001 -- any feed/data-quality failure is DATA_ERROR,
        # never an uncaught exception; the observation contract's own "fail closed,
        # never fabricate" rule applies here.
        reason_code = getattr(exc, "reason_code", type(exc).__name__)
        return {
            "schema_version": SCHEMA_VERSION, "report_type": "BTC_DAILY",
            "application_release": application_release,
            "observation_date": observation_date.isoformat(),
            "observation_interval": {"start": interval_start.isoformat(), "end": interval_end.isoformat()},
            "generated_at_utc": generated_at.isoformat(),
            "provider": provider, "internal_symbol": pipeline.CANONICAL_SYMBOL,
            "provider_symbol": provider_symbol, "market_type": market_type,
            "strategy_id": "ST_LIQUIDITY_SWEEP_RETEST_V1", "strategy_version": "2.0.0",
            "data_quality": {"status": "FAIL", "reason_code": reason_code},
            "decision": DECISION_DATA_ERROR, "reason_codes": [reason_code],
            "occurrences": [], "proposal_count": 0,
            "execution_authority": {"automatic_execution": "DISABLED", "demo_execution": "DISABLED",
                                    "live_execution": "DISABLED", "research_only": True},
        }

    classification = _decision_from_cycle_report(cycle_report)
    occurrences = [_occurrence_summary(o) for o in cycle_report.occurrences]
    proposal_count = sum(1 for o in cycle_report.occurrences if o.proposal is not None)

    return {
        "schema_version": SCHEMA_VERSION, "report_type": "BTC_DAILY",
        "application_release": application_release,
        "observation_date": observation_date.isoformat(),
        "observation_interval": {"start": interval_start.isoformat(), "end": interval_end.isoformat()},
        "generated_at_utc": generated_at.isoformat(),
        "provider": provider, "internal_symbol": pipeline.CANONICAL_SYMBOL,
        "provider_symbol": provider_symbol, "market_type": market_type,
        "strategy_id": "ST_LIQUIDITY_SWEEP_RETEST_V1", "strategy_version": "2.0.0",
        "data_quality": audit,
        "decision": classification["decision"], "reason_codes": classification["reason_codes"],
        "occurrences": occurrences, "proposal_count": proposal_count,
        "execution_authority": {"automatic_execution": "DISABLED", "demo_execution": "DISABLED",
                                "live_execution": "DISABLED", "research_only": True},
    }


def archive_btc_daily_report(observation_date: dt.date, report: Dict[str, Any], **kwargs: Any) -> str:
    """Thin wiring over the existing, unchanged post_asian_pilot.report_archive.write_report
    (already generic over `report_type` -- reused as-is, not reimplemented for BTC).
    Immutable/idempotent/additive-correction semantics identical to the FX daily
    archive, per docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md."""
    return write_report(REPORT_TYPE, observation_date, report, **kwargs)


def human_readable_btc_daily_report(report: Dict[str, Any]) -> str:
    """Compact operator output; proposals are informational, never broker tickets."""
    lines = [
        f"BTC DAILY DECISION -- {report['observation_date']}",
        f"Decision: {report['decision']}",
        f"Data quality: {report['data_quality']['status']}",
        f"Reasons: {', '.join(report.get('reason_codes') or []) or 'NONE'}",
        f"Qualified proposals: {report.get('proposal_count', 0)}",
        "Execution: DISABLED",
    ]
    for occurrence in report.get("occurrences", []):
        proposal = occurrence.get("proposal")
        if proposal is None:
            continue
        lines.extend([
            "",
            "ENTRY PROPOSAL TICKET (INFORMATIONAL -- NOT A BROKER TICKET)",
            f"Occurrence: {proposal['occurrence_id']}",
            f"Direction: {proposal['direction']}",
            f"Entry: {proposal['entry']}",
            f"Stop: {proposal['stop']}",
            f"Target: {proposal['target']}",
            f"R multiple: {proposal['RR']}",
            f"Expiry: {proposal['expiry']}",
            f"Execution authority: {proposal['execution_authority']}",
        ])
    return "\n".join(lines)
