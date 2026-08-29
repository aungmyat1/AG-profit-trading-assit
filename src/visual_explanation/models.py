"""SMC_VISUAL_EXPLANATION_V1 (spec sections 35-42): a portable, JSON-serializable
annotation model -- NOT coupled to matplotlib or any other plotting library. Existing
`chart_renderer/renderer.py` stays the one module that touches matplotlib; this module
only produces annotation *instructions* that a renderer (chart_renderer or otherwise)
can consume. Every annotation traces back to an evidence_id/source_id so a viewer can
ask "why is this here" and get a real answer (spec section 41-42).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

SMC_VISUAL_EXPLANATION_V1 = "SMC_VISUAL_EXPLANATION_V1"

ANNOTATION_BOX = "BOX"
ANNOTATION_LINE = "LINE"
ANNOTATION_MARKER = "MARKER"
ANNOTATION_LABEL = "LABEL"


@dataclass(frozen=True)
class Annotation:
    type: str  # BOX / LINE / MARKER / LABEL
    timeframe: Optional[str] = None
    timestamp: Optional[str] = None  # ISO string, for LINE/MARKER
    time_start: Optional[str] = None  # ISO string, for BOX
    time_end: Optional[str] = None
    price: Optional[float] = None  # for LINE/MARKER
    low: Optional[float] = None  # for BOX
    high: Optional[float] = None
    label: str = ""
    semantic_role: str = ""  # e.g. "POI", "ENTRY_ARRAY", "LIQUIDITY_REFERENCE", "DIRECTION"
    source_id: Optional[str] = None  # ties back to smc_map evidence, when resolvable
    developing: bool = False  # True = still forming/unconfirmed, False = CONFIRMED (spec section 52)


@dataclass(frozen=True)
class SMCVisualExplanation:
    version: str = SMC_VISUAL_EXPLANATION_V1
    symbol: str = ""
    combination: str = ""
    direction: Optional[str] = None
    snapshot_time: Optional[str] = None

    annotations: Tuple[Annotation, ...] = field(default_factory=tuple)
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
