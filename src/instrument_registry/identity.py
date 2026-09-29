"""CANONICAL_INSTRUMENT_REGISTRY_V1 (WP-7A): deterministic canonical instrument identity.

    canonical ID -> registry version -> venue -> server -> exact venue symbol
      -> observed broker symbol list + BrokerMetadataSnapshot -> ResolutionResult

Two separate models with separate fingerprints:

  CanonicalInstrumentIdentity  -- what the instrument IS (registry-owned, versioned)
  BrokerMetadataSnapshot       -- what the broker currently REPORTS (observed, read-only)

A metadata change never rewrites identity; an identity change requires a new registry
version file (config/instruments/registry/<version>.yaml), never an in-place edit --
each version's content fingerprint is pinned in REGISTRY_VERSIONS and verified on load.

Exact match only: venue symbols and servers are compared with `==`. No prefix/suffix
stripping ("EURUSD+", "EURUSD-VIP"), no case folding, no nearest match, no alias
creation, no AI. A missing expected symbol is BROKER_SYMBOL_DRIFT and resolution stops
for that instrument only; other instruments resolve independently.

Pure: no MT5 import. Observations (server, exposed symbol names, symbol_info) are
caller-supplied; `snapshot_from_symbol_info` only reads attributes of an object.

CUSTOM_BUILD_REASON = AG_SPECIFIC_IDENTITY_AND_GOVERNANCE_CONTRACT.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import yaml

from post_asian_pilot.fingerprint import fingerprint

SCHEMA = "AG_CANONICAL_INSTRUMENT_REGISTRY_V1"
# Anchored to this package's location (src/instrument_registry/ -> repository root), the
# same convention as session_clock._CONFIG_PATH -- never the process cwd (WP-7A R1).
REGISTRY_DIR = str(Path(__file__).resolve().parents[2] / "config" / "instruments" / "registry")
CURRENT_REGISTRY_VERSION = "instruments-v1.0.0"
# Content fingerprints (canonical JSON of the parsed YAML, newline-agnostic) of every
# published registry version. Editing a published file in place fails the load; a
# change must be a NEW version file plus a new entry here.
REGISTRY_VERSIONS: Dict[str, str] = {
    "instruments-v1.0.0": "322468278a4208d3764c96df8e13fc201ed329b2eb61331c2f4aafa8ff05d1b2",
}

# ---- result states ---------------------------------------------------------------
RESOLVED = "RESOLVED"
UNKNOWN_CANONICAL_INSTRUMENT = "UNKNOWN_CANONICAL_INSTRUMENT"
UNKNOWN_REGISTRY_VERSION = "UNKNOWN_REGISTRY_VERSION"
VENUE_NOT_CONFIGURED = "VENUE_NOT_CONFIGURED"
SERVER_MISMATCH = "SERVER_MISMATCH"
BROKER_SYMBOL_DRIFT = "BROKER_SYMBOL_DRIFT"
INSTRUMENT_DISABLED = "INSTRUMENT_DISABLED"
BROKER_METADATA_MISMATCH = "BROKER_METADATA_MISMATCH"
BROKER_METADATA_UNAVAILABLE = "BROKER_METADATA_UNAVAILABLE"

# ---- broker metadata field classes -----------------------------------------------
# IDENTITY_CRITICAL: must equal the registry identity exactly.
IDENTITY_CRITICAL = ("symbol", "server", "currency_base", "currency_profit")
# TRADING_CRITICAL: must be present and finite; pinned ones must equal the registry's
# expected value. tick_value is account-currency dependent, so it is required but not pinned.
TRADING_CRITICAL_PINNED = ("digits", "point", "tick_size", "contract_size", "volume_min", "volume_max", "volume_step")
TRADING_CRITICAL_REQUIRED = TRADING_CRITICAL_PINNED + ("tick_value",)
# INFORMATIONAL: recorded and fingerprinted, never gate identity in V1.
INFORMATIONAL = ("trade_mode", "execution_mode", "filling_mode")

_REL_TOL = 1e-9


class RegistryIntegrityError(RuntimeError):
    """A published registry version file no longer matches its pinned fingerprint."""


@dataclass(frozen=True)
class CanonicalInstrumentIdentity:
    canonical_instrument_id: str
    asset_class: str
    base_asset: str
    quote_asset: str
    product_type: str
    venue_id: str
    server: str
    venue_symbol: str
    enabled: bool
    registry_version: str
    settlement_currency: Optional[str] = None
    contract_multiplier: Optional[float] = None
    instrument_subtype: Optional[str] = None

    def fingerprint(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class BrokerMetadataSnapshot:
    """Observed, read-only broker facts. `observed_at` and `source` are audit context and
    are excluded from `fingerprint()` so identical metadata always hashes identically."""
    venue_id: str
    server: str
    symbol: str
    currency_base: Optional[str]
    currency_profit: Optional[str]
    digits: Optional[int]
    point: Optional[float]
    tick_size: Optional[float]
    tick_value: Optional[float]
    contract_size: Optional[float]
    volume_min: Optional[float]
    volume_max: Optional[float]
    volume_step: Optional[float]
    trade_mode: Optional[int] = None
    execution_mode: Optional[int] = None
    filling_mode: Optional[int] = None
    source: str = "MT5_SYMBOL_INFO"
    observed_at: Optional[str] = None

    def fingerprint(self) -> str:
        return fingerprint({k: v for k, v in asdict(self).items() if k not in ("source", "observed_at")})


def snapshot_from_symbol_info(info: Any, *, venue_id: str, server: str,
                              observed_at: Optional[dt.datetime] = None) -> BrokerMetadataSnapshot:
    """Map an MT5 `symbol_info()` result (any object with those attributes) to a snapshot.
    Missing attributes stay None -- never defaulted."""
    g = lambda name: getattr(info, name, None)  # noqa: E731
    return BrokerMetadataSnapshot(
        venue_id=venue_id, server=server, symbol=g("name"), currency_base=g("currency_base"),
        currency_profit=g("currency_profit"), digits=g("digits"), point=g("point"),
        tick_size=g("trade_tick_size"), tick_value=g("trade_tick_value"), contract_size=g("trade_contract_size"),
        volume_min=g("volume_min"), volume_max=g("volume_max"), volume_step=g("volume_step"),
        trade_mode=g("trade_mode"), execution_mode=g("trade_exemode"), filling_mode=g("filling_mode"),
        observed_at=observed_at.isoformat() if observed_at else None,
    )


@dataclass(frozen=True)
class VenueMapping:
    identity: CanonicalInstrumentIdentity
    expected_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class Registry:
    registry_version: str
    content_fingerprint: str
    venues: Mapping[str, Mapping[str, Any]]
    instruments: Mapping[str, Mapping[str, VenueMapping]]


@dataclass(frozen=True)
class ResolutionResult:
    status: str
    canonical_instrument_id: str
    registry_version: str
    venue_id: str
    expected_server: Optional[str] = None
    observed_server: Optional[str] = None
    expected_symbol: Optional[str] = None
    observed_symbol: Optional[str] = None
    identity: Optional[CanonicalInstrumentIdentity] = None
    identity_fingerprint: Optional[str] = None
    metadata_fingerprint: Optional[str] = None
    mismatched_fields: Tuple[str, ...] = ()
    # Report-only evidence for human review of drift; NEVER used to resolve or remap.
    drift_evidence_symbols: Tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def registry_path(version: str) -> str:
    return os.path.join(REGISTRY_DIR, f"{version}.yaml")


def content_fingerprint(raw: Mapping[str, Any]) -> str:
    return fingerprint(raw)


def _req(raw: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in raw or raw[key] in (None, ""):
        raise RegistryIntegrityError(f"{where}: missing {key!r}")
    return raw[key]


def load_registry(version: str, registry_dir: str = REGISTRY_DIR) -> Optional[Registry]:
    """None for a version that is not published (UNKNOWN_REGISTRY_VERSION). Raises
    RegistryIntegrityError if a published version's content drifted from its pin."""
    pinned = REGISTRY_VERSIONS.get(version)
    path = os.path.join(registry_dir, f"{version}.yaml")
    if pinned is None or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    actual = content_fingerprint(raw)
    if actual != pinned:
        raise RegistryIntegrityError(f"{version}: content fingerprint {actual} != pinned {pinned}")
    if raw.get("schema") != SCHEMA or raw.get("registry_version") != version:
        raise RegistryIntegrityError(f"{version}: schema/version header mismatch")
    venues = dict(_req(raw, "venues", version))
    instruments: Dict[str, Dict[str, VenueMapping]] = {}
    for cid, spec in sorted(_req(raw, "instruments", version).items()):
        where = f"{version}:{cid}"
        mappings: Dict[str, VenueMapping] = {}
        for venue_id, vspec in sorted(_req(spec, "venues", where).items()):
            if venue_id not in venues:
                raise RegistryIntegrityError(f"{where}: venue {venue_id!r} not declared")
            identity = CanonicalInstrumentIdentity(
                canonical_instrument_id=cid,
                asset_class=_req(spec, "asset_class", where), base_asset=_req(spec, "base_asset", where),
                quote_asset=_req(spec, "quote_asset", where), product_type=_req(spec, "product_type", where),
                venue_id=venue_id, server=_req(vspec, "server", where),
                venue_symbol=_req(vspec, "venue_symbol", where), enabled=vspec.get("enabled") is True,
                registry_version=version, settlement_currency=spec.get("settlement_currency"),
                contract_multiplier=spec.get("contract_multiplier"), instrument_subtype=spec.get("instrument_subtype"),
            )
            mappings[venue_id] = VenueMapping(identity, dict(vspec.get("expected_metadata") or {}))
        instruments[cid] = mappings
    return Registry(version, actual, venues, instruments)


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, float) or isinstance(observed, float):
        return _finite(expected) and _finite(observed) and \
            abs(expected - observed) <= _REL_TOL * max(abs(expected), abs(observed))
    return expected == observed


def resolve_identity(
    canonical_instrument_id: str,
    *,
    venue_id: str,
    observed_server: Optional[str],
    exposed_symbols: Optional[Iterable[str]],
    metadata: Optional[BrokerMetadataSnapshot],
    registry_version: str = CURRENT_REGISTRY_VERSION,
    registry_dir: str = REGISTRY_DIR,
) -> ResolutionResult:
    """Deterministic, fail-closed, per instrument. Order: version -> canonical ID ->
    venue -> enabled -> server -> exact symbol -> metadata availability -> metadata."""
    base = dict(canonical_instrument_id=canonical_instrument_id, registry_version=registry_version,
                venue_id=venue_id, observed_server=observed_server)

    def out(status: str, **kw: Any) -> ResolutionResult:
        return ResolutionResult(status=status, **{**base, **kw})

    registry = load_registry(registry_version, registry_dir)
    if registry is None:
        return out(UNKNOWN_REGISTRY_VERSION)
    venues = registry.instruments.get(canonical_instrument_id)
    if venues is None:
        return out(UNKNOWN_CANONICAL_INSTRUMENT)
    mapping = venues.get(venue_id)
    if mapping is None:
        return out(VENUE_NOT_CONFIGURED)
    ident = mapping.identity
    base.update(expected_server=ident.server, expected_symbol=ident.venue_symbol)
    if not ident.enabled:
        return out(INSTRUMENT_DISABLED)
    if observed_server != ident.server:
        return out(SERVER_MISMATCH)

    exposed = None if exposed_symbols is None else tuple(exposed_symbols)
    meta_fp = metadata.fingerprint() if metadata is not None else None
    if exposed is not None and ident.venue_symbol not in exposed:
        evidence = tuple(sorted(s for s in exposed if ident.venue_symbol in s))
        return out(BROKER_SYMBOL_DRIFT, observed_symbol=evidence[0] if len(evidence) == 1 else None,
                   drift_evidence_symbols=evidence, metadata_fingerprint=meta_fp)
    if metadata is not None and metadata.symbol != ident.venue_symbol:
        return out(BROKER_SYMBOL_DRIFT, observed_symbol=metadata.symbol, metadata_fingerprint=meta_fp)
    if exposed is None or metadata is None:
        return out(BROKER_METADATA_UNAVAILABLE, metadata_fingerprint=meta_fp)
    if metadata.venue_id != venue_id or metadata.server != ident.server:
        return out(SERVER_MISMATCH, observed_symbol=metadata.symbol, metadata_fingerprint=meta_fp,
                   mismatched_fields=tuple(f for f in ("venue_id", "server")
                                           if getattr(metadata, f) != (venue_id if f == "venue_id" else ident.server)))

    missing = tuple(f for f in TRADING_CRITICAL_REQUIRED if not _finite(getattr(metadata, f)))
    if missing or metadata.currency_base is None or metadata.currency_profit is None:
        return out(BROKER_METADATA_UNAVAILABLE, observed_symbol=metadata.symbol, metadata_fingerprint=meta_fp,
                   mismatched_fields=missing + tuple(f for f in ("currency_base", "currency_profit")
                                                     if getattr(metadata, f) is None))
    mismatched = []
    if metadata.currency_base != ident.base_asset:
        mismatched.append("currency_base")
    if metadata.currency_profit != ident.quote_asset:
        mismatched.append("currency_profit")
    if metadata.tick_value <= 0:
        mismatched.append("tick_value")
    for f in TRADING_CRITICAL_PINNED:
        if f in mapping.expected_metadata and not _equal(mapping.expected_metadata[f], getattr(metadata, f)):
            mismatched.append(f)
    if mismatched:
        return out(BROKER_METADATA_MISMATCH, observed_symbol=metadata.symbol, metadata_fingerprint=meta_fp,
                   mismatched_fields=tuple(mismatched))
    return out(RESOLVED, observed_symbol=metadata.symbol, identity=ident,
               identity_fingerprint=ident.fingerprint(), metadata_fingerprint=meta_fp)


def resolve_many(
    requests: Iterable[str],
    *,
    venue_id: str,
    observed_server: Optional[str],
    exposed_symbols: Optional[Iterable[str]],
    metadata_by_symbol: Mapping[str, BrokerMetadataSnapshot],
    registry_version: str = CURRENT_REGISTRY_VERSION,
    registry_dir: str = REGISTRY_DIR,
) -> Dict[str, ResolutionResult]:
    """Per-instrument resolution: one instrument's failure never blocks another.
    `metadata_by_symbol` is keyed by the EXACT expected venue symbol."""
    exposed = None if exposed_symbols is None else tuple(exposed_symbols)
    results: Dict[str, ResolutionResult] = {}
    registry = load_registry(registry_version, registry_dir)
    for cid in requests:
        mapping = (registry.instruments.get(cid) or {}).get(venue_id) if registry else None
        meta = metadata_by_symbol.get(mapping.identity.venue_symbol) if mapping else None
        results[cid] = resolve_identity(cid, venue_id=venue_id, observed_server=observed_server,
                                        exposed_symbols=exposed, metadata=meta,
                                        registry_version=registry_version, registry_dir=registry_dir)
    return results
