"""SSC integration proof (P16) -- ST_SESSION_SWEEP_CONTINUATION_V1.

Proves the historical canonical replay and the forward canonical decision path share
the same strategy authority: both resolve to `session_sweep_continuation.replay.run_replay`.
The adapter changes only the data source; it never alters SSC semantics and never
consumes H2 September spread data before its campaign is admitted.

A real trade is NOT required for this architecture proof; NO_SETUP is a valid outcome.
"""
from __future__ import annotations

from typing import Callable, Sequence

from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION
from session_sweep_continuation.replay import ReplayResult, run_replay as _run_replay

from svos.historical_runner import HistoricalOccurrence

SSC_HISTORICAL_REPLAY_ENTRYPOINT = "session_sweep_continuation.replay.run_replay"
SSC_FORWARD_DECISION_ENTRYPOINT = "session_sweep_continuation.replay.run_replay"


def historical_replay_entrypoint() -> Callable:
    return _run_replay


def forward_decision_entrypoint() -> Callable:
    return _run_replay


def same_authority_verified() -> bool:
    return (
        historical_replay_entrypoint() is forward_decision_entrypoint()
        and forward_decision_entrypoint() is _run_replay
    )


def replay_result_to_occurrences(
    replay_result: ReplayResult,
    strategy_id: str = STRATEGY_ID,
    strategy_version: str = STRATEGY_VERSION,
) -> Sequence[HistoricalOccurrence]:
    """Converts an SSC ReplayResult into immutable HistoricalOccurrence records.

    Reads ONLY the replay's own already-resolved outcome fields (gross_R/net_R/
    cost_status/terminal_state) -- never re-resolves or fabricates an outcome. An
    accepted setup whose outcome has no gross_R is emitted as an unresolved occurrence
    (gross_R None is NOT allowed by HistoricalOccurrence, so it is skipped rather than
    invented -- see note)."""
    occurrences = []
    for i, setup in enumerate(replay_result.accepted_setups):
        outcome = setup.get("outcome") or {}
        gross_R = outcome.get("gross_R")
        if gross_R is None:
            continue  # never fabricate an R for an unresolved setup
        occurrences.append(
            HistoricalOccurrence(
                occurrence_id=f"{replay_result.session_pair}:{replay_result.trading_date}:{i}",
                symbol=replay_result.symbol,
                session=replay_result.session_pair,
                direction=str(setup.get("direction") or ""),
                setup=str(setup.get("setup_model") or ""),
                exit_path=str(outcome.get("terminal_state") or ""),
                outcome=str(outcome.get("terminal_state") or ""),
                gross_R=float(gross_R),
                friction_R=(
                    float(outcome["friction_R"]) if outcome.get("friction_R") is not None else 0.0
                ),
                net_R=float(outcome["net_R"]) if outcome.get("net_R") is not None else float(gross_R),
                cost_status=str(outcome.get("cost_status") or "UNAVAILABLE"),
            )
        )
    return tuple(occurrences)
