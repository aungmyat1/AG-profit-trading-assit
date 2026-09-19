from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from historical_replay.evaluation_context import ReplayEvaluationContext, ReplayEvaluationError
from historical_replay.symbol_metadata_manifest import HistoricalSymbolMetadataManifest
from session_sweep_continuation.canonical_consumer import CanonicalCycleResult, run_canonical_shadow_cycle
from session_sweep_continuation.sessions import session_windows_from_config


@dataclass(frozen=True)
class SSCReplayResult:
    event_id: str
    cycle: Optional[CanonicalCycleResult]
    status: str
    reason_codes: tuple[str, ...] = ()


def evaluate_ssc_replay(context: ReplayEvaluationContext, *, manifest: HistoricalSymbolMetadataManifest,
                        config: dict, session_pair_id: str, trading_date: date,
                        pip_size: float, pip_value_per_lot: float = 10.0,
                        include_m1_outcome: bool = False) -> SSCReplayResult:
    """Run the existing SSC canonical consumer for a completed trade session."""
    windows = session_windows_from_config(config)[session_pair_id]
    ref_end = windows["reference"].bounds_for_date(trading_date)[1]
    trade_end = windows["trade"].bounds_for_date(trading_date)[1]
    if context.as_of < trade_end:
        return SSCReplayResult(context.event_id, None, "DEFERRED", ("COMPLETED_TRADE_SESSION_REQUIRED",))
    if "H1" not in context.timeframes or "M15" not in context.timeframes:
        raise ReplayEvaluationError("SSC requires H1 and M15 replay series")
    m15 = context.candles("M15")
    # Admit the canonical consumer only when the completed reference population
    # represented by the existing SSC session window is intact.  The context has
    # already applied the bound-series identity and closed-bar visibility rules;
    # this check only validates the required window's timestamps.
    ref_window = windows["reference"]
    ref_start, ref_end = ref_window.bounds_for_date(trading_date)
    reference = tuple(c for c in m15 if ref_start <= c.time < ref_end)
    expected = int((ref_end - ref_start) / timedelta(minutes=15))
    expected_times = tuple(ref_start + timedelta(minutes=15 * i) for i in range(expected))
    actual_times = tuple(c.time for c in reference)
    if (context.as_of < ref_end or actual_times != expected_times or
            any(c.time + timedelta(minutes=15) > context.as_of for c in reference)):
        return SSCReplayResult(context.event_id, None, "SESSION_INCOMPLETE",
                               ("SSC_REFERENCE_SESSION_INCOMPLETE",))
    m1 = context.candles("M1") if include_m1_outcome else None
    if include_m1_outcome and "M1" not in context.timeframes:
        raise ReplayEvaluationError("M1 outcome mode requires an M1 replay series")
    cycle = run_canonical_shadow_cycle(
        h1_store=context.provider.store_view(), manifest=manifest, m15_candles=m15,
        config=config, symbol=context.symbol, session_pair_id=session_pair_id,
        trading_date=trading_date, decision_time=ref_end, pip_size=pip_size,
        pip_value_per_lot=pip_value_per_lot, m1_candles=m1,
    )
    return SSCReplayResult(context.event_id, cycle, "COMPLETE")
