"""AGP-C20 T1: per-scope verification ledger (read-only, byte-reproducible).

One row per family x symbol x session/cycle x branch of the OD1012 universe (v1_tickets.scope_status.FAMILIES;
AUDUSD excluded there). Every value is read from strategies/registry.yaml (via the canonical scope resolver),
the identity code (v1_tickets.authority.logic_identity) or a committed evidence file; anything not recorded is
UNKNOWN -- never inferred. No timestamps: the same tree always yields the same bytes.

    python scripts/verification_ledger.py            # writes the two outputs
    python scripts/verification_ledger.py --check    # exit 1 if the committed outputs are stale
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

JSON_OUT = "artifacts/verification_ledger/ledger.json"
MD_OUT = "docs/status/VERIFICATION_LEDGER.md"
UNKNOWN = "UNKNOWN"
GATES = ("L1", "L2", "L3", "L4", "L5", "L6")

# Branch vocabulary per family, as recorded by the registry / scope resolver (never the contract text):
# ASW scopes are recorded per RANGE_SWEEP branch only (scope_status._ASW_BRANCH); CCFD per direction; LSMC
# records detection vs entry, not a direction.
BRANCHES = {"session_fx_gold": ("RANGE_SWEEP",), "crypto_cfd": ("LONG", "SHORT"), "large_smc": ("ENTRY",)}
# CCFD registry records no weekday/weekend window, so one row covers both config windows.
CCFD_SESSION_LABEL = "ALL_WINDOWS"

# Deterministic next-action owner by (status, reason). Documented, not inferred per row.
NEXT_ACTION = {
    "LOGIC_VERIFIED": "OWNER_DECISION",           # standing DEMO authorization is the owner's call
    "STALE_IDENTITY": "OWNER_DECISION",           # re-record the identity (C20 T2 proposal)
    "SUSPENDED": "ENGINEERING",                   # fix lives in a candidate version (v1.1.3, C20 T3)
    "DIRECTION_NOT_IN_SCOPE": "DATA_INSUFFICIENT",  # branch never exercised on the recorded dataset
    "WINDOW_NOT_IN_SCOPE": "OWNER_DECISION",      # verified record, but no weekday/weekend window recorded
    "ENTRY_LOGIC_NOT_VERIFIED": "ENGINEERING",    # entry/proposal layer has no verification yet
    "LOGIC_NOT_VERIFIED": "ENGINEERING",          # L1-L6 not passed for this scope
}


def sha256_file(rel: Optional[str]) -> Optional[str]:
    if not rel:
        return None
    path = ROOT / rel
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _load_json(rel: str) -> Optional[Dict[str, Any]]:
    path = ROOT / rel
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _asw_gates(evidence: Optional[Dict[str, Any]], symbol: str, session: str) -> Dict[str, str]:
    for cell in (evidence or {}).get("matrix") or []:
        if cell.get("symbol") == symbol and cell.get("session") == session:
            return {g: str((cell.get("gates") or {}).get(g, UNKNOWN)) for g in GATES}
    return {g: UNKNOWN for g in GATES}


def _ccfd_gates(evidence: Optional[Dict[str, Any]], symbol: str, branch: str) -> Dict[str, str]:
    cell = (((evidence or {}).get("logic_verification") or {}).get(symbol) or {}).get("branches", {}).get(branch)
    gates = (cell or {}).get("gates") or {}
    return {g: str(gates.get(g, UNKNOWN)) for g in GATES}


def divergence(status: str, gates: Dict[str, str], reason: str, decision: Any = None) -> str:
    """Compare historical gates with current scope authority without rewriting either."""
    all_pass = all(gates.get(g) == "PASS" for g in GATES)
    if status == "LOGIC_VERIFIED" and not all_pass:
        if isinstance(decision, str) and decision.strip():
            # Registry decisions may include a decision-group prefix (e.g. OD1014-FAST D9).
            return f"OWNER_RESOLVED:{decision.split()[-1]}"
        return "UNRESOLVED_GATE"
    if status == "UNVERIFIED" and all_pass:
        return reason
    return "-"


def lane_version(family: str, symbol: str, session: str, default: str) -> str:
    """Contract version the report lane evaluates for this scope; S1 stays on its canonical v1.1.2 path."""
    if family != "session_fx_gold":
        return default
    import yaml

    from reporting.asw_lane import strategy_path_for
    spec = yaml.safe_load((ROOT / strategy_path_for(symbol, session)).read_text(encoding="utf-8")) or {}
    return str(spec.get("version") or default)


def build() -> Dict[str, Any]:
    from v1_tickets.authority import load_registry, logic_identity
    from v1_tickets.scope_status import FAMILIES, resolve_ticket_scope

    registry = load_registry()
    # 60d L1-L6 matrix per ASW version the report lane runs (v1.1.2 S1 run; v1.1.3 C17 run, OD1014-FAST D9).
    asw_ev_paths = {"1.1.2": "docs/status/AGP_ASW_V112_S1_60D_2026-10-11.json",
                    "1.1.3": "artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_1_1_3/c17_2026-10-13/"
                             "asw_v113_60d_run1.json"}
    asw_ev = {v: _load_json(p) for v, p in asw_ev_paths.items()}
    rows: List[Dict[str, Any]] = []
    for family in sorted(FAMILIES):
        spec = FAMILIES[family]
        sid = spec["strategy_id"]
        entry = registry.get(sid) or {}
        sessions = (CCFD_SESSION_LABEL,) if family == "crypto_cfd" else tuple(spec["sessions"])
        for symbol in spec["pairs"]:
            for session in sessions:
                # The version this scope's report lane actually runs (ASW: per-scope contract, OD1014-FAST D3).
                version = lane_version(family, symbol, session, spec["strategy_version"])
                candidate = (entry.get("candidate_versions") or {}).get(version) or {}
                source = candidate.get("config_source") or entry.get("config_source")
                identity = logic_identity(sid, version)
                for branch in BRANCHES[family]:
                    resolve_session = spec["sessions"][0] if family == "crypto_cfd" else session
                    direction = branch if branch in ("LONG", "SHORT") else None
                    scope = resolve_ticket_scope(sid, version, symbol, resolve_session, direction, registry=registry)
                    status, reason = scope["scope_verification_status"], scope["scope_reason"]
                    evidence_path, recorded_sha, gates = None, None, {g: UNKNOWN for g in GATES}
                    recorded_contract = None
                    gates_source = None
                    if family == "session_fx_gold":
                        # Gates: the committed 60d matrix for this version/identity. Evidence: what the registry
                        # records for this scope (verified or suspended); none recorded -> UNKNOWN.
                        gates_source = asw_ev_paths.get(version)
                        gates = _asw_gates(asw_ev.get(version), symbol, session)
                        for item in candidate.get("logic_verified_scopes") or []:
                            if item.get("symbol") == symbol and item.get("session") == session:
                                evidence_path, recorded_contract = item.get("evidence"), item.get("contract_hash")
                        for item in candidate.get("logic_suspended_scopes") or []:
                            if item.get("symbol") == symbol and item.get("session", session) == session:
                                evidence_path = item.get("evidence")
                    elif family == "crypto_cfd":
                        for item in candidate.get("logic_verified_symbols") or []:
                            if item.get("symbol") == symbol:
                                evidence_path, recorded_sha = item.get("evidence"), item.get("evidence_sha256")
                                recorded_contract = item.get("contract_hash")
                        gates_source = evidence_path
                        gates = _ccfd_gates(_load_json(evidence_path) if evidence_path else None, symbol, branch)
                    else:
                        det = entry.get("detection_logic_verification") or {}
                        parts = str(det.get("identity") or "").split("/")
                        if len(parts) >= 2 and parts[1] == symbol:     # detection-only, one symbol
                            evidence_path = det.get("report")
                    rows.append({
                        "family": family, "strategy": f"{sid}@{version}", "symbol": symbol, "session": session,
                        "branch": branch,
                        "contract_path": source or UNKNOWN,
                        "contract_sha256": sha256_file(source) or UNKNOWN,
                        "contract_hash_recorded": recorded_contract or UNKNOWN,
                        "logic_identity_current": identity["digest"] if identity else UNKNOWN,
                        "logic_identity_recorded": scope.get("verification_identity") or UNKNOWN,
                        "gates": gates,
                        "gates_source": gates_source or UNKNOWN,
                        "registry_status": status,
                        "divergence": divergence(status, gates, reason, candidate.get("registration_decision")),
                        "blocking_finding_id": None if status == "LOGIC_VERIFIED" else reason,
                        "evidence_path": evidence_path or UNKNOWN,
                        "evidence_sha256": sha256_file(evidence_path) or UNKNOWN,
                        "evidence_sha256_recorded": recorded_sha or UNKNOWN,
                        "next_action_owner": NEXT_ACTION.get(status, NEXT_ACTION.get(str(reason).split(":")[0],
                                                                                       UNKNOWN)),
                    })
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["registry_status"]] = counts.get(row["registry_status"], 0) + 1
    return {"schema": "AGP_C20_VERIFICATION_LEDGER_V1",
            "registry_sha256": sha256_file("strategies/registry.yaml"),
            "row_count": len(rows), "status_counts": dict(sorted(counts.items())), "rows": rows}


def render_md(ledger: Dict[str, Any]) -> str:
    out = ["# Verification ledger (AGP-C20 T1)", "",
           "Generated by `scripts/verification_ledger.py` from `strategies/registry.yaml`, the identity code and "
           "committed evidence only; `UNKNOWN` means not recorded. Read-only: no status here grants READY, demo "
           "or live authority.", "",
           f"Registry SHA256 `{ledger['registry_sha256']}`; rows {ledger['row_count']}; status counts "
           + ", ".join(f"{k}={v}" for k, v in ledger["status_counts"].items()) + ".", "",
           "| Strategy | Symbol | Session | Branch | Historical L1-L6 | Current scope status | Divergence | Blocking finding | Next action | "
           "Evidence (sha256 prefix) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in ledger["rows"]:
        gates = " ".join(f"{g}:{r['gates'][g]}" for g in GATES)
        sha = r["evidence_sha256"][:12] if r["evidence_sha256"] != UNKNOWN else UNKNOWN
        out.append(f"| {r['strategy']} | {r['symbol']} | {r['session']} | {r['branch']} | {gates} | "
                   f"{r['registry_status']} | {r['divergence']} | {r['blocking_finding_id'] or '-'} | {r['next_action_owner']} | "
                   f"`{r['evidence_path']}` ({sha}) |")
    out += ["", "Full fields (contract and identity hashes, recorded vs current) are in "
            f"`{JSON_OUT}`.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    ledger = build()
    outputs = {JSON_OUT: json.dumps(ledger, indent=2, sort_keys=True) + "\n", MD_OUT: render_md(ledger)}
    if args.check:
        if any(r["divergence"] == "UNRESOLVED_GATE" for r in ledger["rows"]):
            print("UNRESOLVED_GATE: LOGIC_VERIFIED scope has non-PASS historical gates without a registry decision")
            return 1
        stale = [p for p, text in outputs.items()
                 if not (ROOT / p).is_file() or (ROOT / p).read_text(encoding="utf-8") != text]
        print("STALE: " + ", ".join(stale) if stale else "UP_TO_DATE")
        return 1 if stale else 0
    for p, text in outputs.items():
        (ROOT / p).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / p).write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(ledger["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
