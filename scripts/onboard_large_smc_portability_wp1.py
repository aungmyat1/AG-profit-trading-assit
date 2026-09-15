"""Portability WP1-WP4: onboard ST_LARGE_SMC_V1 into the frozen AG validation
foundation via StrategyValidationProfile + VALIDATION_ADMISSION, for the target
universe EURUSD/GBPUSD/USDJPY/XAUUSD.

Every field below is copied from an already-existing, citable repository source (see
inline comments) -- nothing is invented to make Large SMC look more admission-ready
than it is. In particular:

- `symbols=("EURUSD",)` mirrors `large_smc_research.engine.FROZEN_INSTRUMENT_UNIVERSE`
  exactly (docs/specs/LARGE_SMC_V1_SPEC.md Section 6: "C01 (instrument list), RESOLVED:
  [EURUSD] only... GBPUSD explicitly deferred"). GBPUSD/USDJPY/XAUUSD are therefore
  expected to BLOCK on admission with SYMBOL_NOT_IN_CANONICAL_UNIVERSE -- this script
  does not widen the universe to make them pass.
- `friction_policy_ref=None` and `validation_policy_ref=None` because no Large-SMC-
  specific friction/cost model or signed validation policy exists anywhere in the
  repository (confirmed by search and by
  src/validation_framework/adapters/large_smc_adapter.py's own docstring: "Friction: no
  Large-SMC-specific cost/friction model or test was found").
- `dataset_roles={}` because no `config/historical_datasets/` package declares
  development/holdout roles for Large SMC specifically (the golden fixture and
  qualified-event corpus the adapter cites are real artifacts but not declared as a
  role-labeled dataset package).
- `hypothesis_state=None` because no G1 preregistration exists for ST_LARGE_SMC_V1.
- `holdout_metadata=None` because no holdout has been reserved for ST_LARGE_SMC_V1.

Read-only: performs no strategy execution, no optimization, no dataset generation, no
holdout access, no file write to any governance/strategy file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validation_framework.ag_validation_methodology import METHODOLOGY_ID  # noqa: E402
from validation_framework.svos_contracts import StrategyValidationProfile  # noqa: E402
from validation_framework.validation_admission import run_validation_admission  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET_UNIVERSE = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")


def _sha256_of_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def build_large_smc_profile() -> StrategyValidationProfile:
    spec_path = os.path.join(REPO_ROOT, "docs", "specs", "LARGE_SMC_V1_SPEC.md")
    return StrategyValidationProfile(
        strategy_id="ST_LARGE_SMC_V1",
        strategy_version="1.0.7",  # strategies/ST_LARGE_SMC_V1.yaml top-level `version`
        methodology_id=METHODOLOGY_ID,
        strategy_spec_ref="docs/specs/LARGE_SMC_V1_SPEC.md",
        strategy_spec_hash=_sha256_of_file(spec_path),
        implementation_ref="src/large_smc_research/engine.py",
        symbols=("EURUSD",),  # large_smc_research.engine.FROZEN_INSTRUMENT_UNIVERSE
        timeframes=("D1", "H1", "M5"),  # strategies/ST_LARGE_SMC_V1.yaml timeframe_authority
        session_timezone_contract_ref=(
            "strategies/ST_LARGE_SMC_V1.yaml: timezone=UTC; "
            "daily_or_session_reset=NOT_APPLICABLE (no session/day boundary participates in identity)"
        ),
        dataset_roles={},  # no role-labeled dataset package declared for this strategy
        friction_policy_ref=None,  # no Large-SMC-specific friction/cost model exists
        validation_policy_ref=None,  # no signed validation policy exists for this strategy
        hypothesis_state=None,  # no G1 preregistration exists yet
        mutable_parameters={},
        immutable_parameters={
            # C10_STRUCTURAL_INVALIDATION_V1, SIGNED_AND_LOCKED (strategies/ST_LARGE_SMC_V1.yaml)
            "c10_atr_timeframe": "M5", "c10_atr_period": 14, "c10_atr_multiplier": 0.35,
            "c10_min_buffer_pips": 1.5,
        },
        holdout_metadata=None,  # no holdout reserved for this strategy
        execution_authority_metadata={
            "demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False,
        },  # strategies/ST_LARGE_SMC_V1.yaml:134-136 / strategies/registry.yaml
    )


def main() -> dict:
    profile = build_large_smc_profile()
    admissions = {
        symbol: run_validation_admission(profile, symbol=symbol)
        for symbol in TARGET_UNIVERSE
    }

    report = {
        "schema_version": "1.0",
        "strategy_id": profile.strategy_id,
        "strategy_version": profile.strategy_version,
        "methodology_id": profile.methodology_id,
        "canonical_symbol_universe": list(profile.symbols),
        "target_universe_this_mission": list(TARGET_UNIVERSE),
        "admissions": {
            symbol: {
                "result": result.result.value,
                "reason_codes": list(result.reason_codes),
            }
            for symbol, result in admissions.items()
        },
        "g0_readiness": {
            symbol: ("READY_FOR_G0_EVALUATION" if result.result.value == "PASS" else "NOT_READY")
            for symbol, result in admissions.items()
        },
    }

    out_path = os.path.join(
        REPO_ROOT, "artifacts", "validation", "ST_LARGE_SMC_V1", "PORTABILITY_WP1_ADMISSION_REPORT.json",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
