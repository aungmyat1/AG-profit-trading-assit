"""Phase 5 -- deterministic contractability gate. Stable reason codes, no scoring,
fail closed: ANY failing check makes the whole gate FAIL.

"Required data available" is part of contractability by mission definition: a candidate
whose instrument has no uncontaminated dataset in an allowed role cannot be screened and
must block rather than silently borrow a near-miss instrument (e.g. a USDT perpetual for
a USD CFD -- that is CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN, never a fallback).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from .models import CandidateManifest, ContractabilityResult

# Stable reason codes (Phase 5).
ENTRY_CONTRACT_UNDEFINED = "ENTRY_CONTRACT_UNDEFINED"
EXIT_CONTRACT_UNDEFINED = "EXIT_CONTRACT_UNDEFINED"
TIMEFRAMES_UNDEFINED = "TIMEFRAMES_UNDEFINED"
PARAMETERS_NOT_FROZEN = "PARAMETERS_NOT_FROZEN"
SYMBOLS_UNDEFINED = "SYMBOLS_UNDEFINED"
ASSET_CLASS_UNDEFINED = "ASSET_CLASS_UNDEFINED"
DISCRETIONARY_CONDITION_PRESENT = "DISCRETIONARY_CONDITION_PRESENT"
FUTURE_DATA_DEPENDENCY = "FUTURE_DATA_DEPENDENCY"
REQUIRED_DATA_UNAVAILABLE = "REQUIRED_DATA_UNAVAILABLE"
COST_REPRESENTATION_UNDEFINED = "COST_REPRESENTATION_UNDEFINED"
HYPOTHESIS_UNDEFINED = "HYPOTHESIS_UNDEFINED"
CREATED_AFTER_RESULTS = "CREATED_AFTER_RESULTS"
CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN = "CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN"

# Vague, non-deterministic qualifiers that must never appear in a contract reference.
_DISCRETIONARY_TOKENS = ("strong ", "good ", "clear ", "nice ", "discretion")


@dataclass(frozen=True)
class AvailableDataset:
    """Descriptor of a dataset the factory may consider (inventory entry, not bytes)."""

    dataset_id: str
    symbol: str
    asset_class: str
    role: str                                   # DatasetRole value
    timeframes: Tuple[str, ...] = ()


def dataset_satisfies(ds: AvailableDataset, manifest: CandidateManifest, symbol: str) -> bool:
    """EXACT symbol + asset-class match only. A USDT-perpetual symbol never
    satisfies the corresponding USD CFD requirement."""
    return (ds.symbol == symbol and ds.asset_class == manifest.asset_class
            and ds.role in manifest.dataset_roles_allowed)


def _near_miss_substitutions(datasets: Sequence[AvailableDataset],
                             manifest: CandidateManifest) -> Tuple[str, ...]:
    """Explicitly name forbidden near-miss instruments instead of silently ignoring
    them (e.g. a USDT-perpetual symbol offered where the USD CFD is required)."""
    notes = []
    for symbol in manifest.symbols:
        for ds in datasets:
            if ds.symbol != symbol and ds.symbol.startswith(symbol):
                notes.append(f"{CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN}:"
                             f"{ds.dataset_id}({ds.symbol}!={symbol})")
    return tuple(notes)


def evaluate_contractability(manifest: CandidateManifest,
                             available_datasets: Optional[Sequence[AvailableDataset]] = None,
                             ) -> ContractabilityResult:
    datasets = list(available_datasets or ())
    checks: dict = {}
    codes: list = []

    def check(name: str, ok: bool, code: str) -> None:
        checks[name] = "PASS" if ok else "FAIL"
        if not ok:
            codes.append(code)

    check("entry_defined", bool(str(manifest.entry_contract or "").strip()),
          ENTRY_CONTRACT_UNDEFINED)
    check("exit_defined", bool(str(manifest.exit_contract or "").strip()),
          EXIT_CONTRACT_UNDEFINED)
    check("timeframes_defined", len(manifest.timeframes) > 0, TIMEFRAMES_UNDEFINED)
    check("parameters_frozen",
          manifest.parameters_frozen and len(manifest.parameters) > 0,
          PARAMETERS_NOT_FROZEN)
    check("symbols_defined", len(manifest.symbols) > 0, SYMBOLS_UNDEFINED)
    check("asset_class_defined", bool(str(manifest.asset_class or "").strip()),
          ASSET_CLASS_UNDEFINED)
    check("hypothesis_defined", bool(str(manifest.hypothesis or "").strip()),
          HYPOTHESIS_UNDEFINED)

    vague = tuple(tok for tok in _DISCRETIONARY_TOKENS
                  for text in (manifest.entry_contract.lower(), manifest.exit_contract.lower())
                  if tok in text)
    check("no_discretionary_condition",
          not manifest.discretionary_conditions and not vague,
          DISCRETIONARY_CONDITION_PRESENT)

    check("no_future_data_dependency", not manifest.future_data_dependencies,
          FUTURE_DATA_DEPENDENCY)

    cost = manifest.cost_assumptions or {}
    check("cost_representation_possible",
          bool(cost.get("friction_model")) and bool(cost.get("evidence_kind")),
          COST_REPRESENTATION_UNDEFINED)

    check("created_before_results", manifest.created_before_results,
          CREATED_AFTER_RESULTS)

    data_ok = all(any(dataset_satisfies(ds, manifest, symbol) for ds in datasets)
                  for symbol in manifest.symbols)
    check("required_data_available", data_ok, REQUIRED_DATA_UNAVAILABLE)

    notes = _near_miss_substitutions(datasets, manifest)
    status = "PASS" if not codes else "FAIL"   # fail closed, never partial credit
    return ContractabilityResult(manifest.candidate_id, status, checks,
                                 tuple(dict.fromkeys(codes)), notes)
