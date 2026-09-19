"""SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1, item 5 (EMA invariant).

regime.ema_fast_period/ema_slow_period (the regime classifier's own EMA
inputs) and ema.fast_period/ema_slow_period (the separate `ema` block other
signals read) are two independently-editable places in
strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml that currently hold the same
values (20/50) but have no structural link to each other. This test fails
closed the moment a future edit changes one block without the other --
before this test existed, that divergence was silently possible; it does not
assert anything about what the values *should* be, and it changes nothing
about them.
"""
from __future__ import annotations

from session_sweep_continuation.config import load_config


def _config():
    return load_config(repo_root=".")


def test_regime_and_signal_ema_periods_stay_in_sync() -> None:
    config = _config()
    regime = config["regime"]
    ema = config["ema"]

    assert regime["ema_fast_period"] == ema["fast_period"], (
        "regime.ema_fast_period and ema.fast_period diverged -- "
        f"{regime['ema_fast_period']!r} != {ema['fast_period']!r}. "
        "If this divergence is intentional, it needs an explicit reviewed "
        "decision, not a silent config edit."
    )
    assert regime["ema_slow_period"] == ema["slow_period"], (
        "regime.ema_slow_period and ema.slow_period diverged -- "
        f"{regime['ema_slow_period']!r} != {ema['slow_period']!r}. "
        "If this divergence is intentional, it needs an explicit reviewed "
        "decision, not a silent config edit."
    )
