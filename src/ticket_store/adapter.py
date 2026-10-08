"""Canonical-ticket -> TICKET_STORE_V1 EVALUATION adapter (write-only; decisions unchanged).

Called by v1_tickets.daily_evaluator after the canonical ticket is built and archived. It
copies facts that already exist on the canonical/source ticket; anything not measured on
this path is null:
- spread_at_signal: the live spread the evaluation measured, with spread_measured_at_utc
  (= evaluated_at_utc) so a reader can see it was taken at evaluation, not at signal close;
- spec_sha256: hash of the registered contract file whose `version` equals the ticket's
  strategy_version (registry config_source or candidate_versions); null when none matches;
- code_sha: v1_tickets.code_identity (null when UNKNOWN);
- input_bar_hashes: sha256 of the reference/trade bars handed to the engine (null when the
  caller supplies none, e.g. crypto or a data error).
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Sequence

import yaml

from ticket_store.store import LIVE, REPLAY, TicketStore, build_evaluation
from v1_tickets.canonical_ticket import canonical_hash

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE_SUBDIR = "ticket_store"
ACTIONABLE_STATES = frozenset({"WATCH_READY"})


@lru_cache(maxsize=None)
def spec_sha256(strategy_id: Optional[str], version: Optional[str], root: str = REPO_ROOT) -> Optional[str]:
    if not strategy_id or not version:
        return None
    try:
        with open(os.path.join(root, "strategies", "registry.yaml"), encoding="utf-8") as f:
            entry = ((yaml.safe_load(f) or {}).get("strategies") or {}).get(strategy_id) or {}
    except (OSError, yaml.YAMLError):
        return None
    paths = [entry.get("config_source")] + [c.get("config_source") for c in (entry.get("candidate_versions") or {}).values()
                                            if isinstance(c, dict)]
    for rel in filter(None, paths):
        path = os.path.join(root, rel)
        try:
            with open(path, "rb") as f:
                data = f.read()
            declared = (yaml.safe_load(data) or {}).get("version")
        except (OSError, yaml.YAMLError, AttributeError):
            continue
        if str(declared) == str(version):
            return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    return None


def bar_hash(bars: Optional[Sequence[Any]]) -> Optional[str]:
    if bars is None:
        return None
    rows = [[b.time.isoformat(), b.open, b.high, b.low, b.close] for b in bars]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _code_sha() -> Optional[str]:
    from v1_tickets.code_identity import UNKNOWN, code_sha
    sha = code_sha()
    return None if sha == UNKNOWN else sha


def evaluation_from_canonical(canonical: Dict[str, Any], ticket: Optional[Dict[str, Any]] = None, *, source: str,
                              reference_bars: Optional[Sequence[Any]] = None,
                              trade_bars: Optional[Sequence[Any]] = None) -> Dict[str, Any]:
    if source not in (LIVE, REPLAY):
        raise ValueError(f"canonical path writes LIVE or REPLAY, not {source!r}")
    ticket = ticket or {}
    prices = canonical.get("prices") or {}
    state = canonical["decision"]
    evaluated_at = canonical.get("created_at")
    spread = ticket.get("spread")
    hashes = None
    if reference_bars is not None or trade_bars is not None:
        hashes = {"reference": bar_hash(reference_bars), "reference_count": len(reference_bars or ()),
                  "trade": bar_hash(trade_bars), "trade_count": len(trade_bars or ())}
    return build_evaluation(
        ticket_id=canonical.get("ticket_id"),
        strategy=f"{canonical.get('strategy_id')}@{canonical.get('strategy_version')}",
        spec_sha256=spec_sha256(canonical.get("strategy_id"), canonical.get("strategy_version")),
        code_sha=_code_sha(), source=source,
        symbol=canonical.get("instrument"), session=canonical.get("session"), evaluated_at_utc=evaluated_at,
        signal_close_utc=(canonical.get("trigger") or {}).get("trigger_bar_close_utc"),
        state=state,
        block_reasons=[] if state in ACTIONABLE_STATES else list(canonical.get("reason_codes") or []),
        warnings=list(canonical.get("warnings") or ticket.get("warnings") or []),
        direction=canonical.get("direction"),
        entry=prices.get("entry_reference_raw"), sl=prices.get("sl_raw"),
        tp1=prices.get("tp1_raw"), tp2=prices.get("tp2_raw"),
        spread_at_signal=spread, spread_measured_at_utc=evaluated_at if spread is not None else None,
        input_bar_hashes=hashes,
        delivery_status=ticket.get("delivery_mode"),
        owner_decision_ref=None,                  # decisions are captured later, keyed by ticket_id
        provenance={"writer": "daily_evaluator", "canonical_schema": canonical.get("schema"),
                    "canonical_hash": canonical_hash(canonical), "venue": canonical.get("venue")},
    )


def write_canonical(archive_root: str, canonical: Dict[str, Any], ticket: Optional[Dict[str, Any]] = None, *,
                    source: str, reference_bars=None, trade_bars=None) -> bool:
    record = evaluation_from_canonical(canonical, ticket, source=source,
                                       reference_bars=reference_bars, trade_bars=trade_bars)
    return TicketStore(os.path.join(archive_root, STORE_SUBDIR)).append_evaluation(record)
