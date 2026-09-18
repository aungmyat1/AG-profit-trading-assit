"""Tests for svos.adapters.ssc -- same-strategy-authority proof (P16)."""
from __future__ import annotations

import session_sweep_continuation.replay as ssc_replay

from svos.adapters.ssc import (
    SSC_FORWARD_DECISION_ENTRYPOINT,
    SSC_HISTORICAL_REPLAY_ENTRYPOINT,
    forward_decision_entrypoint,
    historical_replay_entrypoint,
    replay_result_to_occurrences,
)


def test_same_authority_historical_and_forward():
    assert SSC_HISTORICAL_REPLAY_ENTRYPOINT == "session_sweep_continuation.replay.run_replay"
    assert SSC_FORWARD_DECISION_ENTRYPOINT == "session_sweep_continuation.replay.run_replay"
    assert historical_replay_entrypoint() is ssc_replay.run_replay
    assert forward_decision_entrypoint() is ssc_replay.run_replay
    assert historical_replay_entrypoint() is forward_decision_entrypoint()


def test_replay_result_to_occurrences_never_fabricates_outcome():
    from session_sweep_continuation.replay import ReplayResult

    result = ReplayResult(
        symbol="EURUSD", session_pair="ASIAN_LONDON", trading_date="2026-09-01",
        regime="TREND_UP", campaign=None, accepted_setups=[], rejected_setups=[], steps=[],
    )
    assert replay_result_to_occurrences(result) == ()


def test_occurrences_carry_resolved_outcomes():
    from session_sweep_continuation.replay import ReplayResult

    result = ReplayResult(
        symbol="EURUSD", session_pair="ASIAN_LONDON", trading_date="2026-09-01",
        regime="TREND_UP", campaign=None,
        accepted_setups=[
            {
                "setup_model": "S2", "direction": "LONG", "entry_price": 1.0, "stop_price": 0.998,
                "outcome": {"terminal_state": "RESOLVED_RUNNER_TARGET", "gross_R": 2.0,
                            "net_R": 1.9, "cost_status": "KNOWN", "friction_R": 0.1},
            },
            {
                "setup_model": "S1", "direction": "SHORT", "entry_price": 1.0, "stop_price": 1.002,
                "outcome": {"terminal_state": "UNRESOLVED_NO_DATA", "gross_R": None},
            },
        ],
        rejected_setups=[], steps=[],
    )
    occurrences = replay_result_to_occurrences(result)
    assert len(occurrences) == 1  # unresolved setup skipped, never fabricated
    assert occurrences[0].gross_R == 2.0
    assert occurrences[0].net_R == 1.9
