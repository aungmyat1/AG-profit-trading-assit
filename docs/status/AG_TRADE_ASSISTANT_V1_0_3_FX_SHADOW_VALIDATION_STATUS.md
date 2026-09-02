# AG_TRADE_ASSISTANT_V1_0_3 -- FX Shadow-Validation Evidence Contract (2026-09-03)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. This is the
INITIALIZATION / EVIDENCE-CONTRACT milestone for the V1.0.3 FX proposal-only
shadow-validation phase. It freezes the day-classification schema and the required
evidence fields; it does **not** start Day 1, does not run any strategy cycle, and does
not generate any proposal.

## Baseline

- `git_head`: `506d8b57469cc8825ecc926e50b67c043d8ba88a` -- **unchanged** from the
  prerequisite `AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE`
  milestone. No drift check beyond confirming identity was needed for any file this
  milestone depends on.
- `branch`: main, `upstream`: origin/main, 0 ahead / 0 behind.
- `working_tree_before`: modified `PROJECT_STATUS.md`, `docs/VERSION_HISTORY.md`,
  `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`; untracked
  `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` and three prior V1.0.3 status
  documents (manifest-freeze, operational-preflight, MT5-closure).
- `relevant_drift`: NO -- `git_head` is byte-identical to the closure milestone's own
  recorded head, so nothing relevant to FX authority, pilot configuration, state/ledger
  code, or execution gates could have changed since that evidence was gathered.
- `unrelated_changes_preserved`: YES -- crypto-execution scaffolding, `scripts/scheduled/`,
  the security status doc, and the (separately, independently updated)
  `ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md` were left untouched by this
  milestone.

## Prerequisite

```text
preflight_status    = PREFLIGHT_PASS_SHADOW_READY (docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md)
MT5_data_readiness   = PASS
shadow_entry_ready   = YES
```

Verified directly against that document's own recorded classification and
`shadow_entry_ready` field -- not merely restated from this task's own prompt.

## FX authority

Verified against `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`
(`status: RELEASE_CANDIDATE`, unchanged) and `strategies/registry.yaml`:

```text
strategy               = ST_ASIAN_SWEEP_5R_V1
version                 = 1.1.1
ASIAN_LONDON_owner      = ST_ASIAN_SWEEP_5R_V1 v1.1.1
LONDON_NEWYORK_owner    = ST_ASIAN_SWEEP_5R_V1 v1.1.1
symbols                  = EURUSD, GBPUSD
runtime_authority        = PROPOSAL_ONLY
```

No semantics, authority, or version were changed by this milestone. `SESSION_TRADE_V1`
was not consulted or referenced (same collision trap disclosed in the two prior V1.0.3
status documents).

## Evidence contract

```text
contract_version       = AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1
validation_series_id   = AG_V1_0_3_FX_SHADOW_SERIES_001
frozen_date             = 2026-09-03
```

Once Day 1 is separately authorized and begins, this contract's definitions are frozen.
A material change to any definition below requires a new `contract_version` and an
explicit decision on whether `AG_V1_0_3_FX_SHADOW_SERIES_001` remains comparable to the
new contract (Reset Policy, below) -- it does not silently redefine the running series.

### Daily evidence unit

`trading_date x cycle x symbol`, four expected units per trading day:

```text
ASIAN_LONDON   / EURUSD
ASIAN_LONDON   / GBPUSD
LONDON_NEWYORK / EURUSD
LONDON_NEWYORK / GBPUSD
```

If a unit is legitimately non-applicable on a given day per authoritative
configuration (e.g. a symbol were ever disabled in `fx_universe`), that must be
recorded explicitly on the daily report, not silently omitted.

### Required per-unit evidence fields

Reused verbatim from the existing, already-implemented reporting/ledger model
(`src/post_asian_pilot/report.py::cycle_to_dict`, `src/post_asian_pilot/governor.py`) --
no competing schema is introduced:

```text
application_release        = result.release_id
strategy_id                 = result.strategy.strategy_id
strategy_version             = result.strategy.version
trading_date                  = result.trading_date
cycle_id                       = pilot_config.pair_id (ASIAN_LONDON | LONDON_NEWYORK)
symbol                          = pr.symbol
reference_session               = pilot_config.reference_session_name (source: config/canonical_sessions.yaml)
evaluation_window                = pilot_config.execution_window_start_utc .. execution_window_end_utc
data_source                       = mt5.market_data.get_candles (M15, per session_clock preflight evidence)
data_completeness                 = derived from pr.decision.reason_codes / missing_condition (DATA_ERROR vs. legitimate NO_TRADE, see Data-Error Contract)
session_snapshot_identity          = journal/<state_dir>/session_snapshot.json key for this trading_date/symbol (immutable once written -- src/post_asian_pilot/store.py)
runtime_start/restart_information  = restart timestamp(s), state read before/after, from the same store
decision_state                      = pr.decision.status (strategy_state)
decision_timestamp                   = pr.decision.ready_at
proposal_id                           = pr.proposal.proposal_id (if any)
setup_id                               = pr.proposal.setup_id (if any) -- the existing duplicate-identity key
ledger claim/result                     = daily_opportunity_ledger.used / max_opportunities, slot state (CLAIMED/EXECUTED/EXPIRED/DECLINED -- governor.py SLOT_STATE_*)
quota_state                              = pilot_config.max_new_trades_per_day / max_new_trades_per_symbol_per_day vs. ledger.slots()
duplicate_status                          = EXPECTED_REPLAY_OR_RESTART_REUSE | UNEXPLAINED_DUPLICATE (see Duplicate Contract)
cross_cycle_contamination_status           = PASS | CONTAMINATED (see Cross-Cycle Isolation)
execution_authority                         = PROPOSAL_ONLY / DISABLED (report.py's EXECUTION_STATUS_DISABLED)
broker_send_reachability                     = BLOCKED (config/trading.yaml gates, unchanged)
errors/warnings                               = pr.decision.reason_codes, pr.decision.missing_condition
terminal_outcome                               = pr.decision.status at end of evaluation window
evidence_classification                         = VALID_DAY | EXCLUDED_DAY | INVALID_DAY | PENDING_RECONCILIATION (unit-level; aggregated to one daily classification per section below)
```

No new ledger, snapshot store, or proposal-identity scheme is created. The daily report
aggregates these existing per-cycle fields (already produced by
`report.py::cycle_to_dict` for each pilot process) across both cycles into one
day-level record plus the day-level classification.

### Day classification definitions (frozen)

```text
VALID_DAY               = every mandatory operational requirement satisfied for all
                            applicable units: runtime environment available, MT5 FX
                            data reachable, EURUSD/GBPUSD data available, required M15
                            timeframe available, session data complete, timestamps/
                            session interpretation valid, all four units evaluated
                            (or explicitly recorded non-applicable), deterministic
                            terminal states recorded, state + ledger persistence
                            completed, duplicate check completed, cross-cycle isolation
                            verified, restart anomalies (if any) reconciled, execution
                            remained unreachable, daily evidence report completed. A
                            proposal is NOT required -- NO_TRADE / WATCH / EXPIRED /
                            BLOCKED are legitimate VALID_DAY terminal outcomes when they
                            are genuine deterministic strategy/runtime results, not
                            infrastructure failures. Never optimized for proposal
                            frequency.
EXCLUDED_DAY             = a pre-existing/external reason prevented the day from fairly
                            testing the frozen runtime (weekend/non-trading day,
                            recognized full market closure, a planned environment
                            outage or intentionally unavailable runtime declared BEFORE
                            the evaluation window, external data-source outage). Does
                            not increment or reset the VALID_DAYS counter. Never used
                            because the strategy lost, produced no setup, produced no
                            proposal, or the observed result was unfavorable.
INVALID_DAY              = correct system operation was expected but cannot be
                            established: mandatory data incomplete, unexplained
                            duplicate, cross-cycle quota contamination, wrong state
                            namespace, corrupted ledger, inconsistent restart
                            reconstruction, missing mandatory evidence, execution
                            unexpectedly reachable, strategy/config drift, unresolved
                            session/timestamp failure. Does not increment the counter.
                            Original evidence is preserved, never rerun or overwritten
                            to obtain a favorable classification.
PENDING_RECONCILIATION   = evidence exists but deterministic classification is not yet
                            possible (apparent duplicate awaiting identity
                            reconciliation, restart with ambiguous persistence
                            evidence, delayed broker/data evidence, ledger/report
                            disagreement). Does not count toward 20 while unresolved
                            and is never auto-converted to VALID_DAY.
```

### Immutable evidence

Reuses the existing immutable-snapshot behavior already implemented and tested for
V1.0.2 (`src/post_asian_pilot/store.py` -- session snapshots fail closed on conflicting
rewrite rather than silently overwriting). Finalized daily evidence records follow the
same rule: a correction is never an in-place overwrite. A correction must preserve
`original_record`, and add `correction_reason`, `corrected_record`, and
`correction_timestamp` as a new, additive, auditable entry. No historical evidence
record belonging to an already-finalized day is ever deleted or replaced in place.

### Duplicate contract

Release requirement: **zero unexplained duplicates.**

Reuses the existing idempotency guarantee already implemented in
`src/post_asian_pilot/store.py` (a repeated write for the same identity returns
`written=False` rather than re-persisting) and the existing `setup_id`/`proposal_id`
identity fields (`src/post_asian_pilot/pipeline.py`, `proposal.py`). A repeated identity
that matches this existing idempotent-write/restart-replay behavior is classified
`EXPECTED_REPLAY_OR_RESTART_REUSE`. A repeated identity that does **not** match this
behavior -- i.e. two distinct ledger claims or two distinct proposal records for what
should be one identity -- is an `UNEXPLAINED_DUPLICATE` and is a release-validation
defect (Defect Policy applies; identity semantics are never changed mid-series merely
to make a duplicate disappear).

### Cross-cycle isolation contract

Release requirement: **zero cross-cycle quota contamination.**

`ASIAN_LONDON` (`journal/post_asian_pilot/`, default `state_dir`) and
`LONDON_NEWYORK` (`journal/post_london_newyork_pilot/`, explicit `state_dir`) are
physically separate `DailyTradeLedger`/snapshot stores -- verified again as unchanged
in this milestone's baseline check (byte-identical `git_head` to the preflight
evidence that already confirmed this). Observed each day: cycle identity, state
namespace, ledger namespace, quota ownership, proposal identity, restart restoration.
If a symbol's slot claim, ledger count, or restart-restored state in one cycle is ever
found to reflect the other cycle's activity, the affected day is `INVALID_DAY` and the
defect is recorded, never silently repaired in the historical record.

### Restart contract

A restart does not automatically invalidate a day. Record: restart timestamp, affected
cycle/symbol, state before restart (where available), reconstructed state, ledger
consistency, decision consistency. If restart recovery preserves frozen behavior
(the existing, already-tested `ready_restart_recovery` capability -- V1.0.2, unchanged
in V1.0.3), the day may remain `VALID_DAY`. Lost state, a duplicate proposal, a wrong
quota, wrong-cycle restoration, or a contradictory decision after restart is classified
`INVALID_DAY` or `PENDING_RECONCILIATION` as appropriate to the evidence available.

### Data-error contract

`DATA_ERROR` is never converted to `NO_TRADE`. `MARKET_HAS_NO_SETUP` (a legitimate
strategy conclusion -- can belong to a `VALID_DAY`) is distinct from
`SYSTEM_COULD_NOT_EVALUATE` (missing mandatory data -- cannot belong to a `VALID_DAY`).
This distinction is already structurally available via `pr.decision.status` /
`missing_condition` / `reason_codes` (`STATUS_DATA_ERROR` already exists as a distinct
decision status in `src/post_asian_pilot/decision.py`, separate from a normal `NO_TRADE`
-equivalent outcome) -- reused, not reinvented.

### Reset / no-reset policy

`RESET` (series superseded, new series starts at `VALID_DAYS = 0/20`) is required when
an authorized fix/change affects what the series is testing: strategy semantics,
session semantics, risk semantics, quota semantics, proposal identity, state isolation,
duplicate behavior, materially decision-affecting restart behavior, data
interpretation, or runtime decision semantics. The superseded series' evidence is
preserved, not deleted.

`NO_RESET` applies to changes proven observational/non-semantic only: documentation,
comments, report formatting, non-semantic logging, status updates, unrelated code, or
tooling that cannot affect runtime decisions.

If comparability is uncertain, the counter is **held**, not guessed at -- resolved as
`PENDING_RECONCILIATION` for the affected day(s) until an explicit decision is made.

## Runtime reuse

```text
existing_shadow_runner   = NONE -- no shadow-day/evidence-classification runtime exists anywhere in the repository as of this git_head (verified: grep across src/, tests/, docs/ for VALIDATION_SERIES/shadow_validation/ShadowDay/VALID_DAY/EXCLUDED_DAY found zero hits outside this milestone's own new document and the two prior V1.0.3 status documents)
existing_scheduler        = NONE -- src/post_asian_pilot has an event-driven --watch mode (V1.0.2 capability) but no persistent multi-day scheduler; not started by this milestone
existing_ledger            = REUSED -- src/post_asian_pilot/governor.py::DailyTradeLedger (unmodified)
existing_daily_report       = REUSED -- src/post_asian_pilot/report.py::cycle_to_dict / human_readable_report (unmodified); this contract aggregates two of these per-cycle reports into one daily evidence record, does not replace them
new_runtime_required          = NO -- this milestone is documentation-only; a future, separately authorized milestone will implement the day-aggregation/scheduling code using these frozen definitions and reused components
reuse_status                    = MAXIMAL -- every evidence field and mechanism above maps onto an existing, already-tested project component; no parallel infrastructure was created
```

## Execution boundary

```text
proposal_only                     = YES (unchanged, config/trading.yaml: mode=ANALYSIS, allow_order_check=false, allow_order_send=false, allow_live_trading=false)
automatic_execution                = DISABLED
FX_live_execution                   = DISABLED
shadow_to_broker_reachability        = BLOCKED
execution_gates_changed               = NO
```

No code was written or executed by this milestone that could reach `order_send`,
`order_check` against a real candidate, or any position mutation. Reused, not
re-verified by a fresh test run, since `git_head` is unchanged from the preflight
milestone that already confirmed this via 30 focused tests.

## Large-SMC / C10

Verified directly against `strategies/ST_LARGE_SMC_V1.yaml` and
`docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md` (read in full for this
milestone, not assumed from the prompt's own restatement):

```text
strategy                          = ST_LARGE_SMC_V1
strategy_version                   = 1.0.6 (unchanged)
authority                           = RESEARCH_DRAFT / RESEARCH_ONLY

structural_anchor_policy             = RESOLVED_BY_REUSE (each M-model's own existing SMCEntryCombinationResult.invalidation_price, EXACT_REUSE, no new detector)
directional_placement                  = RESOLVED (stop below anchor for LONG, above anchor for SHORT)
EURUSD_buffer_unit                      = PIPS
buffer_reference_range                    = 1.0-2.0 pips (a requirements range, not a selected value)
missing_anchor_policy                      = FAIL_CLOSED (never synthesize a substitute anchor)
M_model_reuse                               = REQUIRED across M1/M2/M3, each via its own existing structural invalidation output -- no universal sweep-wick semantics forced onto models that do not use one

exact_buffer                                 = UNSIGNED (1 vs 2 pips -- owner decision C10-D1, not made)
price_domain_spread_policy                    = UNSIGNED (bid/ask/spread treatment for historical replay -- owner decision C10-D2, not made)
broker_minimum_distance_policy                  = UNSIGNED (widen/reject/hybrid -- owner decision C10-D3, not made)

C10_implementation_authorized                    = NO
C10_engine_authority                              = BLOCKED (engine returns BLOCKED, reason_code=UNSIGNED_CONTRACT:C10_BROKER_STOP, for every candidate reaching entry-available state)
```

Classification: `PARTIALLY_RESOLVED_REQUIREMENTS` (the decision packet itself records
this as `REQUIREMENTS_REFERENCE_PARTIAL`) -- explicitly **not**
`SIGNED_IMPLEMENTABLE_CONTRACT`. This milestone did not choose C10-D1, C10-D2, or
C10-D3, did not implement `BrokerStopResult` or a C10 converter, did not modify
M1/M2/M3 invalidation logic or the strategy YAML, and did not run any C10 replay or
optimization. Large-SMC/C10 remain fully independent of the FX shadow-validation
decision path: nothing in the evidence contract above lets Large-SMC create, reject, or
modify an FX shadow proposal, FX risk, or FX stops, and nothing in it affects the
20-day FX counter.

## BTC

Verified against `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s
`btc_market_data_authority` block:

```text
production_data_authority   = BYBIT (FROZEN_BY_OWNER, 2026-09-03); adapter NOT_IMPLEMENTED
observation_authorized       = NO (next milestone: AG_BYBIT_BTC_MARKET_DATA_V1)
observation_started            = NO
execution_authority              = DISABLED / NOT_IMPLEMENTED
```

No Bybit/Binance connectivity probe, no BTC observation, and no BTC evidence collection
was performed or mixed into this FX evidence contract.

## Counters

```text
valid_days       = 0/20
excluded_days    = 0
invalid_days      = 0
pending_days       = 0
```

## Tests

```text
focused_tests          = NONE run by this milestone -- purely documentation; the underlying components (ledger, snapshot store, report, execution-boundary tests) were already exercised (30 passed) by the prerequisite preflight milestone at the same, unchanged git_head, and are reused rather than rerun
full_regression_status  = FULL_REGRESSION_NOT_RERUN -- no .py source file changed
git_diff_check           = clean (only pre-existing CRLF warnings on already-modified files; none newly introduced by this milestone)
```

## Files changed

**THIS_MILESTONE:**
- `docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md` (new, this
  document)
- `PROJECT_STATUS.md` (edited -- one new milestone-level rolling-snapshot line)

**PRE_EXISTING_UNRELATED** (untouched by this milestone):
- `docs/VERSION_HISTORY.md`, `docs/status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md` (already modified
  before this milestone started, by other work)
- `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`, and the three prior V1.0.3 status
  documents (manifest-freeze, operational-preflight, MT5-readiness-closure) -- read for
  evidence, not modified
- `scripts/scheduled/`, all nine `src/execution/crypto_*.py` /
  `tests/test_crypto_*.py` files

## Classification

`SHADOW_EVIDENCE_CONTRACT_READY`

The prerequisite (`PREFLIGHT_PASS_SHADOW_READY`) is confirmed in authoritative
repository evidence at an unchanged `git_head`; the manifest remains
`RELEASE_CANDIDATE`; FX authority and strategy semantics are unchanged; the day-
classification schema, immutability rule, duplicate contract, cross-cycle contract, and
restart contract are all frozen above, each mapped onto existing, already-tested
project components with no new runtime built; shadow-to-broker reachability remains
blocked and execution gates are unchanged; Large-SMC/C10 remain correctly
`PARTIALLY_RESOLVED_REQUIREMENTS` / `UNSIGNED_BLOCKED`, untouched by this milestone;
BTC observation has not started; Day 1 has not started.

## Next authorized step

Begin Day 1 only under a separate explicit authorization to start
AG_TRADE_ASSISTANT_V1_0_3 FX proposal-only shadow collection.
