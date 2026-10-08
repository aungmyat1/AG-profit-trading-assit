---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AG Scanner Checklist V1.1 — Implementation Status (2026-10-02)

Authority: Scanner V1 is frozen at commit `d1f23717f07ceb46acb6dde92135a2aeecd0c331`
(tree `e539b2dae2bc81d253b4bd52243bcaefca7bde00`, `origin/main`). Checklist V1.1 is
implemented as a purely additive, read-only, deterministic, fail-closed layer on top of
that frozen base. It grants **no** execution, proposal-promotion, risk, or strategy
authority, and does not modify strategy, risk, or source policy.

## What was built

`src/session_scanner/checklist_v1_1.py` (new) + additive wiring in `scanner.py` and one
additive line in `report.py`. Scanner V1's own outputs (`checklist`, `result`, `reason`,
`proposal`, aggregate gates) are preserved verbatim; regression-pinned by
`test_attach_is_additive_and_scan_level_summary` and the unchanged Scanner V1 suites.

Sequential phase gates (never a score — a mandatory earlier phase failure makes proposal
eligibility impossible regardless of later phases):

| Phase | Consumes / computes | Failure semantics |
|---|---|---|
| 0 DATA | V1 final gates only: canonical `time.time_gate` (no `gate` alias), aggregate data-quality gate, per-instrument gate, quote, series, history retry, closed-bar status, reference-box completeness | `FAIL` → `INSUFFICIENT_DATA`; later phases `NOT_APPLICABLE`; trigger explicitly non-authoritative |
| 1 CONTEXT | canonical session + active cycle; D1/H1 structure via the existing `market_structure` authority; alignment → direction **permission** (`LONG_ALLOWED`/`SHORT_ALLOWED`/`BOTH_ALLOWED`/`NO_DIRECTION`); engine regime; news | no active cycle → `OUT_OF_SESSION`. HTF conflict is observational (`HTF_DIRECTION_CONFLICT`) because the frozen contract defines no HTF veto (required case F) |
| 2 LOCATION | strategy-authorized facts only: reference-session box POI, strict-penetration sweep events (the engine's own predicate), engine-fired setups, H1 swings (observational), PDH/PDL contract gap (observational) | no POI engagement → `LOCATION_NOT_REACHED` → `NO_TRADE` |
| 3 TRIGGER | wraps the frozen strategy engine (`strategy_id`, `strategy_version`, `setup_type`, `signal_*` evidence) | V1 invariants preserved: signal candle not current → `SIGNAL_ENTRY_WINDOW_PASSED` → `NO_TRADE`; TREND without defined timing → `INCOMPLETE_CONTRACT` / `ENTRY_TIMING_NOT_DEFINED_FOR_SETUP` → `BLOCKED`, never invented |
| 4 RISK | release pilot authority (EURUSD/GBPUSD 0.5%); USDJPY/XAUUSD stay `RISK_POLICY_AMBIGUOUS`; engine geometry (entry/SL/positive stop distance); contract targets (`total_target_r 5.0`, legs); no generic min-RR, no 1.0% fallback | ambiguous authority → `BLOCKED` with `setup_valid` preserved `TRUE` |
| 5 PROPOSAL ELIGIBILITY | V1 spread gate on executable broker symbol; proposal authority; V1 ticket presence | `READY_FOR_PROPOSAL ≠ READY_FOR_EXECUTION`; undefined spread policy stays observational (`SPREAD_POLICY_UNDEFINED`, required case G) |

Shared typed vocabulary (`PhaseStatus`, `ChecklistResult`, `StructureState`,
`DirectionPermission`, `ReasonCode` enums — one status model, one reason-code taxonomy,
no free-form status strings). Critical separation is machine-represented:
`setup_valid`, `proposal_eligible`, `execution_authorized` (always `FALSE`) are
independent fields; proposal tickets carry the complete non-executable contract
(section 14 fields, `proposal_status: READY_FOR_PROPOSAL`).

## Economic calendar finding (section 6)

Repository inspection found **no authoritative read-only economic-calendar path**
(searched `src/`, `config/`, `scripts/`, `docs/`). Checklist V1.1 therefore exposes only
the observational marker `NEWS_POLICY_NOT_DEFINED` (`blocking: false`) in Phase 1
evidence. No blackout window was invented; this remains observation-only and cannot
block a proposal.

## Evidence (Linux container, 2026-10-02)

- Scanner V1 regression (frozen suites): `pytest tests/test_session_scanner_v1.py
  tests/test_session_scanner_sources.py tests/test_session_scanner_data_quality_aggregate.py -q`
  → **38 passed** (baseline 38 passed).
- Full suite: `python -m pytest -q` → **846 passed, 4 skipped** (baseline 806 passed,
  4 skipped; +40 new Checklist V1.1 tests).
- `python -m compileall src/session_scanner scripts/run_session_scan.py
  tests/test_session_scanner_checklist_v1_1.py` → **PASS**.
- Static mutation audit: mission's six forbidden broker-mutation names
  (`trade_send_market_order`, `trade_send_pending_order`, `trade_modify_sl_tp`,
  `trade_delete_order`, `trade_close_single_position`, `trade_close_by_position`) and
  generic broker routes (`order_send`, `order_check`, `mt5/management_gateway`,
  `execution.executor/coordinator`) → **0 hits** in `src/session_scanner/` (hits in the
  new test file are the audit regex constants themselves). `MUTATING_TOOLS_EXECUTED=0`,
  `BROKER_ORDERS_SENT=0`, `EXECUTION_AUTHORITY_ADDED=FALSE`.

Required cases A–G are covered by `tests/test_session_scanner_checklist_v1_1.py`,
including an offline integration test driving `_run_source_scan` over a full fake
read-only source for all four instruments (EURUSD/GBPUSD → `READY_FOR_PROPOSAL`;
USDJPY/XAUUSD → `BLOCKED`/`RISK_POLICY_AMBIGUOUS` with `setup_valid=true`).

**LIVE_VALIDATION = DEFERRED_TO_LOCAL_CODEX** (Windows MT5 Demo host); Arena delivered
implementation, fixtures, unit/integration tests, static safety, and publication only.
