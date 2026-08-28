"""OR-consolidated alert routing (spec sections 20-27) and the M5 handoff (spec
sections 21-22). Nothing here re-detects gap/POI/sweep evidence -- callers supply
SMCConditionResult objects already built by conditions.py. The M5 confirmation step
reuses entry_confirmation.engine.evaluate_entry_confirmation (ENTRY_CONFIRMATION_V1)
verbatim -- timeframe="M5" is just a caller-supplied request field, not a new engine.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Set, Tuple

from entry_confirmation.engine import evaluate_entry_confirmation
from entry_confirmation.models import EntryConfirmationRequest, EntryConfirmationResult

from .models import (
    ALERT_STATE_CONFIRMED,
    ALERT_STATE_NOT_CONFIRMED,
    ALERT_STATE_WAITING_M5_CONFIRMATION,
    SMCConditionAlert,
    SMCConditionResult,
)


def request_m5_confirmation(request: EntryConfirmationRequest) -> EntryConfirmationResult:
    """"Go to 5M chart" (spec section 21): request closed M5 candle data (caller's job,
    via `request`) and run the existing M5 confirmation capability -- never a new
    candle-by-candle scanner."""
    return evaluate_entry_confirmation(request)


class SMCConditionWatcher:
    """OR-routes E1/E2/E3 results into at most one consolidated alert per genuinely new
    triggering event (spec section 24's dedup identity: strategy_id, symbol, and each
    triggered condition's own source_key). Repeated polling of an already-alerted
    condition set returns None, not a duplicate alert."""

    def __init__(self, seen_keys: Optional[Set[Tuple]] = None):
        self._seen: Set[Tuple] = seen_keys if seen_keys is not None else set()

    def evaluate(
        self,
        strategy_id: str,
        symbol: str,
        e1_result: Optional[SMCConditionResult] = None,
        e2_result: Optional[SMCConditionResult] = None,
        e3_result: Optional[SMCConditionResult] = None,
        current_price: Optional[float] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> Optional[SMCConditionAlert]:
        all_results = (e1_result, e2_result, e3_result)
        triggered = [r for r in all_results if r is not None and r.triggered]
        if not triggered:
            return None  # SMC_STATE = WATCHING -- no alert

        dedup_key = (strategy_id, symbol, tuple(sorted((r.condition_id, r.source_key) for r in triggered)))
        if dedup_key in self._seen:
            return None  # same underlying event(s) already alerted -- no duplicate alert
        self._seen.add(dedup_key)

        triggered_conditions = tuple(r.condition_id for r in triggered)
        primary = triggered[0]
        directions = {r.directional_implication for r in triggered if r.directional_implication is not None}
        # Multiple triggered conditions implying opposite directions is a real ambiguity
        # (mirrors route.classify_route's own MULTIPLE-with-no-priority stance) --
        # preserved as None rather than guessed.
        direction = directions.pop() if len(directions) == 1 else None

        reason_codes = tuple(f"{r.condition_id}_TRIGGERED" for r in triggered)

        alert_id = strategy_id + ":" + symbol + ":" + "+".join(triggered_conditions) + ":" + \
            "+".join(str(r.source_key) for r in triggered)

        return SMCConditionAlert(
            alert_id=alert_id,
            strategy_id=strategy_id,
            symbol=symbol,
            triggered_conditions=triggered_conditions,
            primary_condition=primary.condition_id,
            direction=direction,
            e1_result=e1_result,
            e2_result=e2_result,
            e3_result=e3_result,
            current_price=current_price,
            triggered_at=evaluation_time,
            next_stage="M5_CONFIRMATION",
            alert_state=ALERT_STATE_WAITING_M5_CONFIRMATION,
            confirmation_state="PENDING",
            execution_eligible=False,
            reason_codes=reason_codes,
        )

    @staticmethod
    def advance_with_m5_confirmation(
        alert: SMCConditionAlert, m5_request: EntryConfirmationRequest,
    ) -> SMCConditionAlert:
        """Spec section 40: CONFIRMED/NOT_CONFIRMED/INDETERMINATE from the real M5
        engine, never fabricated; execution_eligible stays False regardless (spec
        section 34 -- alert confirmation is not execution authority)."""
        from dataclasses import replace

        result = request_m5_confirmation(m5_request)
        overall = result.overall_state.value
        if overall == "CONFIRMED":
            alert_state = ALERT_STATE_CONFIRMED
        elif overall == "NOT_CONFIRMED":
            alert_state = ALERT_STATE_NOT_CONFIRMED
        else:  # PARTIAL / INDETERMINATE -- not yet resolved, still waiting
            alert_state = ALERT_STATE_WAITING_M5_CONFIRMATION

        return replace(
            alert,
            alert_state=alert_state,
            confirmation_state=overall,
            execution_eligible=False,
        )
