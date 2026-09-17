"""One real-market evaluation cycle for ST_SESSION_SWEEP_CONTINUATION_V1 (SSC).

Orchestration only -- every computation delegates to an already-existing, unmodified
module: real candle fetch (mt5.market_data.get_candles), the canonical SSC engine
(session_sweep_continuation.replay.run_replay), live H1 bias (this package's bias.py,
itself a thin reuse of already-live-wired generic functions), the strategy-neutral
proposal envelope (proposal_envelope.models/ledger/formation_gate), and the new
SSC-specific adapter (proposal_envelope.adapters.ssc_adapter). No S1/S2/S3 logic, stop
model, or risk model is reimplemented here.

Any exception raised while forming/persisting a canonical proposal for one accepted
setup is caught and logged -- it can never abort evaluation of the remaining setups or
symbols this cycle (mirrors post_asian_pilot.pipeline's own isolation invariant)."""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from mt5.market_data import MarketDataError, get_candles
from mt5.symbol_resolver import SymbolMetaError, get_symbol_meta
from proposal_envelope.adapters.ssc_adapter import to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import PROPOSAL_READY
from proposal_envelope.strategy_authority import resolve_strategy_authority
from session_sweep_continuation import STRATEGY_ID, STRATEGY_VERSION
from session_sweep_continuation.config import compute_config_hash, load_config
from session_sweep_continuation.replay import ReplayResult, run_replay
from session_sweep_continuation.sessions import session_windows_from_config
from strategy_contract.market_snapshot import MarketSnapshot, from_real_candle

from .bias import resolve_live_h1_bias

logger = logging.getLogger("session_sweep_continuation_pilot.pipeline")


def _pip_size_for(symbol_meta) -> float:
    # No existing repo convention derives pip_size for a live SSC cycle (every current
    # caller of run_replay is test/historical-fixture-supplied, see WP1 audit). Standard
    # 5-digit-broker FX convention: pip = 10 * point (3-digit JPY-style pairs included).
    # If a future authoritative pip_size source is established, this is the one place to
    # update -- never silently duplicated elsewhere.
    return symbol_meta.point * 10


@dataclass(frozen=True)
class SymbolCycleResult:
    symbol: str
    session_pair: str
    replay_result: Optional[ReplayResult]
    proposals_formed: int
    error: Optional[str] = None


@dataclass(frozen=True)
class SSCCycleResult:
    trading_date: dt.date
    results: Tuple[SymbolCycleResult, ...]


def _evaluate_symbol_session(
    config: dict, symbol: str, session_pair_id: str, trading_date: dt.date,
    proposal_ledger: ProposalLedger, config_hash: str,
) -> SymbolCycleResult:
    windows = session_windows_from_config(config)[session_pair_id]
    ref_start, _ = windows["reference"].bounds_for_date(trading_date)
    _, trade_end = windows["trade"].bounds_for_date(trading_date)

    try:
        symbol_meta = get_symbol_meta(symbol)
    except SymbolMetaError as exc:
        return SymbolCycleResult(symbol, session_pair_id, None, 0, error=str(exc))

    try:
        candles = get_candles(symbol, "M15", ref_start, trade_end)
    except MarketDataError as exc:
        return SymbolCycleResult(symbol, session_pair_id, None, 0, error=str(exc))

    if not candles:
        return SymbolCycleResult(symbol, session_pair_id, None, 0, error="NO_CANDLES")

    pip_size = _pip_size_for(symbol_meta)
    decision_time = windows["reference"].bounds_for_date(trading_date)[1]
    bias_result = resolve_live_h1_bias(symbol, decision_time, session_pair_id)

    replay_result = run_replay(
        candles, config, symbol, session_pair_id, trading_date, pip_size, bias_result=bias_result,
    )

    if not replay_result.accepted_setups:
        return SymbolCycleResult(symbol, session_pair_id, replay_result, 0)

    strategy_authority = resolve_strategy_authority(STRATEGY_ID, STRATEGY_VERSION)
    campaign_id = replay_result.campaign.campaign_id if replay_result.campaign else None
    last_candle = candles[-1]
    market_snapshot = from_real_candle(symbol, "M15", last_candle)

    formed = 0
    for accepted_setup in replay_result.accepted_setups:
        try:
            envelope = to_canonical_proposal(
                accepted_setup, symbol=symbol, session_pair_id=session_pair_id,
                trading_date=trading_date, campaign_id=campaign_id,
                strategy_authority=strategy_authority,
            )
            gated = apply_formation_gate(envelope, market_snapshot=market_snapshot)
            if gated.proposal_state == PROPOSAL_READY:
                gated = dataclasses.replace(gated, config_hash=config_hash, engine_release=None, git_commit=None)
                proposal_ledger.record_proposal(gated)
                formed += 1
            else:
                logger.info(
                    "SSC canonical proposal formation rejected symbol=%s reasons=%s",
                    symbol, gated.reasons,
                )
        except Exception:  # noqa: BLE001 -- must never affect evaluation of other setups
            logger.exception("SSC canonical proposal formation failed symbol=%s setup=%s", symbol, accepted_setup)

    return SymbolCycleResult(symbol, session_pair_id, replay_result, formed)


def run_ssc_cycle(
    trading_date: Optional[dt.date] = None, proposal_ledger: Optional[ProposalLedger] = None,
) -> SSCCycleResult:
    config = load_config()
    config_hash = compute_config_hash(config)
    trading_date = trading_date or dt.datetime.now(dt.timezone.utc).date()
    proposal_ledger = proposal_ledger if proposal_ledger is not None else ProposalLedger()

    results: List[SymbolCycleResult] = []
    for symbol in config.get("instruments", ()):
        for pair in config.get("session_pairs", ()):
            session_pair_id = pair["pair_id"]
            try:
                result = _evaluate_symbol_session(
                    config, symbol, session_pair_id, trading_date, proposal_ledger, config_hash,
                )
            except Exception:  # noqa: BLE001 -- one symbol/session failure must not block the rest
                logger.exception("SSC cycle failed symbol=%s session_pair=%s", symbol, session_pair_id)
                result = SymbolCycleResult(symbol, session_pair_id, None, 0, error="CYCLE_EXCEPTION")
            results.append(result)

    return SSCCycleResult(trading_date=trading_date, results=tuple(results))
