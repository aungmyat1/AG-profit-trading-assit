"""Data shapes for the multi-timeframe-market-context orchestrator.

Advisory only -- see .agents/skills/multi-timeframe-market-context/SKILL.md for the
full authority contract. Nothing here decides a trade; every dataclass is a normalized
report of what other, already-authoritative modules (market_structure, liquidity,
supply_demand, entry_confirmation) returned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

SKILL_ID = "multi-timeframe-market-context"
SKILL_VERSION = "1.0.0"
AUTHORITY = "ADVISORY_ONLY"

ROLE_MACRO = "MACRO"
ROLE_BIAS = "BIAS"
ROLE_WORKING = "WORKING"
ROLE_SETUP = "SETUP"
ROLE_EXECUTION = "EXECUTION"
ROLE_MANAGEMENT = "MANAGEMENT"
ALL_ROLES = (ROLE_MACRO, ROLE_BIAS, ROLE_WORKING, ROLE_SETUP, ROLE_EXECUTION, ROLE_MANAGEMENT)

STATUS_VALID = "VALID"
STATUS_PARTIAL = "PARTIAL"
STATUS_MISSING = "MISSING"
STATUS_DATA_ERROR = "DATA_ERROR"

CONTEXT_READY = "CONTEXT_READY"
PARTIAL_CONTEXT = "PARTIAL_CONTEXT"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
DATA_ERROR = "DATA_ERROR"
INVALID_PROFILE = "INVALID_PROFILE"


class InvalidProfileError(ValueError):
    """Raised for a profile with no roles set or an unknown role key -- never for a
    market-data problem (that becomes a per-role DATA_ERROR layer instead)."""


@dataclass(frozen=True)
class MTFProfile:
    """Role -> timeframe map. All roles optional; at least one must be set.
    Deliberately not a fixed D1/H4/H1/M15 hierarchy -- any string timeframe understood
    by market_structure/liquidity/supply_demand (M1/M5/M15/M30/H1/H4/D1/W1) is valid for
    any role."""
    macro: Optional[str] = None
    bias: Optional[str] = None
    working: Optional[str] = None
    setup: Optional[str] = None
    execution: Optional[str] = None
    management: Optional[str] = None

    def role_timeframes(self) -> Dict[str, str]:
        mapping = {
            ROLE_MACRO: self.macro, ROLE_BIAS: self.bias, ROLE_WORKING: self.working,
            ROLE_SETUP: self.setup, ROLE_EXECUTION: self.execution, ROLE_MANAGEMENT: self.management,
        }
        return {role: tf for role, tf in mapping.items() if tf}


@dataclass(frozen=True)
class LayerResult:
    role: str
    timeframe: str
    status: str
    structure: Any = None
    liquidity: Any = None
    zones: Any = None
    fvgs: Any = None
    confirmation: Any = None
    evidence: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    bar_close_time: Optional[datetime] = None
    data_cutoff: Optional[datetime] = None
    forming_bar_used: bool = False


@dataclass(frozen=True)
class MTFContext:
    skill_id: str
    skill_version: str
    authority: str
    symbol: str
    evaluation_time: datetime
    profile: MTFProfile
    layers: Dict[str, LayerResult]
    alignment: Dict[str, str]
    data_quality: Dict[str, Any]
    status: str
    authorization: Dict[str, bool] = field(default_factory=lambda: {
        "may_create_trade": False,
        "may_reject_trade": False,
        "may_change_strategy_decision": False,
        "may_modify_risk": False,
        "may_execute": False,
    })

    def to_dict(self) -> Dict[str, Any]:
        """Plain-dict rendering matching references/context_contract.json's shape --
        callers that want the raw dataclass objects (StructureResult etc.) should use
        the dataclass form directly instead; this is for JSON/report attachment."""
        return {
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "authority": self.authority,
            "symbol": self.symbol,
            "evaluation_time": self.evaluation_time.isoformat(),
            "status": self.status,
            "profile": self.profile.role_timeframes(),
            "layers": {
                role: {
                    "role": layer.role,
                    "timeframe": layer.timeframe,
                    "status": layer.status,
                    "evidence": list(layer.evidence),
                    "reason_codes": list(layer.reason_codes),
                    "bar_close_time": layer.bar_close_time.isoformat() if layer.bar_close_time else None,
                    "data_cutoff": layer.data_cutoff.isoformat() if layer.data_cutoff else None,
                    "forming_bar_used": layer.forming_bar_used,
                }
                for role, layer in self.layers.items()
            },
            "alignment": dict(self.alignment),
            "data_quality": dict(self.data_quality),
            "authorization": dict(self.authorization),
        }
