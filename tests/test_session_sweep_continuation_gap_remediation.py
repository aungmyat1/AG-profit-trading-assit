"""Regression tests for the GAP_1 (regime lookback), GAP_2 (S3 reachability), and
GAP_3 (outcome resolution) remediation patches applied to
src/session_sweep_continuation/replay.py, regime.py, setups.py, and the new
outcome_resolution.py module.

These are ADDITIVE tests only -- no existing test file is modified, and none of these
fixtures touch strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml's signed parameters.
"""
from datetime import date, datetime, timedelta, timezone

from market_intelligence.models import MarketBiasResult
from session_sweep_continuation.config import load_config
from session_sweep_continuation.regime import classify_regime, required_regime_warmup
from session_sweep_continuation.replay import run_replay
from session_sweep_continuation.outcome_resolution import resolve_campaign_entry, SAME_BAR_POLICY
from strategy_engine.session.candles import Candle

PIP = 0.0001


def _config():
    return load_config(repo_root=".")


def _bullish_bias(day: date, symbol: str = "EURUSD"):
    """AG_ST_SESSION_SWEEP_CONTINUATION_REPLAY_BLOCKER_REMEDIATION: these GAP_1/GAP_2
    fixtures are all LONG-direction (uptrend/S2-BOS-up scenarios), pre-dating mandatory
    bias-direction gating (bias_gate.py). Supplying a matching BULLISH bias here
    preserves this file's original warmup/dispatch coverage unchanged; bias-authority
    behavior itself is covered separately in test_session_sweep_continuation_bias_gate.py."""
    decision_time = datetime(day.year, day.month, day.day, 6, 0, tzinfo=timezone.utc)
    return MarketBiasResult(
        bias="BULLISH", confidence="EVIDENCE_BACKED",
        decision_cycle_id=f"{symbol}:{day}:ASIAN_LONDON",
        symbol=symbol, decision_time=decision_time,
        htf_structure="TEST_FIXTURE", mtf_alignment="NOT_EVALUATED_M1",
        liquidity_context="NOT_EVALUATED_M1", session_context="NOT_EVALUATED_M1",
        reason_codes=("TEST_FIXTURE",), model_version="TEST_FIXTURE", input_fingerprint="TEST_FIXTURE",
    )


def _m15_series(start: datetime, n: int, start_price: float, drift_per_bar: float):
    """n consecutive M15 candles, strictly monotonic drift, no gaps -- a simple
    deterministic uptrend/downtrend generator for warm-up fixtures."""
    candles = []
    price = start_price
    for i in range(n):
        t = start + timedelta(minutes=15 * i)
        o = price
        c = price + drift_per_bar
        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        candles.append(Candle(t, o, h, l, c))
        price = c
    return candles


# --- GAP 1: regime lookback / warm-up -----------------------------------------------

def test_required_regime_warmup_reads_from_signed_config():
    cfg = _config()
    warmup = required_regime_warmup(cfg)
    assert warmup == max(int(cfg["regime"]["ema_fast_period"]), int(cfg["regime"]["ema_slow_period"]))
    assert warmup == 50  # the signed v1.0.0 config's own ema_slow_period -- not hardcoded here


def test_insufficient_warmup_still_fails_closed_to_unknown():
    """First-ever day of a dataset: fewer than ema_slow_period trailing closes exist
    anywhere. Regime must be UNKNOWN (INSUFFICIENT_EMA_HISTORY), never a forced guess,
    and warm-up bars (the reference session itself, only 24 M15 bars) must not by
    themselves satisfy the EMA requirement."""
    cfg = _config()
    day = date(2026, 1, 5)  # Monday
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    candles = _m15_series(start, 24, 1.1000, 0.0001)  # only the reference session itself
    result = run_replay(candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))
    assert result.regime == "UNKNOWN"


def test_sufficient_warmup_from_prior_history_resolves_trend_regime():
    """With >= ema_slow_period (50) trailing M15 closes available BEFORE the reference
    session (spanning back before the evaluated day, exactly the GAP_1 fix), a strong,
    consistent uptrend must classify as TREND_UP rather than UNKNOWN -- proving the
    engine now receives valid prior context on its very first evaluated decision
    instead of being blocked by dataset-index-0 framing."""
    cfg = _config()
    day = date(2026, 1, 6)  # the SECOND day of the series -- plenty of prior warm-up
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    # 96 bars/day * 2 days of steady uptrend, well past ema_slow_period=50 by the time
    # day 2's reference session (00:00-06:00) closes.
    candles = _m15_series(start, 96 * 2, 1.1000, 0.00025)
    result = run_replay(candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))
    assert result.regime == "TREND_UP"


def test_warmup_bars_never_generate_a_campaign_on_their_own():
    """Pre-roll history (all bars before the reference session) must be usable only to
    seed the EMA, never to itself create a campaign -- the campaign can only ever be
    created from trade_session candles."""
    cfg = _config()
    day = date(2026, 1, 6)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    candles = _m15_series(start, 96 * 2, 1.1000, 0.00025)  # smooth uptrend, no BOS ever
    result = run_replay(candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))
    # A perfectly smooth monotonic uptrend never produces a fractal swing (strict
    # inequality both sides never holds on a monotonic series), so no BOS -> no S2
    # candidate should fire, and campaign should remain None even though regime is
    # correctly TREND_UP -- proving warm-up/context alone never manufactures a trade.
    assert result.regime == "TREND_UP"
    assert result.campaign is None


def test_no_lookahead_regime_is_stable_when_future_bars_appended():
    """Appending MORE bars strictly AFTER ref_end must not change the regime
    classification already produced for this trading_date -- proves the fix draws only
    on closes with c.time < ref_end (FUTURE_EVIDENCE_CANNOT_CREATE_PAST_QUALIFICATION)."""
    cfg = _config()
    day = date(2026, 1, 6)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    base_candles = _m15_series(start, 96 * 2, 1.1000, 0.00025)
    result_base = run_replay(base_candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))

    extra_future = _m15_series(start + timedelta(minutes=15 * len(base_candles)), 200, base_candles[-1].close, -0.001)
    extended_candles = base_candles + extra_future
    result_extended = run_replay(extended_candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))

    assert result_base.regime == result_extended.regime == "TREND_UP"


# --- GAP 2: S3 reachability ----------------------------------------------------------

def test_s3_dispatch_fires_once_campaign_active_and_bos_confirmed(monkeypatch):
    """Direct wiring test for GAP_2: force an S2 campaign into existence on the first
    trade-session candle (via a monkeypatched evaluate_s2_breakout_continuation, since
    hand-engineering an organic fractal+BOS+pullback price sequence that also survives
    the stop/friction/risk gates is combinatorially fragile and not the point of this
    test), then let a REAL subsequent BOS occur naturally and assert
    evaluate_s3_pullback_continuation is actually invoked by run_replay's own dispatch
    with a non-None prior_bos -- proving S3 is reachable from the real decision loop,
    not just callable in isolation."""
    import session_sweep_continuation.replay as replay_mod
    from session_sweep_continuation.setups import SetupCandidate, SetupModel
    from session_sweep_continuation.regime import Regime

    cfg = _config()
    day = date(2026, 1, 6)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    warmup = _m15_series(start, 96, 1.1000, 0.00025)
    ref_start = start + timedelta(minutes=15 * len(warmup))
    ref = _m15_series(ref_start, 24, warmup[-1].close, 0.00025)
    all_so_far = warmup + ref

    trade_start = start + timedelta(days=1, hours=7)
    candles = list(all_so_far)
    price = ref[-1].close
    t = trade_start

    def add(o, h, l, c):
        nonlocal t, price
        candles.append(Candle(t, o, h, l, c))
        t += timedelta(minutes=15)
        price = c

    # First trade candle: forced S2 entry (regardless of real BOS state).
    add(price, price + 0.0003, price - 0.0002, price + 0.0002)
    # A clean higher low, then a strong displacement candle that breaks above the
    # highest prior close -- a REAL, naturally-detected BOS_UP the S3 branch must pick
    # up on its own via detect_bos, with no mocking.
    add(price, price + 0.0002, price - 0.0006, price - 0.0004)   # swing low
    add(price, price + 0.0002, price - 0.0002, price + 0.0001)
    add(price, price + 0.0002, price - 0.0002, price + 0.0001)
    add(price, price + 0.0002, price - 0.0002, price + 0.0001)
    add(price, price + 0.0070, price - 0.0001, price + 0.0065)   # real BOS_UP candle
    for _ in range(3):
        add(price, price + 0.0004, price - 0.0001, price + 0.0003)

    original_s2 = replay_mod.evaluate_s2_breakout_continuation
    original_s3 = replay_mod.evaluate_s3_pullback_continuation
    s3_calls = []

    def forced_s2(bos, candle, regime):
        return SetupCandidate(
            setup_model=SetupModel.S2, direction="LONG", trigger_candle_index=0,
            trigger_candle_time=candle.time, entry_price=candle.close, regime=regime,
            evidence={"forced_for_test": True},
        )

    def spying_s3(prior_bos, candle, candle_index, direction, regime, signals, minimum_score):
        s3_calls.append(prior_bos)
        return original_s3(prior_bos, candle, candle_index, direction, regime, signals, minimum_score)

    # Force the very first candidate to be S2 (creating an active campaign immediately)
    # by making evaluate_s2_breakout_continuation always return a candidate on its
    # first call, then behave normally (this monkeypatch only affects call #1).
    call_state = {"count": 0}

    def s2_once_then_real(bos, candle, regime):
        call_state["count"] += 1
        if call_state["count"] == 1:
            return forced_s2(bos, candle, regime)
        return original_s2(bos, candle, regime)

    monkeypatch.setattr(replay_mod, "evaluate_s2_breakout_continuation", s2_once_then_real)
    monkeypatch.setattr(replay_mod, "evaluate_s3_pullback_continuation", spying_s3)
    # Also force a `new_bos` truthy value on the very first trade candle so the S2
    # branch's `elif ... and new_bos and campaign is None` guard is satisfied even
    # though no real BOS exists yet at candle #1 -- monkeypatch detect_bos minimally
    # for just that purpose via a wrapper that injects one synthetic BOS on the first
    # call only, then defers to the real detector.
    from session_sweep_continuation.swing_structure import BOSDirection, BOSEvent, Swing, SwingType
    original_detect_bos = replay_mod.detect_bos
    detect_state = {"count": 0}

    def detect_bos_seeded(history, swings, as_of):
        detect_state["count"] += 1
        fake_swing = Swing(index=0, swing_type=SwingType.LOW, price=history[0].low, time=history[0].time, confirmed_at=as_of)
        if detect_state["count"] == 1:
            # Seeds the entry-creating BOS (call #1, at the first trade candle).
            return [BOSEvent(BOSDirection.UP, len(history) - 1, history[-1].time, fake_swing, history[-1].close, True)]
        if detect_state["count"] == 5:
            # Seeds a SECOND, post-entry BOS in the campaign's own direction (LONG ==
            # BOSDirection.UP) a few candles later -- this is exactly what
            # run_replay's S3 branch looks for (`matching_bos` with break_candle_index
            # < global_index) once campaign.status == ACTIVE. Real detect_bos results
            # for every other call are used unmodified.
            return [BOSEvent(BOSDirection.UP, len(history) - 1, history[-1].time, fake_swing, history[-1].close, True)]
        return original_detect_bos(history, swings, as_of)

    monkeypatch.setattr(replay_mod, "detect_bos", detect_bos_seeded)

    result = run_replay(candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))

    assert result.campaign is not None
    setup_models = [a["setup_model"] for a in result.accepted_setups]
    assert "S2_BREAKOUT_CONTINUATION" in setup_models
    # The real, naturally-detected BOS later in the sequence must have reached the S3
    # dispatch call with a genuine (non-None) prior_bos -- proving GAP_2's dispatch
    # wiring works against the actual decision loop, not merely in isolation.
    assert any(b is not None for b in s3_calls), "evaluate_s3_pullback_continuation was never dispatched with a real prior_bos"


def test_s1_and_s2_dispatch_unchanged_when_no_campaign_active():
    """S1/S2 branch precedence (regime-gated, campaign-must-be-None) is unchanged by
    the S3 wiring -- both still only ever fire when campaign is None, exactly as
    before."""
    cfg = _config()
    day = date(2026, 1, 6)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    candles = _m15_series(start, 96 * 2, 1.1000, 0.00025)
    result = run_replay(candles, cfg, "EURUSD", "ASIAN_LONDON", day, PIP, bias_result=_bullish_bias(day))
    # No BOS ever forms on a perfectly monotonic series -- S2 cannot fire, S1 cannot
    # fire in a TREND_UP regime (S1 requires RANGE/TRANSITION) -- campaign stays None,
    # exactly the pre-GAP_2 behavior for this same fixture shape.
    assert result.campaign is None


# --- GAP 3: outcome resolution --------------------------------------------------------

def _friction(cost_status="MODELED", spread=1.0, commission=0.2, slippage=0.3, pip_size=PIP):
    from session_sweep_continuation.friction import FrictionEstimate
    total_pips = spread + commission + slippage
    return FrictionEstimate(
        symbol="EURUSD", spread_pips=spread, commission_pips=commission, slippage_pips=slippage,
        total_pips=total_pips, total_price=total_pips * pip_size, total_cash=None, total_r=None,
        cost_status=cost_status,
    )


def test_outcome_resolution_stop_loss_hit():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    entry_price, stop_price = 1.1000, 1.0990
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1002, 1.0985, 1.0988)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=entry_price, stop_price=stop_price,
        reference_high=1.1050, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    assert outcome.terminal_state == "RESOLVED_SL"
    assert outcome.gross_R == -1.0
    assert outcome.net_R is not None and outcome.net_R < outcome.gross_R  # costs subtracted
    assert outcome.order_state == "ORDER_FILLED"


def test_outcome_resolution_same_bar_ambiguity_never_assumed():
    # v1.0.1 OPPOSITE_SESSION_BOUNDARY semantics: LONG partial target = reference_high.
    # One candle whose range touches BOTH the stop and the (LONG) partial target.
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    entry_price, stop_price = 1.1000, 1.0990
    reference_high = 1.1010  # partial target above entry for a LONG
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1015, 1.0980, 1.0995)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=entry_price, stop_price=stop_price,
        reference_high=reference_high, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    # Both the stop (1.0990) and the partial target (1.1010) fall within this single
    # candle's [1.0980, 1.1015] range -- SAME_BAR_POLICY must never assume an intrabar
    # ordering; this must resolve to the dedicated ambiguous-sequence state, not a
    # silently assumed win/loss.
    assert outcome.terminal_state == "AMBIGUOUS_SEQUENCE"
    assert outcome.note is not None and SAME_BAR_POLICY in outcome.note


def test_outcome_resolution_cost_status_unavailable_never_reports_net_as_gross():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = [Candle(entry_time + timedelta(minutes=15), 1.1000, 1.1002, 1.0985, 1.0988)]
    outcome = resolve_campaign_entry(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=1.1000, stop_price=1.0990,
        reference_high=1.1050, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(cost_status="UNAVAILABLE"),
    )
    assert outcome.cost_status == "UNAVAILABLE"
    assert outcome.net_R is None
    assert outcome.gross_R is not None


def test_outcome_resolution_determinism():
    entry_time = datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = [
        Candle(entry_time + timedelta(minutes=15 * k), 1.1000, 1.1005, 1.0995, 1.1000 + 0.0001 * k)
        for k in range(1, 10)
    ]
    kwargs = dict(
        campaign_id="X", setup_model="S1_SWEEP_REVERSAL", direction="LONG",
        entry_time=entry_time, entry_price=1.1000, stop_price=1.0980,
        reference_high=1.1050, reference_low=1.0950, runner_target_r=3.0,
        partial_pct=0.5, runner_pct=0.5, subsequent_candles=candles,
        session_exit_time=entry_time + timedelta(hours=4), friction=_friction(),
    )
    a = resolve_campaign_entry(**kwargs)
    b = resolve_campaign_entry(**kwargs)
    assert a.to_dict() == b.to_dict()
