"""Deterministic occurrence-identity composer for BTC/crypto ST_LIQUIDITY_SWEEP_RETEST_V1
qualified setups (spec section 20).

engine.evaluate_setup()'s own `setup_id` parameter is CALLER-supplied (see engine.py's
module docstring / evaluate_setup signature -- it takes setup_id as an argument, never
generates one itself, since evaluate_setup is a pure function of its inputs and must not
change for this task). That makes this module's natural home: a runtime-layer helper the
BTC research pipeline calls BEFORE invoking evaluate_setup/SweepRetestRuntime, not a change
to engine.py itself.

Follows the repo's one established identity-hashing convention (proposals/
occurrence_identity.py, proposals/identity.py, historical_replay/stage1.py::_make_event_id):
deterministic hashlib.blake2b over a "|"-joined string of stable fields only -- never
wall-clock/random/poll-time input, so the same underlying setup always produces the same
id regardless of when or how many times it is (re-)observed.

Distinct from proposals/occurrence_identity.py's candidate_occurrence_id: that module is
specific to ST_LARGE_SMC_V1's M-model layers (setup_family / eligibility_interval /
M-candidate). This one is specific to ST_LIQUIDITY_SWEEP_RETEST_V1's crypto profile, keyed
per spec section 20 on (strategy_id, strategy_version, exchange, canonical_symbol,
reference_trading_day, direction, sweep_time, mss_time) -- the exact fields that jointly
make one qualified setup distinct from another (a different sweep, a different MSS, a
different day, or a different direction is always a genuinely different occurrence; the
same setup re-observed on a later poll must hash to the same id, which is why nothing
poll-time-dependent is an input).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime


def btc_occurrence_id(
    strategy_id: str,
    strategy_version: str,
    exchange: str,
    canonical_symbol: str,
    reference_trading_day: date,
    direction: str,
    sweep_time: datetime,
    mss_time: datetime,
) -> str:
    """Stable identity for one qualified (ENTRY_READY) BTC sweep-retest occurrence.
    reference_trading_day is the previous UTC calendar day the setup's reference box was
    built from (profile.previous_utc_day_window's own `start.date()`), not "today" --
    keeps the id stable regardless of which day the setup is later re-observed on.
    sweep_time/mss_time are market timestamps (SetupState.sweep_time/mss_time), never a
    wall-clock/evaluation timestamp."""
    key = "|".join([
        strategy_id,
        strategy_version,
        exchange,
        canonical_symbol,
        reference_trading_day.isoformat(),
        direction,
        sweep_time.isoformat(),
        mss_time.isoformat(),
    ])
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=12).hexdigest()
    return f"BTC-OCC-{digest}"
