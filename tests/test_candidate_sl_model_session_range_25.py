"""Focused tests for the MODEL_A (SESSION_RANGE_25) candidate stop-loss model.

RESEARCH_CANDIDATE only -- candidate_version=1.1.2-RC1, authority=NONE. Does not touch
the frozen v1.1.1 live setup path (strategy_engine.session.setups.entry_2_sweep is not
imported for computation here, only its Direction enum for typing).

See AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION for the mandatory test
gate this file satisfies (A-G).
"""
import pytest

from strategy_engine.session.candidate_stop_models import (
    CANDIDATE_MODEL_ID,
    CANDIDATE_VERSION,
    CandidateStopModelError,
    session_range_25_stop,
)
from strategy_engine.session.setups import Direction


# A. LONG: session range = 20 pips, stop_loss_range_pct = 0.25 -> expected SL distance = 5 pips
def test_long_expected_sl_distance():
    result = session_range_25_stop(
        direction=Direction.LONG, entry=1.10500, box_high=1.10700, box_low=1.10500,
        stop_loss_range_pct=0.25,
    )
    assert result.reference_session_range == pytest.approx(0.00200)  # 20 pips
    assert result.stop_distance == pytest.approx(0.00050)  # 5 pips
    assert result.stop_loss == pytest.approx(1.10500 - 0.00050)
    assert result.model == CANDIDATE_MODEL_ID
    assert result.candidate_version == CANDIDATE_VERSION


# B. SHORT: same expected geometry in the opposite direction
def test_short_expected_sl_distance():
    result = session_range_25_stop(
        direction=Direction.SHORT, entry=1.10700, box_high=1.10700, box_low=1.10500,
        stop_loss_range_pct=0.25,
    )
    assert result.stop_distance == pytest.approx(0.00050)
    assert result.stop_loss == pytest.approx(1.10700 + 0.00050)


# C. configuration propagation: changing the candidate parameter must deterministically
# change the calculated SL distance (0.20 -> 4 pips, 0.25 -> 5 pips, 0.30 -> 6 pips on a
# 20-pip session range).
@pytest.mark.parametrize("pct,expected_pips", [(0.20, 4.0), (0.25, 5.0), (0.30, 6.0)])
def test_propagation_pct_changes_distance(pct, expected_pips):
    result = session_range_25_stop(
        direction=Direction.LONG, entry=1.10500, box_high=1.10700, box_low=1.10500,
        stop_loss_range_pct=pct,
    )
    assert result.stop_distance == pytest.approx(expected_pips * 0.0001, abs=1e-9)


# D. invalid range: session range <= 0 -> fail closed
@pytest.mark.parametrize("box_high,box_low", [(1.10500, 1.10500), (1.10400, 1.10500)])
def test_nonpositive_session_range_fails_closed(box_high, box_low):
    with pytest.raises(CandidateStopModelError):
        session_range_25_stop(
            direction=Direction.LONG, entry=1.10500, box_high=box_high, box_low=box_low,
            stop_loss_range_pct=0.25,
        )


# E. missing required parameter: stop_loss_range_pct missing/invalid -> fail closed
@pytest.mark.parametrize("pct", [None, 0.0, -0.25, float("nan")])
def test_missing_or_invalid_pct_fails_closed(pct):
    with pytest.raises(CandidateStopModelError):
        session_range_25_stop(
            direction=Direction.LONG, entry=1.10500, box_high=1.10700, box_low=1.10500,
            stop_loss_range_pct=pct,
        )


# F. zero/negative calculated stop distance must not produce a usable result (covered by
# D/E above since stop_distance <= 0 can only arise from a non-positive range or pct, both
# already fail closed) -- explicit direct check on the boundary case too.
def test_zero_computed_distance_fails_closed():
    with pytest.raises(CandidateStopModelError):
        session_range_25_stop(
            direction=Direction.LONG, entry=1.10500, box_high=1.10500, box_low=1.10500,
            stop_loss_range_pct=0.25,
        )


# G. deterministic repeatability: same input must produce exactly the same stop value
def test_deterministic_repeatability():
    kwargs = dict(direction=Direction.SHORT, entry=1.34942, box_high=1.35119, box_low=1.34755,
                  stop_loss_range_pct=0.25)
    r1 = session_range_25_stop(**kwargs)
    r2 = session_range_25_stop(**kwargs)
    assert r1 == r2


def test_unrecognized_direction_fails_closed():
    with pytest.raises(CandidateStopModelError):
        session_range_25_stop(
            direction="UP", entry=1.10500, box_high=1.10700, box_low=1.10500,
            stop_loss_range_pct=0.25,
        )
