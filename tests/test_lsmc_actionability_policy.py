"""AG_V1_HOST_HARDENING_R1 T2 -- LSMC_ACTIONABILITY_POLICY_V1 (D1/D2/D3/D4/D7).

Covers the four owner-named fixtures (the 07:01 case, the XAUUSD late case, the ETH low-R case,
the GBPUSD dedup case) plus direct unit coverage of each rule in isolation.
"""
from __future__ import annotations

import datetime as dt

import pytest

from lsmc_actionability_policy import (
    ACTIONABLE,
    INFO_ONLY,
    MISSED_NOT_ACTIONABLE,
    PENDING_BAR_CLOSE,
    REASON_BAR_NOT_CLOSED,
    REASON_FRESH,
    REASON_LOW_R,
    REASON_STALE_FRESHNESS,
    LsmcCandidate,
    MarketQuote,
    TriggerContext,
    bars_since_close,
    classify,
    correlated_exposure,
    detect_downtime,
    missed_digest,
    remaining_r,
    tag_and_rank_correlated,
    usd_direction,
)

UTC = dt.timezone.utc


def _m5_trigger(close_utc: dt.datetime, closed: bool = True) -> TriggerContext:
    return TriggerContext(trigger_timeframe="M5", trigger_timeframe_minutes=5,
                          trigger_close_utc=close_utc, signal_bar_closed=closed)


def _candidate(symbol, direction, trigger, entry, stop, target, friction=None, strategy_id="ST_LARGE_SMC_V1",
              strategy_version="1.1.0") -> LsmcCandidate:
    return LsmcCandidate(symbol=symbol, direction=direction, strategy_id=strategy_id,
                         strategy_version=strategy_version, trigger=trigger, entry=entry, stop=stop,
                         target=target, friction=friction)


# --------------------------------------------------------------------- D1: the 07:01 case

def test_0701_case_fresh_at_exactly_2_bars_stale_one_minute_later():
    close = dt.datetime(2026, 10, 7, 6, 50, tzinfo=UTC)
    cand = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1200)
    quote = MarketQuote(bid=1.1000, ask=1.1002)

    at_0700 = classify(cand, now=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), send_quote=quote)
    assert at_0700.bars_since_trigger_close == pytest.approx(2.0)
    assert at_0700.classification == ACTIONABLE
    assert REASON_FRESH in at_0700.reason_codes and REASON_STALE_FRESHNESS not in at_0700.reason_codes

    at_0701 = classify(cand, now=dt.datetime(2026, 10, 7, 7, 1, tzinfo=UTC), send_quote=quote)
    assert at_0701.bars_since_trigger_close == pytest.approx(2.2)
    assert at_0701.classification == INFO_ONLY
    assert REASON_STALE_FRESHNESS in at_0701.reason_codes


def test_bars_since_close_never_negative_on_clock_skew():
    close = dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC)
    assert bars_since_close(close, close - dt.timedelta(minutes=5), tf_minutes=5) == 0.0


# --------------------------------------------------------------------- D1: the XAUUSD late case

def test_xauusd_late_case_six_bars_past_trigger_is_info_only():
    close = dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=30)  # 6 M5 bars late
    cand = _candidate("XAUUSD", "SHORT", _m5_trigger(close), entry=2650.0, stop=2660.0, target=2600.0)
    quote = MarketQuote(bid=2649.0, ask=2649.5)

    decision = classify(cand, now=now, send_quote=quote)
    assert decision.bars_since_trigger_close == pytest.approx(6.0)
    assert decision.classification == INFO_ONLY
    assert decision.reason_codes == (REASON_STALE_FRESHNESS,)  # R was fine; only freshness failed
    assert decision.send_time_bid == 2649.0 and decision.send_time_ask == 2649.5  # D2 persists both regardless


# --------------------------------------------------------------------- D2: the ETH low-R case

def test_eth_low_r_case_fresh_but_remaining_r_below_1_5_is_info_only():
    close = dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)  # 1 bar -- clearly fresh
    # entry 4000, stop 3940 (risk 60); target only 4072 -> ~1.2R from the ask reference on a LONG
    cand = _candidate("ETHUSD", "LONG", _m5_trigger(close), entry=4000.0, stop=3940.0, target=4072.0)
    quote = MarketQuote(bid=4000.0, ask=4001.0)

    decision = classify(cand, now=now, send_quote=quote)
    assert decision.bars_since_trigger_close == pytest.approx(1.0)
    r = remaining_r(4000.0, 3940.0, 4072.0, "LONG", reference_price=4000.0)  # LONG uses bid
    assert r == pytest.approx(1.2)
    assert decision.remaining_r == pytest.approx(1.2)
    assert decision.classification == INFO_ONLY
    assert decision.reason_codes == (REASON_LOW_R,)  # freshness passed; only R failed
    assert decision.send_time_bid == 4000.0 and decision.send_time_ask == 4001.0


def test_remaining_r_fails_closed_on_zero_risk():
    assert remaining_r(entry=1.1, stop=1.1, target=1.2, direction="LONG", reference_price=1.1) is None


# --------------------------------------------------------------------- D4: unclosed signal bar

def test_unclosed_signal_bar_is_pending_not_stale():
    close = dt.datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    cand = _candidate("GBPUSD", "LONG", _m5_trigger(close, closed=False), entry=1.3, stop=1.295, target=1.32)
    quote = MarketQuote(bid=1.3001, ask=1.3003)
    # even evaluated far later, an unclosed bar is PENDING_BAR_CLOSE, never STALE/INFO_ONLY
    decision = classify(cand, now=close + dt.timedelta(hours=1), send_quote=quote)
    assert decision.classification == PENDING_BAR_CLOSE
    assert decision.reason_codes == (REASON_BAR_NOT_CLOSED,)
    assert decision.bars_since_trigger_close is None and decision.remaining_r is None
    assert decision.send_time_bid == 1.3001 and decision.send_time_ask == 1.3003  # quote still captured


# --------------------------------------------------------------------- D3: no catch-up READYs

def test_no_downtime_on_first_run_ever():
    assert detect_downtime(last_run_at=None, now=dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC),
                           max_gap=dt.timedelta(minutes=15)) is False


def test_downtime_detected_beyond_configured_gap():
    last = dt.datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
    assert detect_downtime(last, last + dt.timedelta(minutes=10), dt.timedelta(minutes=15)) is False
    assert detect_downtime(last, last + dt.timedelta(minutes=16), dt.timedelta(minutes=15)) is True


def test_missed_digest_combines_every_withheld_candidate_into_one_message():
    close = dt.datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
    missed = [
        _candidate("EURUSD", "LONG", _m5_trigger(close), 1.1, 1.095, 1.12),
        _candidate("GBPUSD", "LONG", _m5_trigger(close), 1.3, 1.295, 1.32),
    ]
    digest = missed_digest(missed, downtime_start=close, downtime_end=close + dt.timedelta(minutes=40))
    assert digest.kind == MISSED_NOT_ACTIONABLE + "_DIGEST"
    assert digest.label == "MISSED - NOT ACTIONABLE"
    assert digest.count == 2 and digest.symbols == ("EURUSD", "GBPUSD")
    assert digest.reason_code == "NO_CATCH_UP_READYS_PER_D3"


# --------------------------------------------------------------------- D7: the GBPUSD dedup case

def test_usd_direction_mapping():
    assert usd_direction("EURUSD", "LONG") == "USD_SHORT"
    assert usd_direction("EURUSD", "SHORT") == "USD_LONG"
    assert usd_direction("USDJPY", "LONG") == "USD_LONG"
    assert usd_direction("USDJPY", "SHORT") == "USD_SHORT"
    assert usd_direction("BTCUSD", "LONG") == "USD_SHORT"
    assert usd_direction("EURGBP", "LONG") is None  # no USD leg


def test_gbpusd_dedup_case_tags_correlated_and_ranks_by_friction_then_r():
    close = dt.datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    gbp = _candidate("GBPUSD", "LONG", _m5_trigger(close), entry=1.3000, stop=1.2950, target=1.3150, friction=0.05)
    eur = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1150, friction=0.10)
    quote = MarketQuote(bid=1.0, ask=1.0)  # placeholder; classify() below uses per-symbol quotes

    gbp_dec = classify(gbp, now=now, send_quote=MarketQuote(bid=1.3000, ask=1.3002))
    eur_dec = classify(eur, now=now, send_quote=MarketQuote(bid=1.1000, ask=1.1002))
    assert gbp_dec.classification == ACTIONABLE and eur_dec.classification == ACTIONABLE

    ranked = tag_and_rank_correlated([(gbp, gbp_dec), (eur, eur_dec)])
    (ranked_gbp_cand, ranked_gbp_dec), (ranked_eur_cand, ranked_eur_dec) = ranked

    assert ranked_gbp_dec.correlated and ranked_eur_dec.correlated
    assert ranked_gbp_dec.correlation_group == "USD_SHORT" == ranked_eur_dec.correlation_group
    assert ranked_gbp_dec.rank_in_group == 1   # lower friction (0.05 < 0.10) ranks first
    assert ranked_eur_dec.rank_in_group == 2
    # classification itself is never changed by D7 -- both remain independently ACTIONABLE
    assert ranked_gbp_dec.classification == ACTIONABLE and ranked_eur_dec.classification == ACTIONABLE


def test_correlation_tie_break_is_remaining_r_descending_when_friction_equal():
    close = dt.datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    # equal friction; GBPUSD has the larger remaining R and should rank first
    gbp = _candidate("GBPUSD", "LONG", _m5_trigger(close), entry=1.3000, stop=1.2950, target=1.3200, friction=0.08)
    eur = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1120, friction=0.08)
    gbp_dec = classify(gbp, now=now, send_quote=MarketQuote(bid=1.3000, ask=1.3002))
    eur_dec = classify(eur, now=now, send_quote=MarketQuote(bid=1.1000, ask=1.1002))
    assert gbp_dec.remaining_r > eur_dec.remaining_r

    ranked = tag_and_rank_correlated([(eur, eur_dec), (gbp, gbp_dec)])   # input order deliberately reversed
    symbols_in_rank_order = [cand.symbol for cand, dec in sorted(ranked, key=lambda pair: pair[1].rank_in_group)]
    assert symbols_in_rank_order == ["GBPUSD", "EURUSD"]


def test_no_correlation_tag_when_group_has_only_one_member():
    close = dt.datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    gbp = _candidate("GBPUSD", "LONG", _m5_trigger(close), entry=1.3000, stop=1.2950, target=1.3150, friction=0.05)
    usdjpy = _candidate("USDJPY", "LONG", _m5_trigger(close), entry=150.00, stop=149.50, target=151.50, friction=0.05)
    gbp_dec = classify(gbp, now=now, send_quote=MarketQuote(bid=1.3000, ask=1.3002))
    jpy_dec = classify(usdjpy, now=now, send_quote=MarketQuote(bid=150.00, ask=150.02))

    ranked = tag_and_rank_correlated([(gbp, gbp_dec), (usdjpy, jpy_dec)])  # USD_SHORT vs USD_LONG -- no overlap
    assert all(not dec.correlated and dec.rank_in_group is None for _, dec in ranked)


def test_r_at_trigger_is_persisted_alongside_r_at_send_and_never_gates():
    """Signed doc D2: 'Persist: reference_price, send_price, R_AT_TRIGGER, R_AT_SEND'.
    R_AT_TRIGGER (measured from the entry price itself) is audit-only and never changes the
    classification -- only R_AT_SEND (the live-quote `remaining_r`) gates ACTIONABLE/INFO_ONLY."""
    close = dt.datetime(2026, 10, 7, 11, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    # Designed as a clean 2R setup at entry, but the live ask has drifted so R_AT_SEND < 1.5.
    cand = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1100)
    decision = classify(cand, now=now, send_quote=MarketQuote(bid=1.1040, ask=1.1042))
    assert decision.remaining_r_at_trigger == pytest.approx(2.0)    # from entry: (1.11-1.10)/0.005
    assert decision.remaining_r < 1.5                                # from the live bid: much less room left
    assert decision.classification == INFO_ONLY and REASON_LOW_R in decision.reason_codes


def test_xauusd_gets_its_own_sensitive_correlation_bucket():
    """Signed doc D7 names 'USD_SHORT_SENSITIVE for XAUUSD' explicitly -- gold must never be
    pooled into the same correlation cluster as a plain USD-quoted FX pair."""
    assert correlated_exposure("XAUUSD", "LONG") == "USD_SHORT_SENSITIVE"
    assert correlated_exposure("XAUUSD", "SHORT") == "USD_LONG_SENSITIVE"
    assert correlated_exposure("EURUSD", "LONG") == "USD_SHORT"       # unaffected, no _SENSITIVE suffix
    assert usd_direction("XAUUSD", "LONG") == "USD_SHORT"             # the underlying direction is unchanged


def test_xauusd_and_eurusd_long_are_not_pooled_into_the_same_cluster():
    close = dt.datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    xau = _candidate("XAUUSD", "LONG", _m5_trigger(close), entry=2650.0, stop=2640.0, target=2690.0, friction=0.05)
    eur = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1150, friction=0.05)
    xau_dec = classify(xau, now=now, send_quote=MarketQuote(bid=2650.0, ask=2650.5))
    eur_dec = classify(eur, now=now, send_quote=MarketQuote(bid=1.1000, ask=1.1002))
    assert xau_dec.classification == ACTIONABLE and eur_dec.classification == ACTIONABLE

    ranked = tag_and_rank_correlated([(xau, xau_dec), (eur, eur_dec)])
    (_, ranked_xau), (_, ranked_eur) = ranked
    assert not ranked_xau.correlated and not ranked_eur.correlated   # each alone in its own bucket
    assert ranked_xau.correlation_group is None and ranked_eur.correlation_group is None


def test_correlation_cluster_id_is_deterministic_and_matches_exposure_and_symbols():
    close = dt.datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
    now = close + dt.timedelta(minutes=5)
    gbp = _candidate("GBPUSD", "LONG", _m5_trigger(close), entry=1.3000, stop=1.2950, target=1.3150, friction=0.05)
    eur = _candidate("EURUSD", "LONG", _m5_trigger(close), entry=1.1000, stop=1.0950, target=1.1150, friction=0.10)
    gbp_dec = classify(gbp, now=now, send_quote=MarketQuote(bid=1.3000, ask=1.3002))
    eur_dec = classify(eur, now=now, send_quote=MarketQuote(bid=1.1000, ask=1.1002))
    ranked = tag_and_rank_correlated([(gbp, gbp_dec), (eur, eur_dec)])
    cluster_ids = {dec.correlation_cluster_id for _, dec in ranked}
    assert cluster_ids == {"USD_SHORT:EURUSD+GBPUSD"}


def test_info_only_and_pending_candidates_are_never_tagged_correlated():
    close = dt.datetime(2026, 10, 7, 10, 0, tzinfo=UTC)
    stale_now = close + dt.timedelta(minutes=30)
    gbp_stale = _candidate("GBPUSD", "LONG", _m5_trigger(close), entry=1.3000, stop=1.2950, target=1.3150)
    eur_pending = _candidate("EURUSD", "LONG", _m5_trigger(close, closed=False), entry=1.1000, stop=1.0950,
                             target=1.1150)
    gbp_dec = classify(gbp_stale, now=stale_now, send_quote=MarketQuote(bid=1.3000, ask=1.3002))
    eur_dec = classify(eur_pending, now=stale_now, send_quote=MarketQuote(bid=1.1000, ask=1.1002))
    assert gbp_dec.classification == INFO_ONLY and eur_dec.classification == PENDING_BAR_CLOSE

    ranked = tag_and_rank_correlated([(gbp_stale, gbp_dec), (eur_pending, eur_dec)])
    assert all(not dec.correlated for _, dec in ranked)
