"""Shared fail-closed helpers for the observational report lanes (AGP-C18-R2).

An observation is built with the existing canonical ticket builder, but only after any engine READY
has been converted to a non-executable SHADOW decision, so a report lane can never yield WATCH_READY.
Observations are archived under `<archive_root>/report_lane/` -- never in TICKET_STORE, the canonical
daily_evaluator archive or any execution path.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
from typing import Any, Dict, Optional

from v1_tickets.canonical_ticket import append_archive, build_canonical_ticket

REPORT_LANE = "REPORT_ONLY_EVALUATION"
REPORT_LANE_SUBDIR = "report_lane"
OBSERVATIONAL_CLASSES = frozenset({"WATCH", "CANDIDATE", "BLOCKED", "NO_OPPORTUNITY", "DATA_ERROR",
                                   "OUT_OF_SESSION"})
_EXECUTABLE_DECISIONS = frozenset({"READY", "TICKET_READY", "WATCH_READY"})
# AGP-C18-TICKET-QUALITY: a signal past its freshness window / already touched / expired is a diagnostic.
UNACTIONABLE_DECISIONS = frozenset({"INFO_ONLY_STALE", "MISSED", "EXPIRED"})


class ReportLaneViolation(RuntimeError):
    """An observational lane produced something that could be read as executable."""


def non_executable(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of the raw ticket in which an engine READY is an explicit, non-executable observation."""
    ticket = copy.deepcopy(raw)
    if ticket.get("decision") in _EXECUTABLE_DECISIONS:
        ticket["suppressed_decision"] = ticket["decision"]
        ticket["decision"] = "SHADOW_INFO_ONLY"
        ticket["ready_authority"] = "OFF"
        ticket["reason_code"] = "REPORT_ONLY_OBSERVATION"
    return ticket


def observational_canonical(raw: Dict[str, Any], *, now: dt.datetime, current_price: Optional[float] = None,
                            window_end: Optional[dt.datetime] = None, report_class: Optional[str] = None,
                            policy=None) -> Dict[str, Any]:
    """Canonical ticket for an observation. Raises ReportLaneViolation instead of ever returning an
    executable-looking record; `report_class` may only name an observational class."""
    canonical = build_canonical_ticket(non_executable(raw), now=now, current_price=current_price,
                                       window_end=window_end, policy=policy)
    if canonical.get("decision") == "WATCH_READY" or canonical.get("report_class") == "READY_TICKET":
        raise ReportLaneViolation(f"report lane produced {canonical.get('decision')}")
    if report_class is not None:
        if report_class not in OBSERVATIONAL_CLASSES:
            raise ReportLaneViolation(f"unsupported report_class {report_class!r}")
        canonical["report_class"] = report_class
    if canonical.get("report_class") not in OBSERVATIONAL_CLASSES or canonical.get("scope_route") != "REPORT_ONLY":
        raise ReportLaneViolation("observation is not REPORT_ONLY")
    if canonical.get("execution_authorization") or canonical.get("demo_authorized") or canonical.get("live_authorized"):
        raise ReportLaneViolation("observation carries an execution authority flag")
    if canonical.get("report_class") == "CANDIDATE" and canonical.get("decision") in UNACTIONABLE_DECISIONS:
        block(canonical, str(canonical["decision"]))
    canonical["lane"] = REPORT_LANE
    return canonical


def guard_candidate(canonical: Dict[str, Any], verdicts) -> Dict[str, Any]:
    """OD1014-FAST D4 (report lane only): a complete priced plan that fails only a spread/cost guard is a
    non-executable CANDIDATE that shows the guard verdict(s), not a price-less BLOCKED. Callers check the plan
    is complete and that no other reason applies; missing/invalid inputs never reach here."""
    prices = canonical.get("prices") or {}
    if (not verdicts or not canonical.get("direction") or prices.get("entry_reference_raw") is None
            or prices.get("sl_raw") is None or prices.get("tp1_raw") is None):
        return canonical
    canonical["report_class"] = "CANDIDATE"
    canonical["guard_verdicts"] = list(verdicts)
    return canonical


def block(canonical: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Demote an observation to a BLOCKED diagnostic with an explicit reason (levels kept for audit only;
    the BLOCKED rendering never presents them as a trade). Never swaps or relabels prices."""
    canonical["report_class"] = "BLOCKED"
    canonical["reason_code"] = reason
    canonical["reason_codes"] = list(dict.fromkeys(list(canonical.get("reason_codes") or []) + [reason]))
    # The signal id is kept so delivery identity stays per signal: the same signal blocked for another
    # reason later (e.g. SPREAD_TOO_WIDE, then TARGET_ORDER_INVALID) is not reported twice.
    return canonical


def archive_observation(archive_root: str, family: str, canonical: Dict[str, Any]) -> str:
    """Append-only JSONL per family and day under report_lane/ (never the canonical evaluator archive)."""
    day = str(canonical.get("session_date") or canonical.get("created_at") or "")[:10] or "unknown-date"
    path = os.path.join(archive_root, REPORT_LANE_SUBDIR, f"{day}_{family}.jsonl")
    append_archive(path, canonical)
    return path
