"""CANONICAL_TO_BROKER_MAP -- the single versioned canonical -> broker symbol map loader
(mission AGP-C2-SYMMAP).

Map rule (``derive_map``): for each canonical instrument, of the probed broker candidates
exactly one must be present, visible and ``trade_mode == FULL``. Zero such candidates or more
than one -> ``UNMAPPED`` with an explicit reason. There is never a guessed fallback (e.g.
"assume the broker symbol equals the canonical name").

Consumers resolve only through ``resolve()`` / ``mapped_symbols()``. An ``UNMAPPED`` or unknown
canonical raises ``SymbolUnmapped`` carrying ``terminal_status = "BLOCKED"`` and a
``reason_code`` so a caller can emit a typed terminal decision instead of going silent.

Pure: no MT5 import. Host re-validation lives in scripts/host/symbol_map_smoke.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

import yaml

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_MAP_PATH = os.path.join(_REPO_ROOT, "config", "broker_symbol_map", "vt_markets_demo.yaml")
SCHEMA = "AG_CANONICAL_TO_BROKER_MAP_V1"
BROKER = "VT_MARKETS"

CANONICALS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD")
# Candidate broker spellings probed per canonical. Fixed and recorded in the evidence, so a
# map derived from a capture can be re-derived from the same candidate set.
CANDIDATE_SUFFIXES = ("", "-VIP", ".crp", "-ECN", "-STD", ".r", ".a", ".pro", "m", "+")
TRADE_MODE_FULL = "FULL"

MAPPED = "MAPPED"
UNMAPPED = "UNMAPPED"
TERMINAL_STATUS = "BLOCKED"
REASON_UNMAPPED = "SYMBOL_UNMAPPED"
REASON_NO_FULL = "NO_VISIBLE_FULL_CANDIDATE"
REASON_AMBIGUOUS = "AMBIGUOUS_FULL_CANDIDATES"
REASON_INCOMPLETE = "INCOMPLETE_PINNED_METADATA"
# Fields pinned per MAPPED entry and re-checked by the host smoke.
PINNED_FIELDS = ("trade_mode_name", "visible", "digits", "point", "trade_contract_size",
                 "volume_min", "volume_step", "volume_max", "trade_tick_size", "trade_calc_mode")


class SymbolMapError(RuntimeError):
    """Malformed / wrong-schema map file."""


class SymbolUnmapped(RuntimeError):
    terminal_status = TERMINAL_STATUS

    def __init__(self, canonical: str, reason: str):
        super().__init__(f"{REASON_UNMAPPED}: {canonical!r}: {reason}")
        self.canonical = canonical
        self.reason = reason
        self.reason_code = REASON_UNMAPPED


def candidate_names(canonical: str) -> List[str]:
    return [canonical + s for s in CANDIDATE_SUFFIXES]


@dataclass(frozen=True)
class MapEntry:
    canonical: str
    status: str
    broker_symbol: Optional[str]
    reason: Optional[str]
    expected: Mapping[str, object]


@dataclass(frozen=True)
class BrokerSymbolMap:
    version: int
    broker: str
    server: str
    evidence: str
    entries: Mapping[str, MapEntry]

    def resolve(self, canonical: str) -> str:
        entry = self.entries.get(canonical)
        if entry is None:
            raise SymbolUnmapped(canonical, "NOT_IN_MAP")
        if entry.status != MAPPED or not entry.broker_symbol:
            raise SymbolUnmapped(canonical, entry.reason or "UNMAPPED")
        return entry.broker_symbol

    def mapped_symbols(self, canonicals: Optional[Iterable[str]] = None) -> Dict[str, str]:
        names = self.entries if canonicals is None else canonicals
        resolved: Dict[str, str] = {}
        for canonical in names:
            resolved[canonical] = self.resolve(canonical)
        return resolved


def derive_map(symbols: Mapping[str, Optional[Mapping[str, object]]],
               canonicals: Iterable[str] = CANONICALS) -> Dict[str, dict]:
    """Apply the map rule to a capture: ``symbols`` is broker name -> symbol_info fields
    (None / absent = not offered by the broker). Returns canonical -> entry dict."""
    out: Dict[str, dict] = {}
    for canonical in canonicals:
        eligible = []
        for name in candidate_names(canonical):
            info = symbols.get(name)
            if info and info.get("trade_mode_name") == TRADE_MODE_FULL and info.get("visible") is True:
                eligible.append(name)
        if len(eligible) == 1:
            info = symbols[eligible[0]]
            missing = [k for k in PINNED_FIELDS if info.get(k) is None]
            if missing:
                out[canonical] = {"status": UNMAPPED, "reason": f"{REASON_INCOMPLETE}: {', '.join(missing)}"}
                continue
            out[canonical] = {"status": MAPPED, "broker_symbol": eligible[0],
                              "expected": {k: info.get(k) for k in PINNED_FIELDS}}
        elif not eligible:
            out[canonical] = {"status": UNMAPPED, "reason": REASON_NO_FULL}
        else:
            out[canonical] = {"status": UNMAPPED, "reason": f"{REASON_AMBIGUOUS}: {', '.join(eligible)}"}
    return out


def diff_map(symbol_map: BrokerSymbolMap, symbols: Mapping[str, Optional[Mapping[str, object]]]) -> List[str]:
    """Re-derive from a (live) capture and list every disagreement with the committed map.
    Empty list == the committed map still holds."""
    derived = derive_map(symbols, symbol_map.entries.keys())
    diffs: List[str] = []
    for canonical, entry in symbol_map.entries.items():
        live = derived[canonical]
        if live["status"] != entry.status:
            diffs.append(f"{canonical}: status {entry.status} -> {live['status']} ({live.get('reason', '')})")
            continue
        if entry.status == UNMAPPED:
            if live["reason"] != entry.reason:
                diffs.append(f"{canonical}: reason {entry.reason!r} -> {live['reason']!r}")
            continue
        if live["broker_symbol"] != entry.broker_symbol:
            diffs.append(f"{canonical}: broker_symbol {entry.broker_symbol} -> {live['broker_symbol']}")
            continue
        for key, want in entry.expected.items():
            got = live["expected"].get(key)
            if got != want:
                diffs.append(f"{canonical}: {key} {want!r} -> {got!r}")
    return diffs


def _parse(raw: dict) -> BrokerSymbolMap:
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise SymbolMapError(f"schema must be {SCHEMA}")
    for key in ("map_version", "broker", "server", "evidence", "entries"):
        if key not in raw:
            raise SymbolMapError(f"missing {key!r}")
    entries: Dict[str, MapEntry] = {}
    for canonical, item in (raw["entries"] or {}).items():
        status = item.get("status")
        if status == MAPPED:
            if not item.get("broker_symbol") or not isinstance(item.get("expected"), dict):
                raise SymbolMapError(f"{canonical}: MAPPED needs broker_symbol and expected")
            if item["expected"].get("trade_mode_name") != TRADE_MODE_FULL:
                raise SymbolMapError(f"{canonical}: MAPPED broker symbol must be trade_mode FULL")
            missing = [k for k in PINNED_FIELDS if item["expected"].get(k) is None]
            if missing:
                raise SymbolMapError(f"{canonical}: MAPPED expected must pin {', '.join(missing)}")
        elif status == UNMAPPED:
            if not item.get("reason") or item.get("broker_symbol"):
                raise SymbolMapError(f"{canonical}: UNMAPPED needs a reason and no broker_symbol")
        else:
            raise SymbolMapError(f"{canonical}: status must be {MAPPED} or {UNMAPPED}")
        entries[canonical] = MapEntry(canonical, status, item.get("broker_symbol"), item.get("reason"),
                                      dict(item.get("expected") or {}))
    mapped = [e.broker_symbol for e in entries.values() if e.status == MAPPED]
    if len(mapped) != len(set(mapped)):
        raise SymbolMapError("one broker symbol mapped to more than one canonical")
    return BrokerSymbolMap(int(raw["map_version"]), raw["broker"], raw["server"], raw["evidence"], entries)


_CACHE: Dict[str, BrokerSymbolMap] = {}


def load_map(path: str = DEFAULT_MAP_PATH) -> BrokerSymbolMap:
    if path not in _CACHE:
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except OSError as exc:
            raise SymbolMapError(f"cannot read {path}: {exc}") from None
        _CACHE[path] = _parse(raw)
    return _CACHE[path]


def resolve(canonical: str, path: str = DEFAULT_MAP_PATH) -> str:
    return load_map(path).resolve(canonical)
