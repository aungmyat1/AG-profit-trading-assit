"""Canonical instrument registry for the scanner.

Broker symbol names come ONLY from mt5.broker_symbol_resolver (config/mt5.yaml
symbol_map, fail-closed). Scanner components hold canonical symbols and resolve through
this module; nothing else in the package spells a broker suffix.

Live metadata (digits/point/trade_mode/contract size) is verified against the broker's
own symbol record. Any mismatch -- wrong name, wrong digits, trade_mode not full --
fails closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

from mt5.broker_symbol_resolver import BrokerSymbolMapError, resolve_broker_symbol

PRICE_SOURCE = "TERMINAL_MCP"


class InstrumentRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstrumentSpec:
    canonical_symbol: str
    broker_symbol: str
    asset_class: str
    expected_digits: int
    session_policy: str
    daily_break_server: Optional[tuple]


@dataclass(frozen=True)
class InstrumentRecord:
    canonical_symbol: str
    broker_symbol: str
    asset_class: str
    digits: int
    point: float
    pip_size: float
    trade_mode: str
    session_policy: str
    daily_break_server: Optional[tuple]
    price_source: str
    contract_size: float
    currency_profit: str
    volume_min: float
    volume_step: float
    tick_size: float
    tick_value: float
    volume_max: float

    def as_dict(self) -> dict:
        return asdict(self)


def load_specs(scanner_cfg: dict, resolver=resolve_broker_symbol, *, include_crypto: bool = False) -> Dict[str, InstrumentSpec]:
    broker = scanner_cfg["broker"]
    policies = scanner_cfg["session_policies"]
    specs = {}
    for canonical, item in scanner_cfg["instruments"].items():
        if item.get("asset_class") == "CRYPTO" and not include_crypto:
            continue
        try:
            broker_symbol = resolver(canonical, broker)
        except BrokerSymbolMapError as exc:
            raise InstrumentRegistryError(f"FAIL_CLOSED: {exc}") from None
        policy = policies.get(item["session_policy"])
        if policy is None:
            raise InstrumentRegistryError(f"FAIL_CLOSED: unknown session_policy {item['session_policy']!r}")
        brk = policy.get("daily_break_server")
        specs[canonical] = InstrumentSpec(canonical, broker_symbol, item["asset_class"], int(item["expected_digits"]),
                                          item["session_policy"], tuple(brk) if brk else None)
    return specs


def resolve_spec(specs: Dict[str, InstrumentSpec], canonical_symbol: str) -> InstrumentSpec:
    spec = specs.get(canonical_symbol)
    if spec is None:
        raise InstrumentRegistryError(f"FAIL_CLOSED: no scanner registry entry for {canonical_symbol!r}")
    return spec


def pip_size_for(point: float) -> float:
    # Same convention as session_sweep_continuation_pilot.pipeline._pip_size_for:
    # pip = 10 * point on 5/3-digit FX quotes. For metals this is a labeled convention
    # only (no signed metal pip definition exists in the repo).
    return round(point * 10, 10)


def spread_gate_values(asset_class: str, bid: float, ask: float, point: float, pip_size: float,
                       max_spread_pips: Optional[float]) -> dict:
    spread = ask - bid
    if asset_class == "FX" and max_spread_pips is not None:
        pips = spread / pip_size
        return {"status": "PASS" if pips <= max_spread_pips else "FAIL",
                "spread_pips": round(pips, 3), "max_spread_pips": max_spread_pips,
                "reason": "SPREAD_WITHIN_LIMIT" if pips <= max_spread_pips else "SPREAD_EXCEEDS_LIMIT"}
    values = {"spread_points": int(round(spread / point)), "spread_price": round(spread, 10),
              "spread_pct": round((spread / bid) * 100, 8) if bid else None,
              "spread_pips": None}
    if asset_class == "CRYPTO":
        return {"status": "OBSERVED_ONLY", "reason": "SPREAD_POLICY_UNDEFINED", **values}
    return {"status": "OBSERVED_ONLY", "reason": "NO_ASSET_SPREAD_POLICY", "spread_pips": None}


def verify_live(spec: InstrumentSpec, info: Optional[dict], price_source: str = PRICE_SOURCE) -> InstrumentRecord:
    if info is None:
        raise InstrumentRegistryError(f"FAIL_CLOSED: {spec.broker_symbol} not found or ambiguous on broker")
    if info.get("symbol") != spec.broker_symbol:
        raise InstrumentRegistryError(f"FAIL_CLOSED: broker returned {info.get('symbol')!r} for {spec.broker_symbol!r}")
    digits = int(info.get("digits", -1))
    if digits != spec.expected_digits:
        raise InstrumentRegistryError(f"FAIL_CLOSED: {spec.broker_symbol} digits {digits} != expected {spec.expected_digits}")
    trade_mode = str(info.get("trade_mode_name", "")).lower()
    if trade_mode != "full":
        raise InstrumentRegistryError(f"FAIL_CLOSED: {spec.broker_symbol} trade_mode {trade_mode!r} is not 'full'")
    point = float(info["point"])
    if spec.asset_class == "CRYPTO":
        required = ("tick_size", "tick_value", "contract_size", "volume_min", "volume_max", "volume_step")
        if any(info.get(key) is None for key in required):
            raise InstrumentRegistryError(f"FAIL_CLOSED: incomplete native contract metadata for {spec.broker_symbol}")
    return InstrumentRecord(
        canonical_symbol=spec.canonical_symbol, broker_symbol=spec.broker_symbol, asset_class=spec.asset_class,
        digits=digits, point=point, pip_size=pip_size_for(point), trade_mode=trade_mode,
        session_policy=spec.session_policy, daily_break_server=spec.daily_break_server, price_source=price_source,
        contract_size=float(info.get("contract_size", 0.0)), currency_profit=str(info.get("currency_profit", "")),
        volume_min=float(info.get("volume_min", 0.0)), volume_step=float(info.get("volume_step", 0.0)),
        tick_size=float(info.get("tick_size", 0.0)), tick_value=float(info.get("tick_value", 0.0)),
        volume_max=float(info.get("volume_max", 0.0)),
    )
