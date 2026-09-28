"""Canonical FX instrument contract for the Opportunity platform (facts only).

Loads config/instruments/fx_opportunity_instruments.yaml and fails closed on any
missing or inconsistent field. Pip semantics are per instrument (EURUSD/GBPUSD
0.0001, USDJPY 0.01) -- nothing here assumes a universal pip.

`check_broker_spec` is a pure comparison against an object exposing MT5-style
`digits`/`point` (e.g. a read-only `symbol_info()` result); it never calls MT5 itself.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

INSTRUMENTS_PATH = "config/instruments/fx_opportunity_instruments.yaml"
_SCHEMA = "AG_FX_INSTRUMENTS_V1"
_REL_TOL = 1e-9


class InstrumentConfigError(ValueError):
    """Instrument contract missing, malformed or internally inconsistent."""


class UnknownInstrumentError(KeyError):
    """Symbol is not in the platform instrument contract -- fail closed."""


@dataclass(frozen=True)
class BrokerSymbol:
    broker: str
    symbol: str
    verified: bool


@dataclass(frozen=True)
class Broker:
    """Canonical broker identity and the servers verified for it (no credentials)."""
    key: str
    canonical_name: str
    servers: Tuple[str, ...]
    environment: str


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str
    base_currency: str
    quote_currency: str
    digits: int
    point: float
    pip_size: float
    broker_symbols: Tuple[BrokerSymbol, ...]
    time_semantics: str
    allowed_cycles: Tuple[str, ...]
    minimum_history: str
    timeframe: str

    @property
    def points_per_pip(self) -> int:
        return int(round(self.pip_size / self.point))

    def price_to_pips(self, price_distance: float) -> float:
        return round(price_distance / self.pip_size, 6)

    def broker_symbol(self, broker: str) -> BrokerSymbol:
        for entry in self.broker_symbols:
            if entry.broker == broker:
                return entry
        raise UnknownInstrumentError(f"{self.symbol}: no broker symbol mapping for {broker!r}")

    def fingerprint(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _REL_TOL * max(abs(a), abs(b))


def _require(raw: Mapping[str, Any], key: str, symbol: str) -> Any:
    if key not in raw or raw[key] in (None, ""):
        raise InstrumentConfigError(f"{symbol}: missing {key!r}")
    return raw[key]


def _parse(symbol: str, raw: Mapping[str, Any], timeframe: str, cycles: Tuple[str, ...]) -> Instrument:
    digits = int(_require(raw, "digits", symbol))
    point = float(_require(raw, "point", symbol))
    pip = float(_require(raw, "pip_size", symbol))
    if not _close(point, 10.0 ** -digits):
        raise InstrumentConfigError(f"{symbol}: point {point} inconsistent with digits {digits}")
    if not _close(pip, point * 10):
        raise InstrumentConfigError(f"{symbol}: pip_size {pip} is not 10 points ({point * 10})")
    base, quote = _require(raw, "base_currency", symbol), _require(raw, "quote_currency", symbol)
    if base + quote != symbol:
        raise InstrumentConfigError(f"{symbol}: base/quote {base}/{quote} do not form the symbol")
    if _require(raw, "time_semantics", symbol) != "UTC":
        raise InstrumentConfigError(f"{symbol}: only UTC time semantics are supported")
    allowed = tuple(_require(raw, "allowed_cycles", symbol))
    if not set(allowed) <= set(cycles):
        raise InstrumentConfigError(f"{symbol}: allowed_cycles {allowed} not within {cycles}")
    brokers = tuple(
        BrokerSymbol(broker=name, symbol=str(_require(entry, "symbol", symbol)), verified=bool(entry.get("verified")))
        for name, entry in sorted(_require(raw, "broker_symbols", symbol).items())
    )
    return Instrument(
        symbol=symbol, asset_class=str(_require(raw, "asset_class", symbol)), base_currency=base,
        quote_currency=quote, digits=digits, point=point, pip_size=pip, broker_symbols=brokers,
        time_semantics="UTC", allowed_cycles=allowed,
        minimum_history=str(_require(raw, "minimum_history", symbol)), timeframe=timeframe,
    )


def load_instruments(path: str = INSTRUMENTS_PATH) -> Dict[str, Instrument]:
    """Fresh dict per call over an immutable, per-path cached parse."""
    return dict(_load(path)[0])


def load_brokers(path: str = INSTRUMENTS_PATH) -> Dict[str, Broker]:
    return dict(_load(path)[1])


def get_broker(key: str, path: str = INSTRUMENTS_PATH) -> Broker:
    brokers = load_brokers(path)
    if key not in brokers:
        raise UnknownInstrumentError(f"{key!r} is not a broker in the instrument contract {sorted(brokers)}")
    return brokers[key]


def _parse_brokers(raw: Mapping[str, Any]) -> Tuple[Tuple[str, Broker], ...]:
    if not raw:
        raise InstrumentConfigError("no brokers defined")
    out = []
    for key, spec in sorted(raw.items()):
        env = _require(spec, "environment", key)
        if env != "DEMO":
            raise InstrumentConfigError(f"{key}: only DEMO broker environments are supported")
        out.append((key, Broker(key=key, canonical_name=str(_require(spec, "canonical_name", key)),
                                servers=tuple(str(x) for x in (spec.get("servers") or ())), environment=env)))
    return tuple(out)


@lru_cache(maxsize=8)
def _load(path: str) -> Tuple[Tuple[Tuple[str, Instrument], ...], Tuple[Tuple[str, Broker], ...]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise InstrumentConfigError(f"instrument contract not found: {path}") from exc
    if data.get("schema") != _SCHEMA:
        raise InstrumentConfigError(f"unexpected schema {data.get('schema')!r}")
    timeframe = data.get("timeframe")
    if timeframe != "M15":
        raise InstrumentConfigError(f"unsupported timeframe {timeframe!r}")
    cycles = tuple(data.get("cycles") or ())
    raw = data.get("instruments") or {}
    if not raw:
        raise InstrumentConfigError("no instruments defined")
    brokers = _parse_brokers(data.get("brokers") or {})
    instruments = tuple((sym, _parse(sym, spec, timeframe, cycles)) for sym, spec in sorted(raw.items()))
    known = {key for key, _ in brokers}
    for sym, inst in instruments:
        unknown = {b.broker for b in inst.broker_symbols} - known
        if unknown:
            raise InstrumentConfigError(f"{sym}: broker_symbols reference undefined brokers {sorted(unknown)}")
    return instruments, brokers


def get_instrument(symbol: str, path: str = INSTRUMENTS_PATH) -> Instrument:
    instruments = load_instruments(path)
    if symbol not in instruments:
        raise UnknownInstrumentError(f"{symbol!r} is not in the FX Opportunity instrument contract {sorted(instruments)}")
    return instruments[symbol]


def check_broker_spec(instrument: Instrument, info: Optional[Any]) -> Tuple[str, ...]:
    """Reason codes (empty == consistent) comparing the contract with broker facts."""
    if info is None:
        return ("BROKER_SYMBOL_UNAVAILABLE",)
    reasons = []
    if int(getattr(info, "digits", -1)) != instrument.digits:
        reasons.append("INSTRUMENT_DIGITS_MISMATCH")
    if not _close(float(getattr(info, "point", 0.0) or 0.0), instrument.point):
        reasons.append("INSTRUMENT_POINT_MISMATCH")
    return tuple(reasons)
