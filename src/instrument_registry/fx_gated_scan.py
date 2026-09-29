"""WP-7B: canonical identity authority in front of FX Opportunity evaluation.

    platform symbol -> canonical ID (registry, exact) -> resolve_identity()
      -> strategy-neutral MarketState (fx_opportunity.market_state.observe_market_state)
      -> gate_market_state() -> AUTHORITATIVE ?
           yes -> fx_opportunity.scanner.scan_symbol (unchanged) on the SAME cached bars;
                  its MarketState fingerprint must equal the gated one
           no  -> MARKETSTATE_AUTHORITY BLOCKED, OPPORTUNITY NOT_EVALUATED,
                  PROPOSAL BLOCKED, TRADETICKET BLOCKED (strategy never runs)

Composition only: the scanner/runner, ST_ASIAN_SWEEP_5R_V1, OpportunityCandidate,
ProposalEligibility, sizing and TradeTicket are not modified. Symbols without a
production canonical mapping (V1: everything except FX.EURUSD) get
CANONICAL_IDENTITY_NOT_CONFIGURED -- no fallback to the raw-symbol path and no data read.

Broker facts (server, exposed symbol names, BrokerMetadataSnapshot) are caller-supplied;
this module performs no MT5 call itself. trade_mode is INFORMATIONAL for this read-only
path and never grants or blocks anything here.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import session_clock as sc
from fx_opportunity import scanner
from fx_opportunity.instruments import get_instrument
from fx_opportunity.market_state import MarketState, observe_market_state
from mt5.market_data import MarketDataError

from .gates import BLOCKED, NOT_EVALUATED, MarketStateIdentityGate, gate_market_state
from .identity import (
    CURRENT_REGISTRY_VERSION,
    BrokerMetadataSnapshot,
    ResolutionResult,
    load_registry,
    resolve_identity,
)

CANONICAL_IDENTITY_NOT_CONFIGURED = "CANONICAL_IDENTITY_NOT_CONFIGURED"
IDENTITY_BLOCKED = "IDENTITY_BLOCKED"
MARKETSTATE_UNAVAILABLE = "MARKETSTATE_UNAVAILABLE"
MARKETSTATE_FINGERPRINT_DIVERGENCE = "MARKETSTATE_FINGERPRINT_DIVERGENCE"

FetchCandles = Callable[[str, str, dt.datetime, dt.datetime], list]


def venue_for_broker(broker_canonical_name: str, platform: str = "MT5",
                     registry_version: str = CURRENT_REGISTRY_VERSION) -> Optional[str]:
    """Registry venue whose declared broker + platform match exactly; None if none/ambiguous."""
    registry = load_registry(registry_version)
    if registry is None:
        return None
    hits = [vid for vid, v in registry.venues.items()
            if v.get("broker_canonical_name") == broker_canonical_name and v.get("platform") == platform]
    return hits[0] if len(hits) == 1 else None


def canonical_id_for(symbol: str, venue_id: Optional[str],
                     registry_version: str = CURRENT_REGISTRY_VERSION) -> Optional[str]:
    """Exact FX platform-symbol -> canonical ID lookup from the registry (base+quote ==
    symbol AND the instrument is mapped on `venue_id`). No aliasing; None if unmapped."""
    registry = load_registry(registry_version)
    if registry is None or venue_id is None:
        return None
    hits = [cid for cid, venues in registry.instruments.items()
            if venue_id in venues and venues[venue_id].identity.asset_class == "FX"
            and venues[venue_id].identity.base_asset + venues[venue_id].identity.quote_asset == symbol]
    return hits[0] if len(hits) == 1 else None


class MemoFetch:
    """Read-through cache so the gated MarketState and the unchanged scanner consume the
    exact same broker bars (one broker read per window)."""

    def __init__(self, fetch: FetchCandles):
        self._fetch = fetch
        self._cache: Dict[Tuple[Any, ...], Any] = {}
        self.calls = 0

    def __call__(self, symbol, timeframe, start, end):
        key = (symbol, timeframe, start, end)
        if key not in self._cache:
            self.calls += 1
            self._cache[key] = self._fetch(symbol, timeframe, start, end)
        return list(self._cache[key])


@dataclass(frozen=True)
class GatedSymbolScan:
    cycle: str
    symbol: str
    status: str
    reason_codes: Tuple[str, ...]
    canonical_instrument_id: Optional[str]
    resolution: Optional[ResolutionResult]
    gate: Optional[MarketStateIdentityGate]
    market_state: Optional[MarketState]
    scan: Optional[Any]  # fx_opportunity.scanner.SymbolScan when evaluated
    metadata: Optional[BrokerMetadataSnapshot]

    @property
    def opportunity_evaluated(self) -> bool:
        return self.scan is not None

    def summary(self) -> Dict[str, Any]:
        r, g = self.resolution, self.gate
        ident = r.identity if r is not None else None
        out: Dict[str, Any] = {
            "cycle": self.cycle,
            "symbol": self.symbol,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "canonical_identity": {
                "canonical_instrument_id": self.canonical_instrument_id,
                "resolution": r.status if r is not None else CANONICAL_IDENTITY_NOT_CONFIGURED,
                "registry_version": r.registry_version if r is not None else CURRENT_REGISTRY_VERSION,
                "venue_id": r.venue_id if r is not None else None,
                "server": ident.server if ident else (r.expected_server if r else None),
                "venue_symbol": ident.venue_symbol if ident else (r.expected_symbol if r else None),
                "observed_server": r.observed_server if r else None,
                "observed_symbol": r.observed_symbol if r else None,
                "mismatched_fields": list(r.mismatched_fields) if r else [],
                "instrument_identity_fingerprint": r.identity_fingerprint if r else None,
                "broker_metadata_fingerprint": r.metadata_fingerprint if r else None,
            },
            "broker_metadata": None if self.metadata is None else {
                k: v for k, v in asdict(self.metadata).items() if k not in ("source",)},
            "marketstate_authority": g.marketstate_authority if g else BLOCKED,
            "market_data_readable": g.market_data_readable if g else False,
            "opportunity": g.opportunity if (g and self.scan is not None) else NOT_EVALUATED,
            "proposal": "NO_PROPOSAL_AUTHORITY" if self.scan is not None else BLOCKED,
            "trade_ticket": "NOT_CREATED" if self.scan is not None else BLOCKED,
            "execution_authority": "NONE",
        }
        if self.scan is not None:
            out["scan"] = self.scan.summary()
        elif self.market_state is not None:
            out["market_state"] = self.market_state.to_dict()
        return out


def _blocked(cycle, symbol, status, reasons, cid, resolution=None, gate=None, state=None, metadata=None):
    return GatedSymbolScan(cycle, symbol, status, tuple(reasons), cid, resolution, gate, state, None, metadata)


def gated_scan_symbol(
    ctx: scanner.CycleContext,
    symbol: str,
    *,
    venue_id: Optional[str],
    observed_server: Optional[str],
    exposed_symbols: Optional[Iterable[str]],
    metadata: Optional[BrokerMetadataSnapshot],
    trading_date: dt.date,
    now: dt.datetime,
    fetch_candles: FetchCandles,
    market_data_mode: str,
    source: str,
    store: Any = None,
    spread_price: Optional[float] = None,
    spread_source: Optional[str] = None,
    application_lineage: Optional[str] = None,
    server_clock: Optional[Sequence[Mapping[str, Any]]] = None,
    server_clock_provider: Optional[Callable[[], Sequence[Mapping[str, Any]]]] = None,
    spread_provider: Optional[Callable[[], Tuple[Optional[float], Optional[str]]]] = None,
    registry_version: str = CURRENT_REGISTRY_VERSION,
) -> GatedSymbolScan:
    """`server_clock_provider` / `spread_provider` (live runner) are invoked only AFTER
    identity RESOLVES, so no market data is read for an unmapped or drifted instrument."""
    if venue_id is None and load_registry(registry_version) is not None:
        return _blocked(ctx.cycle, symbol, IDENTITY_BLOCKED, ("VENUE_NOT_CONFIGURED",), None, metadata=metadata)
    cid = canonical_id_for(symbol, venue_id, registry_version)
    if cid is None:
        # Distinguish "registry itself unusable" from "this symbol has no production mapping".
        if load_registry(registry_version) is None:
            res = resolve_identity(f"FX.{symbol}", venue_id=venue_id or "", observed_server=observed_server,
                                   exposed_symbols=exposed_symbols, metadata=metadata,
                                   registry_version=registry_version)
            return _blocked(ctx.cycle, symbol, IDENTITY_BLOCKED, (res.status,), None, res,
                            gate_market_state(res, None), metadata=metadata)
        return _blocked(ctx.cycle, symbol, CANONICAL_IDENTITY_NOT_CONFIGURED,
                        (CANONICAL_IDENTITY_NOT_CONFIGURED,), None, metadata=metadata)

    res = resolve_identity(cid, venue_id=venue_id or "", observed_server=observed_server,
                           exposed_symbols=exposed_symbols, metadata=metadata, registry_version=registry_version)
    if not res.resolved:
        return _blocked(ctx.cycle, symbol, IDENTITY_BLOCKED, (res.status,), cid, res,
                        gate_market_state(res, None), metadata=metadata)

    if server_clock_provider is not None:
        try:
            server_clock = server_clock_provider()
        except MarketDataError as exc:
            return _blocked(ctx.cycle, symbol, MARKETSTATE_UNAVAILABLE, (exc.reason_code,), cid, res,
                            gate_market_state(res, None), metadata=metadata)
    if spread_provider is not None:
        spread_price, spread_source = spread_provider()
    memo = fetch_candles if isinstance(fetch_candles, MemoFetch) else MemoFetch(fetch_candles)
    pilot = ctx.pilot
    ref_start, ref_end = sc.get_session_bounds(trading_date, pilot.reference_session_name)
    window = tuple(dt.datetime.combine(trading_date, dt.time.fromisoformat(t), tzinfo=dt.timezone.utc)
                   for t in (pilot.execution_window_start_utc, pilot.execution_window_end_utc))
    state, data_reasons = observe_market_state(
        instrument=get_instrument(symbol), cycle=ctx.cycle, trading_date=trading_date, now=now,
        reference_session=pilot.reference_session_name, reference_window=(ref_start, ref_end),
        execution_window=window, expected_reference_bars=sc.expected_bar_count(pilot.reference_session_name, "M15"),
        fetch_candles=memo, market_data_mode=market_data_mode, source=source,
        spread_price=spread_price, spread_source=spread_source, server_clock=server_clock,
    )
    gate = gate_market_state(res, state)
    if state is None:
        return _blocked(ctx.cycle, symbol, MARKETSTATE_UNAVAILABLE, data_reasons or ("MARKET_STATE_MISSING",),
                        cid, res, gate, metadata=metadata)
    if not gate.authoritative:
        return _blocked(ctx.cycle, symbol, IDENTITY_BLOCKED, gate.reason_codes, cid, res, gate, state, metadata)

    scan = scanner.scan_symbol(
        ctx, symbol, trading_date=trading_date, now=now, fetch_candles=memo, market_data_mode=market_data_mode,
        source=source, store=store, spread_price=spread_price, spread_source=spread_source,
        application_lineage=application_lineage, server_clock=server_clock,
    )
    if scan.market_state is None or scan.market_state.fingerprint != state.fingerprint:
        return _blocked(ctx.cycle, symbol, MARKETSTATE_FINGERPRINT_DIVERGENCE, (MARKETSTATE_FINGERPRINT_DIVERGENCE,),
                        cid, res, gate, state, metadata)
    return GatedSymbolScan(ctx.cycle, symbol, scan.status, scan.reason_codes, cid, res, gate, state, scan, metadata)
