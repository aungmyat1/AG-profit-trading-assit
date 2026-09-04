# AG_TRADE_ASSISTANT_V1_0_3 -- Release-Qualification Blockers Status (2026-09-03)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Reconciliation-
only milestone: no strategy, execution, or runtime source code was changed. Documents
the two blockers on V1.0.3's frozen release-qualification program (20/20 FX shadow
days, 30/30 BTC observation days) and defines, without applying, the minimal
remediation for each.

## Baseline

- `git_head`: `fad8ee2df8361f32df765805367b721c3cbd04f7`, branch `main`, 0 ahead/0
  behind `origin/main`.
- `working_tree_before`: modified `PROJECT_STATUS.md` (pre-existing, unrelated);
  untracked `docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md` and
  `..._DAY_002_STATUS.md` (from the prior two milestones this session).
- `relevant_drift`: NONE -- no change to `config/releases/`, `config/pilot/`,
  `strategies/`, or FX/BTC runtime code since the last frozen baseline.
- `unrelated_changes_preserved`: YES -- not touched by this milestone.

## Objective contract (restated, unchanged)

- Daily FX requirement: one deterministic **decision report** per
  cycle x symbol (READY / WATCH / NO_TRADE / DATA_ERROR / BLOCKED / EXPIRED per
  existing vocabulary), not a forced proposal. A zero-proposal day is compatible with
  `VALID_DAY`.
- Daily BTC requirement: same shape, once a production daily-decision runtime exists
  (currently does not).
- `FX_required_valid_days = 20`, `BTC_required_valid_days = 30`.

## PART A -- FX

### FX session-gate verification

Read `config/canonical_sessions.yaml` and `config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`:

```text
asian reference session      = 00:00-06:00 UTC   (config/canonical_sessions.yaml)
ASIAN_LONDON execution window = 07:00-11:00 UTC   (pilot config execution_window)
```

The 2026-09-03 GBPUSD READY result was produced at `10:36:27Z`, from a probe run inside
this window (`07:00-11:00`) and after the Asian reference session had already closed
(`06:00`). **`FX_SESSION_GATE = VERIFIED_CORRECT`** -- `11:00 UTC` is the window
*close*/final-checkpoint time, not the earliest legal evaluation time. No session
semantics were or need to be changed. The proposal itself
(`PROPOSAL-ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-03`, SHORT, entry
1.34942, reason `UPPER_SWEEP_STRICT_PENETRATION`) is preserved as real, non-synthesized
runtime output (`REAL_RUNTIME_OUTPUT=YES`, `SYNTHESIZED=NO`, `EXECUTED=NO`,
`BROKER_MUTATION=NO`) -- not deleted, not treated as a defect.

### FX release-identity blocker (confirmed, not yet remediated)

Traced every reference to the hardcoded release path across the runtime:

```text
src/post_asian_pilot/pilot_config.py:14   DEFAULT_RELEASE_CONFIG_PATH = ".../AG_TRADE_ASSISTANT_V1_0_2.yaml"
src/post_asian_pilot/preflight.py:53      release_path default = ".../AG_TRADE_ASSISTANT_V1_0_2.yaml"
src/post_asian_pilot/preflight.py:80-81   asserts release_id == "AG_TRADE_ASSISTANT_V1_0_2", else FAIL "WRONG_RELEASE_LOADED"
src/post_asian_pilot/report.py:1,202      module docstring + "AG_TRADE_ASSISTANT_V1_0_2_PILOT_END" label
scripts/run_post_asian_pilot.py:1,52,121,127  docstring + 3 literal V1.0.2 CLI output strings
tests/test_post_asian_pilot.py:825,827,859-860,882  5 assertions on the literal string "AG_TRADE_ASSISTANT_V1_0_2"
```

`release_id` is read only as ledger/proposal/report **metadata**
(`governor.py::DailyTradeLedger._load/try_claim`, `report.py`'s rendered fields) -- it
never selects `pilot_path`, `strategy_source_path`, universe, quota, risk, or session
window (those come from the pilot/strategy config files, byte-identical between what
V1.0.2 and V1.0.3 both reference). **`FX_RELEASE_IDENTITY =
PRESENTATION_ONLY_METADATA_DRIFT`** -- confirmed, independently re-derived this
milestone from source, not merely carried over from the prior finding.

**Remediation defined, not applied** (owner chose "define the diff, hold for
go-ahead" when asked this milestone): change `DEFAULT_RELEASE_CONFIG_PATH` (and
`preflight.py`'s default/assertion) to point at
`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`, update the 4 label/docstring sites in
`report.py`/`run_post_asian_pilot.py`, and update the 5 test assertions in
`tests/test_post_asian_pilot.py` to the V1.0.3 string. This is application-version
provenance only -- it does not touch `ST_ASIAN_SWEEP_5R_V1` semantics, sessions, risk,
quota, or execution gates, and the affected files/lines above are the complete surface
(confirmed by grep across `*.py` for the literal string, not a guess).

This was deliberately **not applied** this milestone: it reverses an explicit prior
design decision recorded in the V1.0.3 manifest itself ("this manifest is not wired
into that runtime and does not change its default") and changes the default output of
a script other automation may already depend on
(`scripts/scheduled/run_asian_london_once.bat`) -- a cross-file, test-touching,
default-behavior change judged to warrant explicit confirmation beyond this prompt
alone. `runtime_reported_release` remains `AG_TRADE_ASSISTANT_V1_0_2` pending that
confirmation.

### Day 001 / Day 002 evidence (preserved, not relabeled)

```text
Day 001 (2026-09-02): EXCLUDED_DAY   -- unchanged, not rewritten
Day 002 (2026-09-03): PENDING_RECONCILIATION -- unchanged; includes the 10:30 UTC
                       WATCH/WATCH intermediate evidence and the 10:36 UTC GBPUSD READY
                       proposal, both preserved in
                       docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md
Series_001_status: neither day counts toward 20/20 -- Day 001 is EXCLUDED_DAY by
                    definition, and Day 002's evidence is blocked from counting by the
                    unresolved release-identity gate above (not by its own content).
```

Recommended conservative treatment once the identity gate is resolved one way or the
other: reclassify Day 002 as `NON_COUNTING_HISTORICAL_EVIDENCE` (not deleted) and open a
clean `AG_V1_0_3_FX_SHADOW_SERIES_002` (`valid_days=0/20, excluded_days=0,
invalid_days=0, pending_days=0`) for future collection, once
`runtime_reported_release` actually reads `AG_TRADE_ASSISTANT_V1_0_3`. **Not started
this milestone** -- the first Series 002 operational day requires separate
authorization, per instruction.

`FX_valid_days = 0/20` (unchanged).

## PART B -- BTC

Verified against `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` and existing test
evidence (`tests/test_btc_occurrence_identity.py` -- 8 tests, `deduplication_verified`;
`tests/test_btc_sweep_research_pipeline.py` -- 4 tests; both collect and pass per prior
`AG_COMPLETE_TRADE_OPPORTUNITY_V1` regression evidence, not rerun this milestone --
`FULL_REGRESSION_NOT_RERUN`, no source changed):

```text
BTC_RESEARCH_RUNTIME              = UNIT_TESTED (src/btc_sweep_research/)
BTC_RESEARCH_PROPOSALS            = CONDITIONAL_ON_STRATEGY_QUALIFICATION
                                     (execution_domain=CRYPTO_RESEARCH, execution_authority=DISABLED)
BTC_DAILY_PRODUCTION_DECISION      = NOT_OPERATIONAL -- no daily decision-report runtime
                                     exists yet analogous to src/post_asian_pilot/pipeline.py;
                                     only occurrence-enumeration research code exists
BTC_BYBIT_ADAPTER                 = NOT_IMPLEMENTED (manifest: adapter_status = NOT_IMPLEMENTED,
                                     next milestone AG_BYBIT_BTC_MARKET_DATA_V1)
BTC_OBSERVATION_STARTED           = NO
BTC_OBSERVATION_EVIDENCE          = 0/30
CRYPTO_EXECUTION                  = DISABLED (execution.executor.execute() rejects any
                                     non-TradeCommand object; CryptoExecutionAdapter NOT_IMPLEMENTED)
production_data_authority          = BYBIT (FROZEN_BY_OWNER, 2026-09-03, manifest
                                     btc_market_data_authority block)
current_environment_access          = ENVIRONMENT_BLOCKED (Bybit HTTP 403 country-block,
                                     Binance HTTP 451 -- both recorded prior evidence, not
                                     re-tested this milestone; treated as environment-specific,
                                     not generalized to universal unavailability, and no
                                     bypass attempted)
```

Mock/testnet BTC data remains valid for adapter **unit testing** only
(`testnet_excluded_from_strategy_evidence: true` in the manifest) -- it does not and
will not count toward 30/30 production observation days.

### Bybit scope conflict (classified, not resolved)

The manifest's own `release_qualification_gates.btc.bybit_adapter_implemented: false`
is a **required gate for RELEASED**, but `scope_freeze.new_capabilities_added: false`
and `scope_freeze.invariant` explicitly excludes "new strategy filters... unrelated
architecture redesign" -- and a new exchange market-data adapter is squarely a new
capability, not a defect fix, under that same invariant. The manifest already
anticipated this as `next milestone: AG_BYBIT_BTC_MARKET_DATA_V1`, i.e. a separate,
not-yet-opened unit of work.

**Classification: `QUALIFICATION_REMEDIATION_REQUIRES_OWNER_AUTHORIZATION`.**
Building the Bybit adapter cannot happen inside V1.0.3's own scope freeze as currently
worded; it requires either an explicit owner-authorized scope exception for this
release or owner deferral of BTC gates to a later release. **Not resolved and not
implemented this milestone** -- no Bybit code was written.

`owner_authorization_required = YES`.

### Minimum authorized remediation, if/when the owner opens this scope

Bounded to **read-only market data** only, matching section 21 of the authorizing
prompt: Bybit public/production market-data adapter -> BTCUSDT normalization -> required
timeframe/bars -> timestamps -> closed-bar validation -> data-quality checks -> existing
`ST_LIQUIDITY_SWEEP_RETEST_V1` engine -> daily decision report -> conditional
research/proposal-only output -> immutable observation evidence. Explicitly excludes
order placement, API trading, wallet/withdrawal/deposit operations, position
management, and any execution routing. Not started this milestone.

## PART C -- Execution safety (verified unchanged)

```text
FX_proposal_only            = YES
BTC_proposal_only            = YES (research-only; no production runtime yet to violate this)
automatic_execution            = DISABLED
FX_live_execution                = DISABLED
crypto_execution                    = DISABLED / NOT_IMPLEMENTED
broker_mutation_performed              = NO
exchange_mutation_performed              = NO
```

No `order_send`, no MT5/Bybit/Binance order calls, no execution-gate code touched this
milestone.

## Tests / diff check

```text
FX_focused_tests        = NOT RUN this milestone -- no FX code was changed (remediation
                           held for confirmation); nothing to test yet
BTC_existing_tests_reused = tests/test_btc_occurrence_identity.py,
                            tests/test_btc_sweep_research_pipeline.py -- collected
                            (19 tests total across both), reused prior pass evidence,
                            not rerun (no source change)
full_regression           = FULL_REGRESSION_NOT_RERUN (no .py file changed this milestone)
backtests                  = NOT RUN (out of scope per instruction)
git_diff_check              = clean vs. baseline except the one status doc this
                              milestone adds; PROJECT_STATUS.md unchanged by this
                              milestone (pre-existing mod from before this session untouched)
```

## Files changed

```text
THIS_MILESTONE:            docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md (new, this file)
PRE_EXISTING_UNRELATED:    PROJECT_STATUS.md (modified before this session),
                            docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md,
                            docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md
                            (both from the prior two milestones this session, untouched here)
```

## Release qualification

```text
FX_shadow_evidence      = 0/20
BTC_observation_evidence = 0/30
```

**`RELEASE_QUALIFICATION_BLOCKED`**

## Classification

```text
FX_DAILY_DECISION_RUNTIME     = OPERATIONAL_PROPOSAL_ONLY
FX_RELEASE_ATTRIBUTION          = REMEDIATION_REQUIRED (diff defined, not applied -- owner
                                    chose to hold for explicit go-ahead this milestone)
FX_SESSION_GATE                    = VERIFIED_CORRECT
FX_SHADOW_EVIDENCE                    = 0/20
BTC_RESEARCH_RUNTIME                     = UNIT_TESTED
BTC_DAILY_PRODUCTION_DECISION               = NOT_OPERATIONAL
BTC_BYBIT_ADAPTER                              = NOT_IMPLEMENTED
BTC_PRODUCTION_DATA                               = ENVIRONMENT_BLOCKED
BTC_OBSERVATION_EVIDENCE                             = 0/30
OVERALL_V1_0_3                                          = HOLD
```

## Next-step decision

`FX` identity remains unresolved (remediation defined but not applied) **and** BTC's
Bybit adapter remains blocked by scope, so both remediation paths are pending owner
input. Per instruction, the first is reported as:

**`NEXT = FX_RELEASE_IDENTITY_REMEDIATION`** (owner go-ahead needed to apply the defined
5-file diff), running in parallel with **`OWNER_DECISION_ON_BYBIT_QUALIFICATION_REMEDIATION`**
(owner must decide whether the Bybit adapter is an authorized V1.0.3 qualification
exception or deferred to a later release before `AG_BYBIT_BTC_MARKET_DATA_V1` can
start). Neither next milestone was performed here.

No trading performance result, no daily proposal, and no promotion of V1.0.3 to
`RELEASED` were required or produced by this milestone.
