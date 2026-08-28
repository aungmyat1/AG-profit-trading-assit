"""SessionUniverse (spec section 7): the SESSION_TRADE workflow's configured-symbol
source. Reuses strategy_engine.loader.load_strategy verbatim rather than duplicating a
symbol list -- ST_ASIAN_SWEEP_5R_V1.yaml's `instruments` field is this repo's only
strategy whose regime/setup engine (strategy_engine.session.route_completed_session) is
actually implemented locally; SESSION_TRADE_V1 (strategies/session_trade/contract.yaml,
4 symbols) is a DIFFERENT strategy whose engine lives in an external repository (see that
file's `source_of_truth`) and must not be ported here (section 3/6). This is a real
mismatch against this spec's "four-pair" wording, not a rule this module resolves --
surfaced as an open gap rather than silently picking a symbol count.

DEFAULT_STRATEGY_PATH follows this repo's own convention for locating strategy yaml
files (relative to the process cwd == repo root), matching scripts/run_strategy.py and
tests/test_execution_intent_builder.py -- no new path-resolution convention invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from strategy_engine.loader import load_strategy

DEFAULT_STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


@dataclass(frozen=True)
class SessionUniverse:
    strategy_id: str
    configured_symbols: Tuple[str, ...]
    reference_session_names: Tuple[str, ...]
    source_path: str


def load_session_universe(path: str = DEFAULT_STRATEGY_PATH) -> SessionUniverse:
    strategy = load_strategy(path)
    reference_session_names = tuple(
        pair.reference_session.name for pair in strategy.session_pairs
    )
    return SessionUniverse(
        strategy_id=strategy.strategy_id,
        configured_symbols=strategy.instruments,
        reference_session_names=reference_session_names,
        source_path=path,
    )
