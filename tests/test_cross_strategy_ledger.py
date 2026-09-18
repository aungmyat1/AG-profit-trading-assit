"""AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2, WP12-C: proves SSC and
ST_LARGE_SMC_V1 proposals coexist correctly in the same ProposalLedger -- different
strategy IDs never collide, repeated identical decisions from either strategy are
idempotent, restart never duplicates either, and neither strategy can overwrite the
other's record."""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, timezone

from market_intelligence.models import MarketBiasResult
from proposal_envelope.adapters.large_smc_research_adapter import to_canonical_proposal as lsmc_to_canonical
from proposal_envelope.adapters.ssc_adapter import to_canonical_proposal as ssc_to_canonical
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_READY
from proposal_envelope.strategy_authority import resolve_strategy_authority
from large_smc_research.decision import LargeSMCResearchDecision
from session_sweep_continuation import STRATEGY_ID as SSC_STRATEGY_ID, STRATEGY_VERSION as SSC_STRATEGY_VERSION
from session_sweep_continuation.config import load_config
from session_sweep_continuation.replay import run_replay
from strategy_contract.market_snapshot import from_real_candle
from strategy_engine.session.candles import Candle

PIP = 0.0001
DAY = date(2026, 9, 10)

LSMC_STRATEGY_ID = "ST_LARGE_SMC_V1"
LSMC_STRATEGY_VERSION = "1.0.7"


def _bullish_bias(symbol="EURUSD"):
    decision_time = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    return MarketBiasResult(
        bias="BULLISH", confidence="EVIDENCE_BACKED",
        decision_cycle_id=f"{symbol}:{decision_time.date()}:ASIAN_LONDON",
        symbol=symbol, decision_time=decision_time,
        htf_structure="TEST_FIXTURE", mtf_alignment="NOT_EVALUATED_M1",
        liquidity_context="NOT_EVALUATED_M1", session_context="NOT_EVALUATED_M1",
        reason_codes=("TEST_FIXTURE",), model_version="TEST_FIXTURE", input_fingerprint="TEST_FIXTURE",
    )


def _synthetic_candles():
    candles = []
    t0 = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    price = 1.1000
    for i in range(24):
        t = t0 + timedelta(minutes=15 * i)
        o = price
        h = price + 0.0004
        l = price - 0.0004
        c = price + (0.0001 if i % 2 == 0 else -0.0001)
        candles.append(Candle(t, o, h, l, c))
        price = c
    ref_low = min(c.low for c in candles)
    t_trade0 = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)
    for i in range(16):
        t = t_trade0 + timedelta(minutes=15 * i)
        if i == 0:
            o, h, l, c = 1.1000, 1.1005, ref_low - 0.0010, 1.1000
        else:
            o, h, l, c = 1.1000, 1.1006, 1.0994, 1.1000
        candles.append(Candle(t, o, h, l, c))
    return candles


def _ssc_config():
    cfg = dict(load_config(repo_root="."))
    cfg["regime"] = dict(cfg["regime"])
    cfg["regime"]["ema_fast_period"] = 3
    cfg["regime"]["ema_slow_period"] = 5
    cfg["regime"]["min_reference_candles"] = 8
    return cfg


def _ssc_ready_envelope():
    candles = _synthetic_candles()
    config = _ssc_config()
    result = run_replay(candles, config, "EURUSD", "ASIAN_LONDON", DAY, PIP, bias_result=_bullish_bias())
    accepted = result.accepted_setups[0]
    envelope = ssc_to_canonical(
        accepted, symbol="EURUSD", session_pair_id="ASIAN_LONDON", trading_date=DAY,
        campaign_id=result.campaign.campaign_id,
        strategy_authority=resolve_strategy_authority(SSC_STRATEGY_ID, SSC_STRATEGY_VERSION),
    )
    snapshot = from_real_candle("EURUSD", "M15", candles[-1])
    return apply_formation_gate(envelope, market_snapshot=snapshot)


def _lsmc_ready_envelope():
    decision = LargeSMCResearchDecision(
        strategy_version=LSMC_STRATEGY_VERSION, symbol="EURUSD",
        evaluation_timestamp=datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
        entry_condition="E1", maneuver="M1", combination="E1M1", direction="LONG",
        candidate_occurrence_id="OCC-CROSS-1", entry_price=1.1000,
        structural_invalidation_price=1.0980, simulated_broker_stop=1.0985,
        target_price=1.1050, target_tier="PRIMARY_EXTERNAL_LIQUIDITY", target_type="LIQUIDITY_POOL",
        state="RESEARCH_QUALIFIED",
    )
    envelope = lsmc_to_canonical(decision, resolve_strategy_authority(LSMC_STRATEGY_ID, LSMC_STRATEGY_VERSION))
    snapshot = from_real_candle(
        "EURUSD", "M15", Candle(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc), 1.1, 1.1, 1.1, 1.1),
    )
    return apply_formation_gate(envelope, market_snapshot=snapshot)


def test_cross_strategy_ledger_coexistence_and_idempotency():
    ssc_envelope = _ssc_ready_envelope()
    lsmc_envelope = _lsmc_ready_envelope()
    assert ssc_envelope.proposal_state == PROPOSAL_READY
    assert lsmc_envelope.proposal_state == PROPOSAL_READY

    # 1: distinct strategy_ids -> distinct identities, never colliding.
    assert ssc_envelope.proposal_envelope_id != lsmc_envelope.proposal_envelope_id
    assert ssc_envelope.strategy_id != lsmc_envelope.strategy_id

    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/cross_ledger.json"
        ledger = ProposalLedger(path)

        ssc_first = ledger.record_proposal(ssc_envelope)
        lsmc_first = ledger.record_proposal(lsmc_envelope)

        # 2/3: repeated identical decision from either strategy is idempotent.
        ssc_second = ledger.record_proposal(ssc_envelope)
        lsmc_second = ledger.record_proposal(lsmc_envelope)
        assert ssc_second.version == ssc_first.version == 1
        assert lsmc_second.version == lsmc_first.version == 1

        # 5: neither record is disturbed by the other's writes.
        assert ledger.get_proposal(ssc_envelope.proposal_envelope_id).strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
        assert ledger.get_proposal(lsmc_envelope.proposal_envelope_id).strategy_id == "ST_LARGE_SMC_V1"

        # 4: restart (fresh ProposalLedger instance, same store path) does not duplicate either.
        restarted_ledger = ProposalLedger(path)
        active = restarted_ledger.list_active_proposals()
        assert len(active) == 2
        by_strategy = {p.strategy_id for p in active}
        assert by_strategy == {"ST_SESSION_SWEEP_CONTINUATION_V1", "ST_LARGE_SMC_V1"}

        # 6: strategy/version/setup identity remains inspectable per record.
        ssc_record = restarted_ledger.get_proposal(ssc_envelope.proposal_envelope_id)
        lsmc_record = restarted_ledger.get_proposal(lsmc_envelope.proposal_envelope_id)
        assert ssc_record.strategy_version == "1.0.1"
        assert ssc_record.setup_evidence["setup_model"] in ("S1_SWEEP_REVERSAL", "S2_BREAKOUT_CONTINUATION", "S3_PULLBACK_CONTINUATION")
        assert lsmc_record.strategy_version == "1.0.7"
        assert lsmc_record.setup_evidence["combination"] == "E1M1"
