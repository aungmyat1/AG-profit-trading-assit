"""TD-8: tests for the additive TopDownContext.composition_mode/dataset_identity
fields (src/mtf_context/topdown_contracts.py). Contract-only, no market data -- mirrors
tests/test_topdown_context_contracts.py's own idiom and fixtures. See
tests/test_topdown_composer_replay.py for the end-to-end proof that a real
HISTORICAL_AS_OF composition actually populates these fields correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mtf_context.topdown_contracts import (
    COMPOSITION_MODE_HISTORICAL_AS_OF,
    COMPOSITION_MODE_LIVE_CURRENT,
    DATA_QUALITY_MISSING,
    InvalidCompositionModeError,
    TopDownContext,
)

_T = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)


def _ctx(**overrides):
    base = dict(context_id="TDCTX-TOP-1", symbol="EURUSD", evaluation_time=_T, data_quality_status=DATA_QUALITY_MISSING)
    base.update(overrides)
    return TopDownContext(**base)


def test_default_composition_mode_is_live_current():
    """Backward compatibility: every pre-TD-8 TopDownContext(...) construction (the
    entire existing test_topdown_context_contracts.py suite) never passed
    composition_mode/dataset_identity -- must default to exactly what those
    constructions already implied."""
    ctx = _ctx()
    assert ctx.composition_mode == COMPOSITION_MODE_LIVE_CURRENT
    assert ctx.dataset_identity is None


def test_live_current_with_dataset_identity_is_rejected():
    with pytest.raises(InvalidCompositionModeError):
        _ctx(composition_mode=COMPOSITION_MODE_LIVE_CURRENT, dataset_identity="SOME-DATASET")


def test_historical_as_of_without_dataset_identity_is_rejected():
    with pytest.raises(InvalidCompositionModeError):
        _ctx(composition_mode=COMPOSITION_MODE_HISTORICAL_AS_OF, dataset_identity=None)


def test_historical_as_of_with_empty_string_dataset_identity_is_rejected():
    with pytest.raises(InvalidCompositionModeError):
        _ctx(composition_mode=COMPOSITION_MODE_HISTORICAL_AS_OF, dataset_identity="")


def test_historical_as_of_with_dataset_identity_is_accepted():
    ctx = _ctx(composition_mode=COMPOSITION_MODE_HISTORICAL_AS_OF, dataset_identity="SOME-DATASET")
    assert ctx.composition_mode == COMPOSITION_MODE_HISTORICAL_AS_OF
    assert ctx.dataset_identity == "SOME-DATASET"


def test_unknown_composition_mode_is_rejected():
    with pytest.raises(InvalidCompositionModeError):
        _ctx(composition_mode="SOMETHING_ELSE")
