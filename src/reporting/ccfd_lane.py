"""CCFD observational lane (AGP-C18-R2, owner decision D3).

Runs the existing archive-first `v1_tickets.crypto_cfd.run_crypto_cfd_windows` (runtime contract
ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0, unchanged; its own CycleDecisionRecord archive stays authoritative)
and turns each per-symbol row into a REPORT_ONLY observation. A priced plan becomes a CANDIDATE; the
row's own BLOCKED / NO_TRADE / DATA_ERROR decisions are preserved with their reasons (including
LOGIC_STATUS_NOT_VERIFIED). Scope status is per symbol and direction (resolve_ticket_scope); the
registry records no weekday/weekend window, so a window is never assumed verified.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from reporting.common import archive_observation, observational_canonical

FAMILY = "crypto_cfd"


def _class_for(row: Dict[str, Any]) -> str:
    decision = row.get("decision")
    if decision == "DATA_ERROR":
        return "DATA_ERROR"
    if decision == "NO_TRADE":
        return "NO_OPPORTUNITY"
    priced = row.get("direction") and row.get("entry") is not None and row.get("stop_loss") is not None
    if decision == "READY" and priced:
        return "CANDIDATE"
    if row.get("cycle") == "OUTSIDE_WINDOW":
        return "OUT_OF_SESSION"
    return "BLOCKED"


def observe_row(row: Dict[str, Any], *, now: dt.datetime, policy=None) -> Dict[str, Any]:
    report_class = _class_for(row)
    raw = dict(row)
    if report_class in ("BLOCKED", "OUT_OF_SESSION") and raw.get("decision") == "READY":
        raw["decision"] = "BLOCKED"          # a READY without a complete priced plan is never a candidate
    return observational_canonical(raw, now=now, report_class=report_class, policy=policy)


def run_ccfd_lane(now: dt.datetime, *, feed, archive_root: str, policy=None) -> List[Dict[str, Any]]:
    """Evaluate both instruments (never silently omitted) and archive one observation per row."""
    from v1_tickets.crypto_cfd import run_crypto_cfd_windows
    out = []
    for row in run_crypto_cfd_windows(now, feed=feed, archive_root=archive_root):
        row = row[0] if isinstance(row, tuple) else row     # (ticket, archive_path)
        canonical = observe_row(row, now=now, policy=policy)
        archive_observation(archive_root, FAMILY, canonical)
        out.append(canonical)
    return out
