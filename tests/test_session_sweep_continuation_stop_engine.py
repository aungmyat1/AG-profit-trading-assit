from session_sweep_continuation.friction import FrictionEstimate
from session_sweep_continuation.stop_engine import AnchorResult, compute_stop


def _friction(total_price, status="MODELED"):
    return FrictionEstimate(
        symbol="EURUSD", spread_pips=1.0, commission_pips=0.2, slippage_pips=0.3,
        total_pips=1.5, total_price=total_price, total_cash=15.0, total_r=None, cost_status=status,
    )


def test_stop_rejected_when_no_anchor_available():
    anchor = AnchorResult(None, "NONE")
    result = compute_stop("LONG", 1.1000, anchor, atr_m15=0.0010, stop_buffer_multiplier=0.20,
                           friction=_friction(0.00015), minimum_stop_multiple=3.0)
    assert result.accepted is False
    assert result.reason == "NO_STRUCTURAL_ANCHOR_AVAILABLE"


def test_stop_rejected_when_atr_unavailable():
    anchor = AnchorResult(1.0950, "S1_SWEEP_EXTREME")
    result = compute_stop("LONG", 1.1000, anchor, atr_m15=None, stop_buffer_multiplier=0.20,
                           friction=_friction(0.00015), minimum_stop_multiple=3.0)
    assert result.accepted is False
    assert result.reason == "ATR_UNAVAILABLE"


def test_stop_includes_atr_buffer_in_structural_distance():
    anchor = AnchorResult(1.0950, "S1_SWEEP_EXTREME")
    atr = 0.0010
    result = compute_stop("LONG", 1.1000, anchor, atr_m15=atr, stop_buffer_multiplier=0.20,
                           friction=_friction(0.00015), minimum_stop_multiple=3.0)
    assert result.accepted is True
    expected_structural = abs(1.1000 - 1.0950) + 0.20 * atr
    assert abs(result.structural_stop_distance - expected_structural) < 1e-12
    assert result.final_stop_distance == result.structural_stop_distance
    assert abs(result.stop_price - (1.1000 - result.final_stop_distance)) < 1e-12


def test_stop_rejected_when_below_friction_floor_never_widened():
    # anchor extremely close to entry -> tiny structural distance, well below 3x friction
    anchor = AnchorResult(1.09999, "S1_SWEEP_EXTREME")
    result = compute_stop("LONG", 1.1000, anchor, atr_m15=0.0000001, stop_buffer_multiplier=0.20,
                           friction=_friction(0.0010), minimum_stop_multiple=3.0)
    assert result.accepted is False
    assert result.reason == "STOP_BELOW_FRICTION_FLOOR"
    # must not have silently produced a final_stop_distance by widening to the floor
    assert result.final_stop_distance is None


def test_stop_rejected_when_friction_unavailable_fails_closed():
    anchor = AnchorResult(1.0950, "S1_SWEEP_EXTREME")
    unavailable = FrictionEstimate(
        symbol="EURUSD", spread_pips=None, commission_pips=None, slippage_pips=None,
        total_pips=None, total_price=None, total_cash=None, total_r=None, cost_status="UNAVAILABLE",
    )
    result = compute_stop("LONG", 1.1000, anchor, atr_m15=0.0010, stop_buffer_multiplier=0.20,
                           friction=unavailable, minimum_stop_multiple=3.0)
    assert result.accepted is False
    assert result.reason == "FRICTION_UNAVAILABLE"


def test_short_direction_stop_price_above_entry():
    anchor = AnchorResult(1.1050, "S1_SWEEP_EXTREME")
    result = compute_stop("SHORT", 1.1000, anchor, atr_m15=0.0010, stop_buffer_multiplier=0.20,
                           friction=_friction(0.00015), minimum_stop_multiple=3.0)
    assert result.accepted is True
    assert result.stop_price > 1.1000
