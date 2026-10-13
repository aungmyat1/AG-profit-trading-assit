"""CCFD observational lane (AGP-C18-R2, owner decision D3).

Runs the existing archive-first `v1_tickets.crypto_cfd.run_crypto_cfd_windows` (runtime contract
ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0, unchanged; its own CycleDecisionRecord archive stays authoritative)
and turns each per-symbol row into a REPORT_ONLY observation. A priced plan becomes a CANDIDATE; the
row's own BLOCKED / NO_TRADE / DATA_ERROR decisions are preserved with their reasons (including
LOGIC_STATUS_NOT_VERIFIED). Scope status is per symbol and direction (resolve_ticket_scope); the
registry records no weekday/weekend window, so a window is never assumed verified.

OD1014 (owner-directed, pending ratification): unverified is not blocked on the report lane only. A row
whose ONLY block reason is LOGIC_STATUS_NOT_VERIFIED and which carries a complete contract-priced plan
(direction, entry, stop, TP1 and TP2) is reported as a non-executable CANDIDATE stamped with the
registry verification status of its own 1.0.0 identity. Any other reason keeps it BLOCKED. The manual /
canonical ticket gating (v1_tickets.manual_ticket) is unchanged.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from reporting.common import archive_observation, block, observational_canonical

FAMILY = "crypto_cfd"
UNVERIFIED_ONLY = "LOGIC_STATUS_NOT_VERIFIED"


def _complete_plan(row: Dict[str, Any]) -> bool:
    return bool(row.get("direction")) and all(row.get(k) is not None for k in ("entry", "stop_loss", "tp1", "tp2"))


def unverified_opportunity(row: Dict[str, Any]) -> bool:
    """BLOCKED solely by LOGIC_STATUS_NOT_VERIFIED with a complete priced plan (OD1014)."""
    return (row.get("decision") == "BLOCKED" and list(row.get("reason_codes") or []) == [UNVERIFIED_ONLY]
            and _complete_plan(row))


def _class_for(row: Dict[str, Any]) -> str:
    decision = row.get("decision")
    if decision == "DATA_ERROR":
        return "DATA_ERROR"
    if decision == "NO_TRADE":
        return "NO_OPPORTUNITY"
    priced = row.get("direction") and row.get("entry") is not None and row.get("stop_loss") is not None
    if decision == "READY" and priced:
        return "CANDIDATE"
    if guard_verdicts(row):
        return "CANDIDATE"
    if unverified_opportunity(row):
        return "CANDIDATE"
    if row.get("cycle") == "OUTSIDE_WINDOW":
        return "OUT_OF_SESSION"
    return "BLOCKED"


GUARD_REASONS = frozenset({"SPREAD_TOO_WIDE", "COST_TOO_HIGH"})


def guard_verdicts(row: Dict[str, Any]) -> List[str]:
    """OD1014-FAST D4: verdict lines for a priced row blocked only by spread/cost guards (plus, per OD1014, the
    unverified logic status). Any other reason, or a guard without its measured value, -> [] (stays BLOCKED)."""
    reasons = set(row.get("reason_codes") or [])
    if row.get("decision") != "BLOCKED" or not reasons & GUARD_REASONS or not _complete_plan(row):
        return []
    if reasons - GUARD_REASONS - {UNVERIFIED_ONLY}:
        return []
    from v1_tickets.crypto_cfd_policy import load_ticket_policy
    policy = load_ticket_policy()
    out = []
    if "SPREAD_TOO_WIDE" in reasons:
        pct, limit = row.get("spread_pct_of_stop"), policy.get("spread_block_pct")
        if not isinstance(pct, (int, float)) or limit is None:
            return []
        out.append(f"spread {pct:.0f}% of risk > {limit:g}% -- NOT ACTIONABLE")
    if "COST_TOO_HIGH" in reasons:
        cost, limit = row.get("cost_in_R"), policy.get("cost_block_R")
        if not isinstance(cost, (int, float)) or limit is None:
            return []
        out.append(f"cost {cost:.2f}R >= {limit:g}R -- NOT ACTIONABLE")
    return out


def observe_row(row: Dict[str, Any], *, now: dt.datetime, policy=None) -> Dict[str, Any]:
    report_class = _class_for(row)
    raw = dict(row)
    if report_class in ("BLOCKED", "OUT_OF_SESSION") and raw.get("decision") == "READY":
        raw["decision"] = "BLOCKED"          # a READY without a complete priced plan is never a candidate
    verdicts = guard_verdicts(row) if report_class == "CANDIDATE" else []
    unverified = report_class == "CANDIDATE" and (unverified_opportunity(row) or bool(verdicts))
    if unverified:
        raw["decision"] = "SHADOW_INFO_ONLY"  # observation only; the source row stays BLOCKED in its archive
        raw["reason_code"] = "REPORT_ONLY_OBSERVATION"
    canonical = observational_canonical(raw, now=now, report_class=report_class, policy=policy)
    if unverified:
        canonical["opportunity_basis"] = ("OD1014_FAST_D4_GUARD_VERDICT" if verdicts
                                          else "OD1014_UNVERIFIED_NOT_BLOCKED")
    if verdicts:
        canonical["guard_verdicts"] = verdicts
    if canonical.get("report_class") == "CANDIDATE":
        # Registry status of the ticket's own identity (resolve_ticket_scope, version-bound); never borrowed.
        canonical["verification_status"] = canonical.get("scope_verification_status") or "UNVERIFIED"
        if canonical["verification_status"] == "SUSPENDED":
            block(canonical, "SCOPE_SUSPENDED")
    canonical["sizing_inputs"] = {"commission_R": row.get("commission_R")}
    return canonical


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
