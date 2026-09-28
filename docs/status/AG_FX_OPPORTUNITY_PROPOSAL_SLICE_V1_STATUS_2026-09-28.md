# AG FX OPPORTUNITY/PROPOSAL SLICE V1 — STATUS (2026-09-28)

## Classification

`AG_FX_OPPORTUNITY_PROPOSAL_RUNTIME_SLICE_V1_READY` — implemented per the
reconciliation plan (WP1 + WP2); **UNAUDITED CANDIDATE** pending independent
audit. Base: `4bbba319` (main, includes PR #10). Candidate branch:
`refs/heads/audit/fx-opportunity-proposal-slice-v1` (one commit).

## What this slice is

The smallest operational FX opportunity/proposal cycle, capability-zero
end to end:

```
read-only MT5 market data (mt5.market_data — copy_rates_* ONLY)
  -> strategy evaluation          (strategy_engine.evaluate, ST_ASIAN_SWEEP_5R_V1)
  -> PostAsianDecision            (post_asian_pilot.decision — pure mapping)
  -> MarketEvent                  (opportunity.events — deterministic BAR_CLOSE, REAL mode)
  -> OpportunityCandidate         (opportunity.engine.evaluate_funnel + asian_sweep_adapter)
  -> ProposalEligibility          (opportunity.proposal_eligibility — hardened, audited, PUBLISHED)
  -> CanonicalProposal + ledger   (proposal_envelope — audited, dedup, atomic persistence)
  -> owner-readable ticket        (proposal_envelope.owner_report — DATA ONLY)
  -> EXIT (one-shot CLI; no scheduler, no execution consumer, no broker mutation)
```

Run:
```
python scripts/run_fx_opportunity_cycle.py \
  --pair ASIAN_LONDON --symbols EURUSD,GBPUSD,USDJPY \
  --as-of 2026-09-23T11:00:00+00:00
```
(LONDON_NEWYORK: `--as-of ...T15:00:00+00:00`.) Reports land in
`reports/fx_cycles/<pair>_<date>/`; state in `state/`.

## Change set (22 files)

**16 restored, blob-exact from frozen lineage `2b75bbf0`** (per the plan's
Phase 5 allowlist; all SOURCE_SHAs verified by `git hash-object` equality):
read-only MT5 data layer (`src/mt5/{market_data,broker_time,connection,config}.py`),
bounded caches (`src/shared_cache/` ×3), funnel bridge
(`src/opportunity/{asian_sweep_adapter,events}.py`), decision contract
(`src/post_asian_pilot/{__init__,decision}.py`), authority data
(`strategies/{registry.yaml,ST_ASIAN_SWEEP_5R_V1.yaml,STRATEGY_LEDGER.md}`),
evidence tests (`tests/{test_opportunity_asian_sweep_adapter,
test_mt5_market_data_guards}.py`).

**6 new (this mission):**
- `scripts/run_fx_opportunity_cycle.py` — the one-shot capability-zero CLI
  (may invoke ONLY market-read/analysis/opportunity/proposal/reporting).
- `src/proposal_envelope/owner_report.py` — owner ticket / no-proposal
  renderer; zero-dependency, renders governance fields as DATA, interprets
  nothing.
- `tests/test_fx_opportunity_cycle_e2e.py` — Phase-8 acceptance: 6 golden
  scenarios (EURUSD/GBPUSD/USDJPY × ASIAN_LONDON/LONDON_NEWYORK) each proving
  data-acquired (read-only call surface recorded), session classified,
  opportunity evaluated (ENTRY_CONFIRMED), eligibility ELIGIBLE, proposal
  recorded (envelope `OPP:ST_ASIAN_SWEEP_5R_V1:…`, execution_authority=NONE,
  proposal_only=True), owner ticket written, full re-run byte-stable
  (ledger + candidate store unchanged, exactly 1 ledger record — dedup),
  and order_send/order_check/positions/deals as AssertionError tripwires
  (BROKER_CALLS=0, order_check=0, order_send=0, Demo=0, Live=0). Plus
  explicit WATCH (session-not-closed) and DATA_ERROR (market-data-missing)
  outcomes — nothing silent, nothing persisted on either.
- `tests/test_fx_slice_import_boundaries.py` — AST containment: no
  execution/authorization/owner_decision/ticket/trade_management/svos/
  entry_confirmation/notifications/strategy_manager/api/proposals/
  scheduler/subprocess/network imports anywhere in the slice;
  MetaTrader5 only inside `src/mt5/*`; no order call sites; the CLI's import
  set is exactly the capability-zero pipeline.
- `tests/test_fx_market_event_construction.py` — deterministic REAL-mode
  event construction (duck-typed snapshot), forming-bar rejection, and the
  REAL `mt5.market_data.get_candles` body driven against a read-only fake
  terminal (UTC round-trip, DATA_MISSING fail-closed).
- this status document.

## Session/window semantics (verified)

- Authority: `config/canonical_sessions.yaml` (on main) — UTC, half-open
  windows, fixed-DST. ASIAN_LONDON = asian 00:00–06:00 reference (canonical
  exact) + 07:00–11:00 trade window (recorded legacy deviation from
  london_am). LONDON_NEWYORK = london_am 06:00–11:00 reference (canonical
  exact) + new_york_am 12:00–15:00 trade window (canonical exact).
- Strategy: ST_ASIAN_SWEEP_5R_V1 (this repo's `strategy_engine`, already on
  main), instruments include all three pairs; registry binding resolved from
  the restored `strategies/registry.yaml`: registered/active →
  opportunity_authority=True, live_observation_supported=True;
  demo_authorized=false, live_authorized=false → execution_authority=NONE.
  (Registry's SESSION_TRADE_V1 `demo_authorized: true` entry is inert
  authority DATA for an engine that lives in a separate repository — no
  dispatcher exists in this repo; restored verbatim, never edited.)
- Eligibility authority: the PUBLISHED, audited, hardened evaluator —
  untouched. Verified compatible with this slice by construction: the frozen
  adapter emits direction/entry/invalidation (targets=() passes — targets are
  not a required input), first-run candidates carry expires_at=None (not
  expired), REAL mode passes the firewall.

## Test evidence (fresh, this tree)

- New suites: 19 passed. Restored suites: 41 passed.
- Full battery: **415 collected = 414 passed + 1 preserved api.app
  negative-control** (the single expected red on main-based trees).
- Web MCP: 5/5 (node --test, explicit file; count grew from 4 with PR #10).
- Golden-path engine proof: all six scenarios yield VALID
  LOWER_SWEEP_STRICT_PENETRATION signals through the REAL strategy engine
  (entry 1.099375 / stop 1.097875 for EURUSD etc. — finite, LONG, stop<entry).

## Known boundaries (recorded honestly)

- **USDJPY**: engine-declared + pipeline-proven (golden E2E passes), but no
  pilot config, dataset config, or broker symbol_map capture exists yet —
  operational enablement on a real terminal is WP3 (owner-gated, new
  evidence-based configuration; not a code change).
- The MT5 boundary requires a Windows terminal; on Linux the existing strict
  conftest placeholder keeps collection green and the E2E drives the REAL
  module bodies against a read-only fake (order APIs are tripwires).
- Forged-data hardening (R0, ledger admission invariant) remains recommended
  BEFORE any future execution consumer; this slice adds no consumer, so it
  remains unblocked (no operational interpretation of authority fields —
  the ticket renders them as text).

## Invariants held

EXECUTION_CAPABILITY = ZERO · BROKER_MUTATION_REACHABLE = NO ·
ORDER_CHECK/ORDER_SEND REACHABLE = NO · OPPORTUNITY/PROPOSAL_TO_EXECUTION_PATH
= NONE · api.app negative-control preserved · no complete-runtime wholesale
restore (16 of 980 candidates, allowlist-exact) · current main wins every
conflict (none of the 16 paths existed on main).

## Next gate

`INDEPENDENT_FX_SLICE_AUDIT` of this candidate, then the owner's publication
decision.
