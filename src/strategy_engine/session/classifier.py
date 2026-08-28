"""ER_ONLY_V2 trend/range classifier (config/session_flow_v2.yaml `session_classifier`,
classifier_id ER_ONLY_V2, VALIDATED). Reused here rather than re-derived, per the migration
policy of not inventing a new classifier when a signed one already exists.
"""
from __future__ import annotations

from enum import Enum

from .reference_box import ReferenceBox

CLASSIFIER_ID = "ER_ONLY_V2"
CLASSIFIER_VERSION = "1.0"
EFFICIENCY_RATIO_THRESHOLD = 0.40


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"


def classify(box: ReferenceBox) -> Regime:
    """Equality at the threshold belongs to TREND; a zero path length is RANGE (both per
    config/session_flow_v2.yaml's session_classifier block)."""
    if box.path_length == 0:
        return Regime.RANGE
    return Regime.TREND if box.efficiency_ratio >= EFFICIENCY_RATIO_THRESHOLD else Regime.RANGE
