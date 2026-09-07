"""Read-only Large-SMC performance adapter. Reads
large_smc_research.live_ledger.LargeSMCSetupLedger's persisted rows (funnel/setup
evidence only -- SetupLedgerRow carries no resolved trade economics, so
resolved-trade metrics are always NOT_EVALUATED here until a separate outcome
resolver exists for ST_LARGE_SMC_V1). Never writes to the ledger.
"""
from __future__ import annotations

from typing import List

from large_smc_research.live_ledger import LargeSMCSetupLedger
from performance.calculator import compute_funnel_counts
from performance.models import FunnelCounts, ResolvedTradeSample


def load_large_smc_funnel_counts(ledger: LargeSMCSetupLedger) -> FunnelCounts:
    return compute_funnel_counts(list(ledger.all().values()))


def load_large_smc_resolved_samples(ledger: LargeSMCSetupLedger) -> List[ResolvedTradeSample]:
    """Always empty today: SetupLedgerRow (the only Large-SMC evidence this adapter can
    read) records setup/funnel geometry, not a resolved trade outcome -- there is no
    realized_R anywhere in it. Kept as an explicit function (rather than a bare
    constant) so a future Large-SMC outcome resolver has one obvious place to plug in
    without changing this adapter's calling convention."""
    return []
