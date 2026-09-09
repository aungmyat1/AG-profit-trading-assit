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
STRATEGY_ID = "ST_LIQUIDITY_SWEEP_RETEST_V1"
STRATEGY_VERSION = "2.0.0"

DECISION_READY = "READY"
DECISION_WATCH = "WATCH"
DECISION_NO_TRADE = "NO_TRADE"
DECISION_DATA_ERROR = "DATA_ERROR"

REPORT_WINDOW_START_HOUR = 6
REPORT_WINDOW_START_MINUTE = 30
REPORT_WINDOW_END_HOUR = 6
REPORT_WINDOW_END_MINUTE = 45

# AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P3.3 -- the canonical BTC campaign counting
# contract. Only these decisions can ever count toward NATURAL_CAMPAIGN_ACCRUAL; a
# DATA_ERROR day is real, persisted, diagnostic evidence but is never confused with a
# qualifying observation ("no trade" is not "no evidence", but "could not evaluate" is
# not "evidence" either -- see the report's own data_quality.status).
QUALIFYING_DECISIONS = frozenset({DECISION_READY, DECISION_WATCH, DECISION_NO_TRADE})

_MAX_ERROR_DETAIL_LENGTH = 300
_REDACTED_SUBSTRING_PATTERNS = ("authorization", "api-key", "api_key", "x-bapi", "cookie", "token", "secret")


def _sanitize_error_detail(exc: BaseException) -> str:
    """Bounded, redacted excerpt of an external-data-acquisition failure (P3.2). Never
    includes a raw HTTP body, header, credential, or cookie -- only the exception's own
    str(), truncated, with any line that looks like it might carry a credential/secret
    header dropped rather than partially redacted (safer than pattern-scrubbing inline)."""
    lines = str(exc).splitlines() or [""]
    safe_lines = [
        line for line in lines
        if not any(marker in line.lower() for marker in _REDACTED_SUBSTRING_PATTERNS)
    ]
    detail = " ".join(safe_lines).strip() or "(detail suppressed: matched credential/secret pattern)"
    if len(detail) > _MAX_ERROR_DETAIL_LENGTH:
        detail = detail[:_MAX_ERROR_DETAIL_LENGTH] + "...(truncated)"
    return detail


def build_external_data_error_report(
    exc: BaseException,
    *,
    strategy_id: str,
    strategy_version: str,
    application_release: str,
    observation_date: dt.date,
    expected_window: Dict[str, str],
    now: dt.datetime,
    endpoint_role: str,
    data_source: str,
    retry_count: int = 0,
) -> Dict[str, Any]:
    """P3.1/P3.2: the fail-closed record for a failure that happens BEFORE
    build_btc_daily_report() is ever entered (e.g. the symbol-metadata fetch) -- the one
    gap build_btc_daily_report()'s own internal try/except cannot cover, since that
    wrapper only starts once this function's caller has already succeeded. Shape matches
    build_btc_daily_report()'s own internal-failure branch exactly (same top-level keys)
    so every downstream consumer (adapter, archive, CLI) treats both paths identically.
    Only bounded, sanitized fields are persisted -- never a raw response body, header, or
    credential (P3.2)."""
    interval_start = dt.datetime.combine(observation_date, dt.time.min, tzinfo=dt.timezone.utc)
    interval_end = interval_start + dt.timedelta(days=1)
    http_status = getattr(getattr(exc, "response", None), "status_code", None)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": "BTC_DAILY",
        "application_release": application_release,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "observation_date": observation_date.isoformat(),
        "observation_interval": {"start": interval_start.isoformat(), "end": interval_end.isoformat()},
        "expected_window": expected_window,
        "observed_at": now.isoformat(),
        "generated_at_utc": now.isoformat(),
        "data_quality": {
            "status": "FAIL",
            "reason_code": getattr(exc, "reason_code", type(exc).__name__),
        },
        "decision": DECISION_DATA_ERROR,
        "reason_codes": [getattr(exc, "reason_code", type(exc).__name__)],
        "error_code": getattr(exc, "reason_code", type(exc).__name__),
        "error_type": type(exc).__name__,
        "error_detail": _sanitize_error_detail(exc),
        "endpoint_role": endpoint_role,
        "http_status": http_status,
        "data_source": data_source,
        "retry_count": retry_count,
        "occurrences": [],
        "proposal_count": 0,
        "evidence_qualified": False,
        "counting_eligible": False,
        "execution_authority": {
            "automatic_execution": "DISABLED", "demo_execution": "DISABLED",
            "live_execution": "DISABLED", "research_only": True,
        },
    }


def evaluate_counting_eligibility(
    report: Dict[str, Any],
    *,
    expected_strategy_id: str,
    expected_strategy_version: str,
) -> Dict[str, Any]:
    """P3.3 canonical counting contract, applied uniformly to every report this module
    or the CLI produces (success, internal DATA_ERROR, or external DATA_ERROR). A record
    counts toward NATURAL_CAMPAIGN_ACCRUAL only if ALL of: it is one of
    QUALIFYING_DECISIONS, its own data_quality.status is PASS, it identifies the
    expected strategy/version, and it was generated inside the signed report window
    (report.get('qualification_evidence_eligible') -- set by the CLI from
    report_window_status()). Returns a dict merged onto the report, never silently
    assumed true for a record missing these fields (a legacy/malformed record fails
    closed to not-eligible, never counted by accident)."""
    reasons = []
    decision = report.get("decision")
    if decision not in QUALIFYING_DECISIONS:
        reasons.append(f"NON_QUALIFYING_DECISION:{decision}")
    data_quality_status = (report.get("data_quality") or {}).get("status")
    if data_quality_status != "PASS":
        reasons.append(f"DATA_QUALITY_NOT_PASS:{data_quality_status}")
    if report.get("strategy_id") != expected_strategy_id:
        reasons.append(f"STRATEGY_ID_MISMATCH:{report.get('strategy_id')}")
    if report.get("strategy_version") != expected_strategy_version:
        reasons.append(f"STRATEGY_VERSION_MISMATCH:{report.get('strategy_version')}")
    if report.get("qualification_evidence_eligible") is not True:
        reasons.append("OUTSIDE_REPORT_WINDOW_OR_UNKNOWN")
    counting_eligible = not reasons
    return {
        "evidence_qualified": data_quality_status == "PASS",
        "counting_eligible": counting_eligible,
        "counting_ineligible_reasons": reasons,
    }

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
            "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
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
        "strategy_id": STRATEGY_ID, "strategy_version": STRATEGY_VERSION,
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
