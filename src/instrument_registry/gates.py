"""Identity gates downstream of canonical resolution (WP-7A).

MarketState gate: a MarketState is authoritative only when its instrument's canonical
identity RESOLVED and the MarketState itself matches that identity (instrument, and --
for REAL data -- every server-clock record's server). Otherwise the data may still be
readable, but MarketState authority is BLOCKED, Opportunity is NOT_EVALUATED and
Proposal/TradeTicket are BLOCKED.

TradeTicket envelope: the audited AG_TRADE_TICKET_V1 schema (frozen at 1564769) is NOT
changed. A separate, hashed envelope binds a frozen ticket to its canonical identity
(canonical_instrument_id, instrument_registry_version, venue_id, venue_symbol,
instrument_identity_fingerprint, broker_metadata_fingerprint). Moving these fields into
the ticket itself would be a TradeTicket V2 governance decision.

Pure: no MT5, no execution, no I/O beyond reading the pinned registry.
"""
from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass
from typing import Any, Optional, Tuple

from post_asian_pilot.fingerprint import fingerprint
from trade_ticket.ticket import verify_ticket_dict

from .identity import ResolutionResult, load_registry

AUTHORITATIVE = "AUTHORITATIVE"
BLOCKED = "BLOCKED"
MAY_EVALUATE = "MAY_EVALUATE"
MAY_PROCEED = "MAY_PROCEED"
NOT_EVALUATED = "NOT_EVALUATED"

ENVELOPE_SCHEMA = "AG_TICKET_INSTRUMENT_ENVELOPE_V1"


def platform_symbol(resolution: ResolutionResult) -> Optional[str]:
    """The FX Opportunity platform's instrument key for this identity (FX: base+quote).
    Other asset classes have no platform mapping in V1 (None -> blocked)."""
    ident = resolution.identity
    if ident is None or ident.asset_class != "FX":
        return None
    return ident.base_asset + ident.quote_asset


@dataclass(frozen=True)
class MarketStateIdentityGate:
    marketstate_authority: str
    market_data_readable: bool
    opportunity: str
    proposal: str
    tradeticket: str
    reason_codes: Tuple[str, ...]
    canonical_instrument_id: str
    registry_version: str
    identity_fingerprint: Optional[str]
    metadata_fingerprint: Optional[str]
    market_state_fingerprint: Optional[str]

    @property
    def authoritative(self) -> bool:
        return self.marketstate_authority == AUTHORITATIVE


def gate_market_state(resolution: ResolutionResult, market_state: Any) -> MarketStateIdentityGate:
    reasons = []
    if not resolution.resolved:
        reasons.append(resolution.status)
    else:
        expected = platform_symbol(resolution)
        if expected is None:
            reasons.append("ASSET_CLASS_HAS_NO_MARKETSTATE_MAPPING")
        elif market_state is None:
            reasons.append("MARKET_STATE_MISSING")
        else:
            if market_state.symbol != expected:
                reasons.append("MARKET_STATE_INSTRUMENT_MISMATCH")
            if market_state.market_data_mode == "REAL":
                clock = market_state.server_clock or ()
                if not clock:
                    reasons.append("MARKET_STATE_SERVER_UNVERIFIED")
                elif any(rec.get("server") != resolution.identity.server for rec in clock):
                    reasons.append("MARKET_STATE_SERVER_MISMATCH")
    ok = not reasons
    return MarketStateIdentityGate(
        marketstate_authority=AUTHORITATIVE if ok else BLOCKED,
        market_data_readable=market_state is not None,
        opportunity=MAY_EVALUATE if ok else NOT_EVALUATED,
        proposal=MAY_PROCEED if ok else BLOCKED,
        tradeticket=MAY_PROCEED if ok else BLOCKED,
        reason_codes=tuple(reasons),
        canonical_instrument_id=resolution.canonical_instrument_id,
        registry_version=resolution.registry_version,
        identity_fingerprint=resolution.identity_fingerprint,
        metadata_fingerprint=resolution.metadata_fingerprint,
        market_state_fingerprint=getattr(market_state, "fingerprint", None),
    )


@dataclass(frozen=True)
class TicketInstrumentEnvelope:
    schema: str
    ticket_id: str
    ticket_semantic_fingerprint: str
    canonical_instrument_id: str
    instrument_registry_version: str
    venue_id: str
    venue_symbol: str
    server: str
    instrument_identity_fingerprint: str
    broker_metadata_fingerprint: str
    envelope_fingerprint: str = ""


def envelope_for_ticket(ticket: Any, resolution: ResolutionResult,
                        ) -> Tuple[Optional[TicketInstrumentEnvelope], Tuple[str, ...]]:
    """Bind a frozen AG_TRADE_TICKET_V1 to its canonical identity, fail closed."""
    if not resolution.resolved:
        return None, (resolution.status,)
    ident = resolution.identity
    reasons = []
    if not verify_ticket_dict(ticket.to_dict()):
        reasons.append("TICKET_VERIFICATION_FAILED")
    if ticket.symbol != platform_symbol(resolution):
        reasons.append("TICKET_INSTRUMENT_MISMATCH")
    if ticket.broker_symbol != ident.venue_symbol:
        reasons.append("TICKET_VENUE_SYMBOL_MISMATCH")
    if ticket.server != ident.server:
        reasons.append("TICKET_SERVER_MISMATCH")
    registry = load_registry(ident.registry_version)
    venue = (registry.venues if registry else {}).get(ident.venue_id) or {}
    if ticket.environment != venue.get("environment"):
        reasons.append("TICKET_ENVIRONMENT_MISMATCH")
    if reasons:
        return None, tuple(reasons)
    env = TicketInstrumentEnvelope(
        schema=ENVELOPE_SCHEMA, ticket_id=ticket.ticket_id, ticket_semantic_fingerprint=ticket.semantic_fingerprint,
        canonical_instrument_id=ident.canonical_instrument_id, instrument_registry_version=ident.registry_version,
        venue_id=ident.venue_id, venue_symbol=ident.venue_symbol, server=ident.server,
        instrument_identity_fingerprint=resolution.identity_fingerprint,
        broker_metadata_fingerprint=resolution.metadata_fingerprint,
    )
    fp = fingerprint({k: v for k, v in asdict(env).items() if k != "envelope_fingerprint"})
    return dataclasses.replace(env, envelope_fingerprint=fp), ()
