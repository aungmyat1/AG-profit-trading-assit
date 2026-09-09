"""Pure MTF structure-alignment labeling (P17-P19).

Composes an `mtf_alignment` label from already-computed `market_structure.StructureResult
.state` values across an ordered HTF -> LTF timeframe sequence -- this module detects no
structure itself, only names the relationship between states that already exist. It is
NOT a bias engine: the label describes structural agreement/conflict, never
BULLISH/BEARISH/NEUTRAL trade bias (P19 -- bias remains a strategy-specific consumer's
decision, e.g. SESSION_BIAS_V1).

LOWER_TIMEFRAME_CANNOT_SILENTLY_OVERRIDE_HIGHER_TIMEFRAME (P18/SMC_TRAP_GUARD_V1): this
module never resolves a CONFLICT label into a single winning direction -- CONFLICT is
returned as-is for the consuming strategy to interpret under its own rules.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from market_structure.models import STATE_BULLISH, STATE_UNDEFINED

ALIGNMENT_UNKNOWN = "UNKNOWN"


def compute_mtf_alignment(ordered_states: Sequence[Tuple[str, Optional[str]]]) -> str:
    """`ordered_states` is a (timeframe, state_or_None) sequence ordered HTF-first,
    LTF-last -- the caller's own ordering, never assumed/hardcoded here (P17: no fixed
    D1/H4/H1/M15 hierarchy). Returns:

      UNKNOWN                       -- fewer than 2 timeframes, or any state missing/None
      ALIGNED_<STATE>                -- every timeframe reports the identical state
      HTF_<HTF>_LTF_TRANSITION       -- HTF resolved, LTF is STRUCTURE_STATE_UNDEFINED
      HTF_UNDEFINED_LTF_<LTF>        -- HTF is STRUCTURE_STATE_UNDEFINED, LTF resolved
      HTF_<HTF>_LTF_CONFLICT         -- both resolved and they disagree
    """
    if len(ordered_states) < 2:
        return ALIGNMENT_UNKNOWN
    states = [s for _, s in ordered_states]
    if any(s is None for s in states):
        return ALIGNMENT_UNKNOWN

    htf_state = states[0]
    ltf_state = states[-1]

    if all(s == htf_state for s in states):
        return f"ALIGNED_{htf_state}"

    if htf_state == STATE_UNDEFINED and ltf_state != STATE_UNDEFINED:
        return f"HTF_UNDEFINED_LTF_{ltf_state}"
    if htf_state != STATE_UNDEFINED and ltf_state == STATE_UNDEFINED:
        return f"HTF_{htf_state}_LTF_TRANSITION"
    if htf_state == ltf_state:
        # Endpoints agree but an intermediate timeframe differs -- still name it a
        # conflict rather than silently rounding up to ALIGNED, since not every
        # timeframe agrees.
        return f"HTF_{htf_state}_LTF_{htf_state}_INTERMEDIATE_CONFLICT"
    return f"HTF_{htf_state}_LTF_CONFLICT"
