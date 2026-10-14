---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# C14 VT server-day helper and winter host acceptance

Mission `CODEX-AGP-DST-RESET-R2`, 2026-10-14. Base `8416817f972d4238674742b26c56c2fc9caac98e` (main, contains #224).
Merged main without rebase; the DST add/add conflict retains the shared-helper tests.

Runtime assignment of a VT trading day to a C14 `RiskSnapshot`: **MISSING**.
`src/demo_execution/admission.py:319` consumes a caller-supplied snapshot;
`scripts/host/s1_readonly_acceptance.py:56` passes `None`. No production
`RiskSnapshot(...)` constructor was found in `src/` or `scripts/`.
This does not assert host reconciliation or execution readiness.

`src/demo_execution/server_day.py` provides the shared, unwired helper.
It requires hash-verified committed V2 host metadata for VTMarkets-Demo and the
exact `server_utc_offset_rule`. It reuses the existing
`host_evidence.symbol_metadata` conversion functions. Missing/invalid evidence
returns **BLOCKED** with no day/offset. A derived date is labelled
**DERIVED_NOT_OBSERVED**, never a clock observation. The #224 DST tests call this
helper rather than maintaining their own formula. `risk.py`, execution callers,
reset-basis config, registry, READY and flags are unchanged.

## Host acceptance — pending, doc only

- [ ] After the 2026-11-01 US DST transition, capture an actual VTMarkets-Demo
  server-clock reading paired with an aware UTC reference on the host. Record
  capture UTC, source/method, server identity and observed server-minus-UTC offset.
  Do not infer an observation from a rule-converted UTC timestamp or symbol bars.
- [ ] Confirm the observed winter offset is **+2 hours** and correlate the VT-day
  boundary with **22:00 UTC**. Missing, ambiguous or conflicting evidence leaves
  acceptance pending; retain actual evidence and report the discrepancy.
- [ ] Until that capture is reviewed, winter offset = **DERIVED_NOT_OBSERVED**.
  No live clock, broker or Telegram probe is authorized or performed by this task;
  this checklist changes no execution authorization.

## Validation and reuse

OSS-FIRST: existing C14 risk evaluator **REUSED unchanged**; existing host metadata
hash verifier and NY-rule conversion **WRAPPED**, not reimplemented; stdlib/pytest
for regression cases. No dependency or timezone policy change.

`ruff check src/demo_execution/server_day.py tests/test_demo_execution_dst_reset.py
tests/test_demo_execution_server_day.py` and matching `python -m py_compile`: PASS.
Documentation generators followed by `python scripts/docs/check_drift.py`: zero
blocking errors, four existing allowlist advisories. Untouched generated outputs
are deferred to normal regeneration. Focused tests are NOT_RUN_RESOURCE; exact-head CI must pass before handoff.
The admission regression pairs a valid-snapshot control with a missing snapshot:
`None` must return `RISK_SNAPSHOT_MISSING` and risk gate BLOCKED. Existing
production admission already propagates this block; no runtime fix is needed.
The shared R1 lock is held by C24-R3; no passing local pytest result is claimed.
