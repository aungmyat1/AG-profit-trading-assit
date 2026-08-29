"""SMC_SURVEILLANCE_V1 -- state tracking + transition events over SMC_CONDITIONAL_ENTRY_V2
analyses. See engine.py's module docstring for what this deliberately does and does not do.
"""
from .engine import update_surveillance
from .models import (
    EVENT_CONTEXT_QUALIFIED,
    EVENT_ENTRY_READY,
    EVENT_H1_REACTION_CONFIRMED,
    EVENT_M_CONFIRMATION_DEVELOPING,
    EVENT_REFERENCE_TOUCHED,
    EVENT_SETUP_EXPIRED,
    EVENT_SETUP_INVALIDATED,
    SMC_SURVEILLANCE_V1,
    SurveillanceEvent,
    SurveillanceUpdate,
)
from .multi_symbol import poll_symbols
from .report import compact_line, detailed_report

__all__ = [
    "update_surveillance", "poll_symbols", "compact_line", "detailed_report",
    "SurveillanceEvent", "SurveillanceUpdate", "SMC_SURVEILLANCE_V1",
    "EVENT_CONTEXT_QUALIFIED", "EVENT_REFERENCE_TOUCHED", "EVENT_H1_REACTION_CONFIRMED",
    "EVENT_M_CONFIRMATION_DEVELOPING", "EVENT_ENTRY_READY", "EVENT_SETUP_INVALIDATED", "EVENT_SETUP_EXPIRED",
]
