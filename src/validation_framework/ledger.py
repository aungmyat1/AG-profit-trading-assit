"""AG_EGSVF_V1 -- derived, immutable validation ledger + PROJECT_STATUS discrepancy
detector.

The ledger is NOT a new strategy source of truth: every field in it is either copied
from a StrategyValidationRecord (itself built by an adapter from primary evidence) or a
repository-identity fact (git HEAD, timestamp). Building or reading this ledger never
mutates any strategy file, campaign state, historical evidence, or authorization.

Snapshot policy: one JSON file per (repository HEAD, evaluation run), named with both,
so re-running the build never overwrites a prior snapshot -- see build_and_write_snapshot.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from validation_framework.models import GateResult, GateStatus, StrategyValidationRecord

FRAMEWORK_ID = "AG_EGSVF_V1"
FRAMEWORK_VERSION = "1.0.0"

DEFAULT_LEDGER_DIR = os.path.join("artifacts", "validation_ledger")


def _serialize_gate(result: GateResult) -> Dict[str, Any]:
    d = asdict(result)
    d["status"] = result.status.value
    d["evaluated_at"] = result.evaluated_at.isoformat()
    return d


def serialize_record(record: StrategyValidationRecord) -> Dict[str, Any]:
    return {
        "strategy_id": record.identity.strategy_id,
        "semantic_version": record.identity.semantic_version,
        "interface_version": record.identity.interface_version,
        "lifecycle_stage": record.lifecycle_stage.value,
        "gate_results": {name: _serialize_gate(g) for name, g in record.gates.items()},
        "execution_capability": record.execution_capability,
        "execution_capability_evidence": list(record.execution_capability_evidence),
        "execution_authority": record.execution_authority,
        "execution_authority_evidence": list(record.execution_authority_evidence),
        "next_transition": record.next_transition.value if record.next_transition else None,
        "promotion_eligible": record.promotion_eligible,
        "promotion_blockers": list(record.promotion_blockers),
        "last_updated": record.last_updated.isoformat(),
        "details": dict(record.details),
    }


def build_ledger(
    records: Sequence[StrategyValidationRecord],
    repository_head: str,
    evaluated_at: datetime = None,
) -> Dict[str, Any]:
    evaluated_at = evaluated_at or datetime.now(timezone.utc)
    return {
        "framework_id": FRAMEWORK_ID,
        "framework_version": FRAMEWORK_VERSION,
        "repository_head": repository_head,
        "evaluated_at": evaluated_at.isoformat(),
        "strategies": [serialize_record(r) for r in records],
        "source_conflicts": [],
    }


def write_snapshot(ledger: Dict[str, Any], out_dir: str = DEFAULT_LEDGER_DIR) -> str:
    """Writes an immutable, uniquely-named snapshot. Never overwrites an existing file
    -- if the exact (head, timestamp) name already exists, a numeric suffix is added
    rather than replacing it."""
    os.makedirs(out_dir, exist_ok=True)
    head_short = (ledger.get("repository_head") or "unknown")[:12]
    ts = ledger["evaluated_at"].replace(":", "").replace("-", "")
    base_name = f"AG_STRATEGY_PORTFOLIO_LEDGER_V1_{head_short}_{ts}.json"
    path = os.path.join(out_dir, base_name)
    suffix = 1
    while os.path.exists(path):
        path = os.path.join(out_dir, f"AG_STRATEGY_PORTFOLIO_LEDGER_V1_{head_short}_{ts}-{suffix}.json")
        suffix += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


# ---------------------------------------------------------------------------
# PROJECT_STATUS.md discrepancy detector.
#
# Direction is deliberately: primary evidence (the ledger, already built from adapters)
# -> compare against -> PROJECT_STATUS.md prose. PROJECT_STATUS.md is never treated as
# ground truth to validate the ledger against (see AGENT PROMPT section 48).
# ---------------------------------------------------------------------------


def _find_strategy(ledger: Dict[str, Any], strategy_id: str) -> Dict[str, Any]:
    for s in ledger["strategies"]:
        if s["strategy_id"] == strategy_id:
            return s
    return {}


def _last_match(pattern: str, text: str):
    """PROJECT_STATUS.md is an append-mostly, chronologically-ordered rolling log --
    earlier dated milestone lines (e.g. a superseded shadow series) legitimately contain
    stale numbers that must not be mistaken for the document's current claim. Taking the
    LAST match rather than the first avoids exactly the false positive this module
    itself hit during development: `invalid_days=0` from a 2026-09-02 Series 001 entry
    was picked up by a first-match search instead of the current, canonical
    `invalid_days = 1` reconciliation line further down the file. Callers needing a
    specific claim (not "whatever is most recent") should scope `text` to a section
    first."""
    matches = list(re.finditer(pattern, text))
    return matches[-1] if matches else None


def detect_project_status_discrepancies(
    ledger: Dict[str, Any], project_status_text: str
) -> List[Dict[str, Any]]:
    """Checks a small, explicit set of promotion-critical numeric/status claims that
    PROJECT_STATUS.md makes in prose against the ledger's own evidence-derived values.
    This is intentionally narrow (not a general-purpose document parser) -- it targets
    the exact claims section 49 of the AGENT PROMPT gives as the worked example (BTC
    forward count) plus the FX shadow-series equivalent.
    """
    findings: List[Dict[str, Any]] = []

    btc = _find_strategy(ledger, "ST_LIQUIDITY_SWEEP_RETEST_V1")
    btc_gate = (btc.get("gate_results") or {}).get("NATURAL_CAMPAIGN_ACCRUAL", {})
    btc_observed = (btc_gate.get("details") or {}).get("observed_count")
    btc_target = (btc_gate.get("details") or {}).get("target_count")
    if btc_observed is not None:
        m = _last_match(r"BTC[^\n]*?(\d+)\s*/\s*30", project_status_text)
        doc_value = f"{m.group(1)}/30" if m else None
        primary_value = f"{btc_observed}/{btc_target}"
        classification = "NOT_VERIFIABLE"
        if doc_value is not None:
            classification = "CONSISTENT" if doc_value == primary_value else (
                "PROJECT_STATUS_STALE" if int(m.group(1)) < btc_observed else "PROJECT_STATUS_OVERSTATED"
            )
        findings.append(
            {
                "field": "BTC_FORWARD_OBSERVATION_COUNT",
                "PROJECT_STATUS_value": doc_value,
                "primary_evidence_value": primary_value,
                "authoritative_source": "journal/reports/btc/ (archived observation count)",
                "classification": classification,
                "recommended_documentation_action": "none" if classification == "CONSISTENT" else "update PROJECT_STATUS.md's BTC observation counter",
            }
        )

    fx = _find_strategy(ledger, "ST_ASIAN_SWEEP_5R_V1")
    fx_gate = (fx.get("gate_results") or {}).get("SHADOW_SERIES_COMPLETION", {})
    fx_details = fx_gate.get("details") or {}
    fx_valid = fx_details.get("valid_days")
    fx_target = fx_details.get("target_valid_days")
    fx_invalid = fx_details.get("invalid_days")
    if fx_valid is not None:
        m = _last_match(r"valid_days\s*=\s*(\d+)\s*/\s*(\d+)", project_status_text)
        doc_value = f"{m.group(1)}/{m.group(2)}" if m else None
        primary_value = f"{fx_valid}/{fx_target}"
        classification = "NOT_VERIFIABLE"
        if doc_value is not None:
            classification = "CONSISTENT" if doc_value == primary_value else "SOURCE_CONFLICT"
        findings.append(
            {
                "field": "FX_SHADOW_SERIES_002_VALID_DAYS",
                "PROJECT_STATUS_value": doc_value,
                "primary_evidence_value": primary_value,
                "authoritative_source": "docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_*_STATUS.md",
                "classification": classification,
                "recommended_documentation_action": "none" if classification == "CONSISTENT" else "reconcile FX shadow counters between PROJECT_STATUS.md and dated day-status documents",
            }
        )
        m2 = _last_match(r"invalid_days\s*=\s*(\d+)", project_status_text)
        if m2 is not None and fx_invalid is not None:
            doc_invalid = int(m2.group(1))
            classification2 = "CONSISTENT" if doc_invalid == fx_invalid else "SOURCE_CONFLICT"
            findings.append(
                {
                    "field": "FX_SHADOW_SERIES_002_INVALID_DAYS",
                    "PROJECT_STATUS_value": str(doc_invalid),
                    "primary_evidence_value": str(fx_invalid),
                    "authoritative_source": "docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md",
                    "classification": classification2,
                    "recommended_documentation_action": "none" if classification2 == "CONSISTENT" else "reconcile FX shadow invalid-day counter",
                }
            )

    return findings
