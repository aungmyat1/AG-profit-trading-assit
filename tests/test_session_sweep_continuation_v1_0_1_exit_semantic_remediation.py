"""Normative regression tests for the SSC V1.0.1 EXIT CONTRACT SEMANTIC REMEDIATION
(PARTIAL_TARGET_DIRECTION_INVERSION, OPTION_A, owner-adjudicated on repository
semantic/provenance evidence, not economic performance).

Canonical OPPOSITE_SESSION_BOUNDARY mapping as of v1.0.1:
    LONG  -> partial target = reference_high
    SHORT -> partial target = reference_low

These are ADDITIVE tests only -- no existing fixture/assertion in another test file is
weakened; the one pre-existing test whose comment/scenario characterized the v1.0.0
inverted mapping as expected behavior (test_outcome_resolution_same_bar_ambiguity_never_assumed
in test_session_sweep_continuation_gap_remediation.py) was updated in place to exercise
the corrected mapping, not deleted.
"""
from datetime import date, datetime, timedelta, timezone

from session_sweep_continuation.outcome_resolution import (
    PARTIAL_TARGET_INTERPRETATION,
    resolve_campaign_entry,
)
from strategy_engine.session.candles import Candle
from strategy_engine.models import RiskConfig, StrategyConfig, TargetLeg, TradeSignal

PIP = 0.0001


def _friction(cost_status="MODELED", spread=1.0, commission=0.2, slippage=0.3, pip_size=PIP):
    from session_sweep_continuation.friction import FrictionEstimate
    total_pips = spread + commission + slippage
    return FrictionEstimate(
        symbol="EURUSD", spread_pips=spread, commission_pips=commission, slippage_pips=slippage,
        total_pips=total_pips, total_price=total_pips * pip_size, total_cash=None, total_r=None,
        cost_status=cost_status,
    )


def test_wp6_long_mapping_is_reference_high():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1002, 1.0995, 1.0998)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=1.1000, stop_price=1.0980,
        reference_high=1.1050, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.partial_target_price == 1.1050
    assert outcome.partial_target_interpretation == PARTIAL_TARGET_INTERPRETATION


def test_wp6_short_mapping_is_reference_low():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1005, 1.0998, 1.1002)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="SHORT",
        entry_time=entry_time, entry_price=1.1000, stop_price=1.1020,
        reference_high=1.1050, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.partial_target_price == 1.0950


def test_wp6_long_lifecycle_entry_partial_then_runner_target():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    entry_price, stop_price = 1.1000, 1.0980
    reference_high, reference_low = 1.1020, 1.0950
    risk = entry_price - stop_price  # 0.0020
    candles = [
        # Phase 1: touches partial target (reference_high=1.1020), not the stop.
        Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1025, 1.0995, 1.1010),
        # Phase 2 (BE armed): runner target = entry + 3R = 1.1060 hit, BE (1.1000) not hit.
        Candle(entry_time + timedelta(minutes=30), 1.1010, 1.1065, 1.1005, 1.1050),
    ]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=entry_price, stop_price=stop_price,
        reference_high=reference_high, reference_low=reference_low, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.terminal_state == "RESOLVED_PARTIAL_RUNNER_TARGET"
    assert outcome.partial_target_price == reference_high
    events = [e["event"] for e in outcome.event_sequence]
    assert events == ["PARTIAL_TARGET", "RUNNER_TARGET_HIT"]
    expected_gross_R = 0.5 * ((reference_high - entry_price) / risk) + 0.5 * 3.0
    assert outcome.gross_R == expected_gross_R


def test_wp6_short_lifecycle_entry_partial_then_breakeven():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    entry_price, stop_price = 1.1000, 1.1020
    reference_high, reference_low = 1.1050, 1.0980
    candles = [
        # Phase 1: touches partial target (reference_low=1.0980), not the stop.
        Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1005, 1.0975, 1.0990),
        # Phase 2 (BE armed): BE (1.1000) hit, runner target (1.0940) not hit.
        Candle(entry_time + timedelta(minutes=30), 1.0990, 1.1005, 1.0970, 1.0995),
    ]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="SHORT",
        entry_time=entry_time, entry_price=entry_price, stop_price=stop_price,
        reference_high=reference_high, reference_low=reference_low, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.terminal_state == "RESOLVED_PARTIAL_BE"
    assert outcome.partial_target_price == reference_low
    events = [e["event"] for e in outcome.event_sequence]
    assert events == ["PARTIAL_TARGET", "RUNNER_BE_STOP"]


def test_wp6_invalid_geometry_fails_closed_not_reversed():
    """A partial target already behind entry (on the wrong side) must still fail closed
    to 'no valid forward target' -- the direction correction must not weaken this
    pre-existing invariant."""
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1002, 1.0985, 1.0988)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=1.1000, stop_price=1.0990,
        # reference_high below entry_price: invalid forward target for a LONG.
        reference_high=1.0995, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.partial_target_price is None
    assert outcome.terminal_state in ("RESOLVED_SL", "RESOLVED_SESSION_EXIT", "UNRESOLVED_NO_DATA")


def test_wp6_cross_module_parity_with_execution_validator():
    """outcome_resolution.py's LONG/SHORT partial-target mapping must match
    execution/validator.py's leg1_take_profit()/_leg1_target() OPPOSITE_SESSION_BOUNDARY
    mapping for identical box_high/box_low/direction inputs."""
    from execution.validator import leg1_take_profit

    box_high, box_low = 1.1050, 1.0950
    strategy = StrategyConfig(
        strategy_id="TEST", strategy_name="TEST", strategy_family="TEST", version="1.0.0",
        status="ACTIVE", instruments=["EURUSD"], timeframe="M15", magic_number=1,
        session_pairs=[], risk=RiskConfig(risk_mode="FIXED", stop_loss_mode="FIXED",
                                          stop_loss_range_pct=0.0, max_spread_allowed_pips=0.0,
                                          slippage_limit_points=0),
        entry_order_type="MARKET", total_target_r=3.0,
        legs=[TargetLeg(leg_id=1, volume_pct=0.5, target_type="OPPOSITE_SESSION_BOUNDARY")],
        max_range_pips_eurusd=25.0, time_invalidation="NONE", structural_invalidation="NONE",
        source_path="TEST",
    )
    for direction, expected in (("LONG", box_high), ("SHORT", box_low)):
        signal = TradeSignal(
            signal_id="X", strategy_id="TEST", strategy_version="1.0.0", symbol="EURUSD",
            pair_id="ASIAN_LONDON", reference_session="ASIAN", session_date=date(2026, 1, 6),
            box_high=box_high, box_low=box_low, box_mid=(box_high + box_low) / 2,
            regime="TREND", setup="S1", status="SIGNAL", reason_code="OK", direction=direction,
        )
        validator_target = leg1_take_profit(signal, strategy)
        assert validator_target == expected

        # Same-direction SSC resolver mapping under identical box/reference values.
        entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
        candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1002, 1.0995, 1.0998)]
        is_long = direction == "LONG"
        outcome = resolve_campaign_entry(
            campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction=direction,
            entry_time=entry_time,
            entry_price=1.1000, stop_price=1.0980 if is_long else 1.1020,
            reference_high=box_high, reference_low=box_low, runner_target_r=3.0,
            partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
            session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
        )
        assert outcome.partial_target_price == validator_target == expected
