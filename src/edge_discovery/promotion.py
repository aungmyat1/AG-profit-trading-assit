"""Phase 9 -- preregistered promotion policy (research prioritization gate).

FAST_SCREEN_PROMOTION_POLICY_V1, frozen BEFORE any BTCUSD/ETHUSD CFD economic result
exists in this repository. This gate prioritizes research attention; it NEVER verifies
an edge -- a PASS maps to FROZEN_FOR_VERIFICATION + FULL_VERIFICATION_PENDING, and this
module is structurally unable to emit EDGE_VERIFIED (models.PromotionDecision raises).

Preregistered criteria, judged on the preregistered SCREEN_SCENARIO (friction.BASE):

  INCONCLUSIVE  if N < MIN_SAMPLE_N (= 30). Rationale: below ~30 trades the sign of a
                per-trade expectancy of realistic magnitude is dominated by noise; the
                value is fixed here a priori and is NOT tuned to any candidate result
                (none exist at freeze time). Inconclusive is never PASS.
  FAIL          if NET_EXPECTANCY_R <= 0            -> NEGATIVE_NET_EXPECTANCY
                   (plus NEGATIVE_GROSS_EXPECTANCY when gross <= 0,
                    plus FRICTION_DESTROYS_EDGE when gross > 0 but net <= 0)
                if PROFIT_FACTOR_NET <= 1.0         -> NET_PROFIT_FACTOR_LE_1
  PASS          otherwise.

No other thresholds exist; nothing here may be loosened to let a specific candidate
through (Phase 10: after results exist, the candidate is immutable -- improvements are
future candidates, e.g. a C002 hypothesis).
"""
from __future__ import annotations

from typing import Mapping, Sequence, Tuple

from .models import (CandidateStatus, FastScreenResult, PromotionDecision)

PROMOTION_POLICY_ID = "FAST_SCREEN_PROMOTION_POLICY_V1"
MIN_SAMPLE_N = 30

# Stable failure reason codes (Phase 10 vocabulary).
NEGATIVE_NET_EXPECTANCY = "NEGATIVE_NET_EXPECTANCY"
NEGATIVE_GROSS_EXPECTANCY = "NEGATIVE_GROSS_EXPECTANCY"
FRICTION_DESTROYS_EDGE = "FRICTION_DESTROYS_EDGE"
NET_PROFIT_FACTOR_LE_1 = "NET_PROFIT_FACTOR_LE_1"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

FAST_SCREEN_PASS = "FAST_SCREEN_PASS"
FAST_SCREEN_FAIL = "FAST_SCREEN_FAIL"
FAST_SCREEN_INCONCLUSIVE = "FAST_SCREEN_INCONCLUSIVE"

ALLOWED_OUTCOMES: Tuple[str, ...] = (FAST_SCREEN_PASS, FAST_SCREEN_FAIL,
                                     FAST_SCREEN_INCONCLUSIVE)


def decide(candidate_id: str, metrics: Mapping, dataset_ids: Sequence[str],
           friction_scenario: str) -> Tuple[FastScreenResult, PromotionDecision]:
    """Apply the preregistered policy to a Phase-8 metric block."""
    n = int(metrics.get("N") or 0)
    gross_exp = metrics.get("GROSS_EXPECTANCY_R")
    net_exp = metrics.get("NET_EXPECTANCY_R")
    pf_net = metrics.get("PROFIT_FACTOR_NET")

    codes: list = []
    if n < MIN_SAMPLE_N:
        status = FAST_SCREEN_INCONCLUSIVE
        codes.append(INSUFFICIENT_SAMPLE)
        next_status = CandidateStatus.FAST_SCREEN_INCONCLUSIVE
        full_verification = "NOT_EVALUATED"
    else:
        if net_exp is None or net_exp <= 0:
            codes.append(NEGATIVE_NET_EXPECTANCY)
            if gross_exp is not None and gross_exp <= 0:
                codes.append(NEGATIVE_GROSS_EXPECTANCY)
            elif gross_exp is not None and gross_exp > 0:
                codes.append(FRICTION_DESTROYS_EDGE)
        if pf_net is not None and pf_net <= 1.0:
            codes.append(NET_PROFIT_FACTOR_LE_1)
        if codes:
            status = FAST_SCREEN_FAIL
            next_status = CandidateStatus.FAST_SCREEN_FAIL
            full_verification = "NOT_EVALUATED"
        else:
            status = FAST_SCREEN_PASS
            next_status = CandidateStatus.FROZEN_FOR_VERIFICATION
            full_verification = "FULL_VERIFICATION_PENDING"

    screen = FastScreenResult(candidate_id=candidate_id, dataset_ids=tuple(dataset_ids),
                              friction_scenario=friction_scenario, metrics=dict(metrics),
                              status=status, reason_codes=tuple(codes),
                              edge_verified=False)
    decision = PromotionDecision(candidate_id=candidate_id, decision=status,
                                 reason_codes=tuple(codes), next_status=next_status,
                                 full_verification_status=full_verification,
                                 edge_verified=False, policy_id=PROMOTION_POLICY_ID)
    return screen, decision
