"""poll_symbols() -- multi-symbol surveillance (spec section 49). Caller supplies the
already-built SMCConditionalEntryAnalysis per symbol (this module never fetches MT5 data
or hardcodes a symbol universe -- the caller's configured symbol list stays the caller's
own responsibility, e.g. daytrading_runtime's existing symbol iteration)."""
from __future__ import annotations

from typing import Dict

from entry_confirmation.entry_models_v1 import SMCConditionalEntryAnalysis

from .engine import update_surveillance
from .models import SurveillanceUpdate


def poll_symbols(analyses: Dict[str, SMCConditionalEntryAnalysis], store) -> Dict[str, SurveillanceUpdate]:
    return {symbol: update_surveillance(analysis, store) for symbol, analysis in analyses.items()}
