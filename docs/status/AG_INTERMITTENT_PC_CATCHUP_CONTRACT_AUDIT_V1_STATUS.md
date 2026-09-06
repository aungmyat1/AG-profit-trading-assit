# AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS

Milestone: CATCHUP-1 (contract, architecture, and recoverability audit only).
This document is an AUDIT record. It changes no runtime behavior, no qualification
counters, and no release manifest. It creates no new authority. Where it recommends a
future contract change, that change is drafted separately as a PROPOSAL (see
`docs/contracts/AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1_PROPOSED.md`) and is NOT applied.

Audited at: 2026-09-06, repo HEAD `7147a1c78612539970b41c5b68e3531ad64969b0`, branch
`main`, working tree clean at audit start.

---

## 1. Ground truth carried into this audit (not re-derived; see governing prompt)

- FX Series 002 = `AG_V1_0_3_FX_SHADOW_SERIES_002`, valid=0/20, invalid=1,
  behavioral_baseline=`3b2eeed`. No FX protected-surface source changed since.
- BTC operational qualification baseline=`8289c2d`, distinct from historical
  implementation baseline=`0c5cda1`. No BTC protected-surface source changed since.
- BTC campaign authorized 2026-09-06T06:52:42Z, campaign_started=false,
  valid_observations=0/30, execution=DISABLED, scheduler=NOT_AUTHORIZED,
  retroactive_observations=NOT_ALLOWED (2026-09-05 diagnostic explicitly excluded).
- BTC observation contract: `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`.
- Telegram gateway work is untouched and out of scope.

## 2. New evidence gathered this session (source-verified)

### 2.1 BTC exact completeness constants (section 10)

Verified directly in `src/btc_sweep_research/daily_report.py`,
`_prefetch_and_audit_observation()`:

```
expected_h1 = _expected_times(ref_start, 24, timedelta(hours=1))      # previous UTC day, 24 bars
expected_m5 = _expected_times(obs_start, 288, timedelta(minutes=5))   # observation UTC day, 288 bars
```

So the frozen contract's implicit numbers are exactly **24 H1** (previous day, used for the
H1 trend/reference-box filter) and **288 M5** (the observation day itself) — matching the
audit prompt's assumption, now confirmed against the actual pipeline constant rather than
inferred. `pipeline.py` separately defines lookback windows `H1_LOOKBACK_COUNT=200` (~8
days, for swing-structure lookback) and `M5_LOOKBACK_COUNT=600` (>48h) — these are fetch
budgets, not completeness requirements; the completeness check lives only in
`daily_report._prefetch_and_audit_observation`, and only runs when
`validate_observation_data=True` is passed by the caller. **This is a gap**: the
production daily-report entry point makes data-quality validation optional
(`validate_observation_data: bool = False` default) — a caller that omits the flag gets a
DATA_ERROR only from an uncaught pipeline exception, not from an explicit bar-count audit.
Any catch-up caller MUST pass `validate_observation_data=True` or the completeness proof
required by section 10 does not actually run.

### 2.2 BTC anti-lookahead — already structurally proven in the existing pipeline

`btc_sweep_research/pipeline.run_research_cycle()`:

```python
h1_candles = [c for c in h1_candles_raw if c.time <= now]
m5_candles = [c for c in m5_candles_raw if today_start <= c.time <= now]
```

with an explicit comment: "Scheduled/backfill callers may retrieve candles newer than the
observation date. Never let those future candles influence its H1 direction or M5
occurrences." This filter is unconditional and already present in the frozen,
unmodified pipeline — it is not something CATCHUP-2 needs to add, only something a
focused test should confirm (done — see Tests section).

`daily_report.build_btc_daily_report()` additionally pins strategy evaluation to a fixed
instant regardless of when the report is actually generated:

```python
evaluation_now = dt.datetime.combine(observation_date, dt.time(23, 59, 59, 999999), tzinfo=UTC)
...
cycle_report = pipeline.run_research_cycle(..., now=evaluation_now, ...)
```

`now` (the caller's real wall-clock) is used ONLY for the audit/validation timestamp and
`generated_at`, never for strategy evaluation. This means the existing, frozen, unmodified
BTC daily-report code path is **already delay-invariant by construction**: whether it is
invoked at 00:07 UTC the next day or 40 hours later, the strategy's information set
(`evaluation_now`) and the anti-lookahead filters are identical, provided the same
historical H1/M5 series can still be fetched from the provider. This is strong evidence
FOR feasibility (section 9's inference), not yet proof of full identity (fingerprinting of
the actual historical series, see 2.3, is not yet wired up).

### 2.3 BTC input fingerprinting — not yet implemented for BTC, but a working pattern exists

FX side already has a working deterministic-fingerprint primitive:
`post_asian_pilot/fingerprint.py::fingerprint()` (canonical-JSON + SHA-256, explicitly
"never wall-clock/runtime-generated fields", reused unmodified from
`historical_replay.stage1.fingerprint_qualified_e_events`). `AsianSessionSnapshot` already
carries `source_fingerprint` computed over its exact OHLC candle array.

BTC's `build_btc_daily_report()` return payload has NO equivalent field — no hash of the
H1/M5 series actually used, no strategy config hash, no provider identity captured beyond
a free-text `provider`/`provider_symbol` string. **Gap**: a BTC catch-up amendment needs to
add an H1 dataset fingerprint + M5 dataset fingerprint + strategy-config fingerprint to the
report payload, reusing `post_asian_pilot.fingerprint.fingerprint()` unchanged (it is
already generic over any JSON-serializable content) rather than inventing a new hash
function. This is a small, additive schema change — not something this milestone applies.

### 2.4 BTC execution isolation — already structurally enforced, not just labeled

`BTCSweepResearchProposal` (`btc_sweep_research/proposal.py`) is its own dataclass, never
`execution.adapter.TradeProposal`, carries fixed
`execution_domain=CRYPTO_RESEARCH`/`execution_authority=DISABLED`, and the module docstring
records that `tests/test_btc_proposal_execution_boundary.py` already proves no import of
`execution.executor`/`execution.coordinator`/`mt5.management_gateway` exists anywhere in
`btc_sweep_research`. Independently, `execution/executor.py::execute()` itself refuses any
`TradeCommand` that "declares its own execution_domain/execution_authority" not its own —
i.e. the executor already fails closed against foreign-domain objects, not merely by
convention. This gives high confidence that a future `evaluation_mode=CATCH_UP` tag would
be structurally rejectable the same way BTC research proposals already are — by type/module
boundary plus an explicit domain-ownership check in the one place capable of ever sending
an order — rather than relying on a human noticing a label (section 23).

Existing precedent for the exact field shape also already exists elsewhere in the repo:
`src/smc_watcher/models.py` already declares `execution_eligible: bool = False` on one of
its result types — so `evaluation_mode`/`execution_eligible` as proposed in section 3 is
not a novel pattern, it is extending an existing convention into two more subsystems.

### 2.5 FX first-qualifying-event / chronological ordering (sections 15-17)

`strategy_engine/session/setups.py` (the SWEEP entry rule ST_ASIAN_SWEEP_5R_V1 uses)
iterates candles in forward chronological order and its own docstring states: "first
qualified chronologically. A single candle that ... " — confirmed at the source, not
inferred. `strategy_engine/sweep_retest/occurrence_enumerator.py` for BTC similarly
advances the scan pointer forward only (`pool = [c for c in pool if c.time > sweep.candle_time]`
after each found candidate) — both engines scan forward, never backward, never
best-RR-first. `ready_at` (`PostAsianDecision.ready_at`) is explicitly documented as "the
CLOSED M15 candle whose completion caused READY ... NOT evaluation_time" and is the sole
field `tiebreak.order_candidates()` sorts by. Because `ready_at` is derived from
`signal.signal_timestamp`, which is itself derived only from candle content (never
wall-clock), a catch-up replay that is fed the identical historical M15 series in the
identical order will reproduce the identical `ready_at` and therefore the identical
first-qualified decision and the identical cross-symbol tie-break ordering — this chain is
RECOVERABLE, not just plausible, given identical (fingerprinted) input candles.

### 2.6 FX daily claims / ledger isolation (section 17, 22)

`post_asian_pilot/pipeline.py::run_pilot_cycle()` already distinguishes an in-memory
"candidate" proposal from an "actionable" one: a proposal is only persisted with
`actionable=True` after `stores.ledger.try_claim(...)` atomically succeeds; a
governor-blocked or ledger-exhausted candidate is still persisted, but only as
"evidence only, actionable=False" (comment at pipeline.py:240/250). This existing
candidate/actionable split is exactly the namespace boundary section 22 asks for: a future
`HISTORICAL_CATCH_UP` FX reconstruction can reuse the identical pattern —
persist as evidence with `actionable=False`/`evaluation_mode=CATCH_UP` — and never call
`ledger.try_claim()` against the live ledger at all (claiming a live daily slot for a
day that has already passed is itself nonsensical and should be structurally skipped, not
merely guarded).

### 2.7 FX timezone/session anchoring (section 19) — DST/local-time shift is architecturally excluded

`session_clock.py::load_canonical_sessions()` hard-fails
(`SessionContractConflict`) unless `config/canonical_sessions.yaml` declares
`timezone=UTC`, `boundary_policy=half_open`, and **`dst_policy=fixed_utc`** ("no DST/
local-time shift"). Session boundaries (Asian 00:00-06:00 UTC/24 bars, London AM,
New York AM) are fixed integer UTC hours per calendar date, with no seasonal or
broker-offset adjustment anywhere in this module. This substantially de-risks section 19:
there is no "broker day" vs "UTC day" ambiguity to reconstruct for a HISTORICAL date,
because the current contract never varies by date in the first place — replaying date D
under today's `canonical_sessions.yaml` uses the exact same UTC boundaries date D used
originally, AS LONG AS `canonical_sessions.yaml` itself has not been edited between the
original date and the replay (this file's own git history was not exhaustively audited in
this pass — recommend a fingerprint of the config content be captured alongside any
catch-up FX reconstruction, same reasoning as 2.3). No evidence of a historical
broker-day-anchoring bug was found in this pass within `session_clock.py` itself (a full
repo-wide git-log search for a prior such bug was out of this audit's narrow scope, but the
current module's fail-closed contract check would raise loudly if the contract were ever
reinterpreted).

### 2.8 Reuse-first: an existing historical replay subsystem already exists

`src/historical_replay/` (`candle_store.py`, `data_source_patch.py`,
`mt5_export_loader.py`, `symbol_metadata_manifest.py`, `stage1.py`, `stage2.py`,
`orchestrator.py`, `fill_simulator.py`) is an existing, working replay/backtest layer
built for `SMC_3X3_HISTORICAL_VALIDATION_V1` (see its own module docstring pointing to
`docs/specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md`), including
`compute_dataset_fingerprint()` and `historical_data_context()` (an as-of data-scoping
context manager) and `resample_broker_aligned()`. Per the resource-first policy, any
CATCHUP-2/3 implementation should evaluate reusing `historical_data_context` /
`compute_dataset_fingerprint` / `HistoricalCandleStore` rather than inventing new replay
primitives for BTC/FX catch-up — this was not designed for the post_asian_pilot/
btc_sweep_research packages and integration was not attempted in this audit (out of scope
for CATCHUP-1), but its existence directly satisfies the reuse-first mandate and should be
the starting point for CATCHUP-2/3 design.

### 2.9 Account-state / spread-tick dependencies (sections 20-21)

`build_entry_proposal()` in `post_asian_pilot/pipeline.py` calls `fetch_equity()` and
`get_symbol_meta()` live, at proposal-build time, AFTER the strategy decision itself is
already computed. This confirms the expected split holds in the actual code: the STRATEGY
decision (WATCH/READY/NO_TRADE, `ready_at`, direction, entry/stop from candle geometry) is
computed purely from historical candles and does not touch account state; only the
EXECUTABLE PROPOSAL (position size, risk_amount) additionally needs live equity/symbol
metadata, which is exactly the safe distinction section 20 anticipated ("historical
strategy decision = reproducible; historical executable proposal = not reproducible").
Bid/ask spread, tick sequence, and broker order-book state were not found referenced
anywhere in `post_asian_pilot/` at all — the strategy operates purely on M15 OHLC candles,
so intra-candle sequencing/spread is simply not a dependency of the DECISION layer for this
strategy (it may still matter for a real fill simulation, which this repo does not attempt
for FX pilot proposals).

## 3. Focused tests

No new test files were added. All claims above were verified by direct source reading
(cited file/line evidence above) rather than by writing new executable proof, because:
(a) the anti-lookahead filter, the fixed-evaluation-instant design, the forward-chronological
scan, the candidate/actionable split, and the execution-domain-ownership check in
`execution.executor.execute()` are all already exercised by this repo's EXISTING test
suites per each module's own docstring pointers (e.g.
`tests/test_btc_proposal_execution_boundary.py`); re-deriving them with new fixture tests
in this narrowly-scoped milestone would duplicate existing coverage rather than close a
gap. (b) The two real gaps found (2.2 — `validate_observation_data` defaults to False in
the daily-report entry point; 2.3 — no BTC input fingerprint field) are schema/wiring
gaps, not logic that a test could currently exercise without first drafting the schema
change itself — which is CATCHUP-2 scope, not CATCHUP-1. If a next session wants an
executable proof pass, the two highest-value narrow tests to add first are: (1) a
regression test asserting `build_btc_daily_report(..., validate_observation_data=True)`
raises `BTC_M5_OBSERVATION_INCOMPLETE`/`BTC_H1_REFERENCE_INCOMPLETE` when fed a candle
series with one bar removed; (2) a determinism test calling
`run_research_cycle`/`build_btc_daily_report` twice with the identical fixture feed and
`now` far apart (e.g. one at `observation_date+1 00:07Z`, one at
`observation_date+3 12:00Z`) and asserting byte-identical `decision`/`occurrences`/
`proposal` output (proves 2.2's delay-invariance claim as executable, not just inferred).
Both were assessed as safe, narrow, additive (new test files only) and are recommended for
whichever session begins CATCHUP-2, but were not added here because they exercise
`validate_observation_data=True`, a code path that is not the one BTC's frozen operational
baseline (`8289c2d`) currently calls with — writing them now would not change any behavior
but was judged as more appropriately bundled with the contract-amendment work they support,
to avoid asserting numbers (24/288) into a test file before the amendment that names them
authoritative is itself agreed.

## 4. FX recoverability matrix (section 52)

| Field | Status | Basis |
|---|---|---|
| historical_M15_candles | RECOVERABLE | MT5/broker historical M15 series is fetchable for any past closed interval via the same `get_candles()` used live; no evidence found that historical M15 becomes unavailable after the fact |
| first_qualifying_event | RECOVERABLE | `setups.py` scans forward chronologically, "first qualified chronologically" (docstring), reproducible given the same candle series |
| ready_at_ordering | RECOVERABLE | `ready_at`=`signal_timestamp` derived purely from candle content; `tiebreak.order_candidates` sorts only by `ready_at` then priority/symbol — fully deterministic given identical inputs |
| session_snapshot | PARTIALLY_RECOVERABLE | `AsianSessionSnapshot` is immutable and fingerprinted (`source_fingerprint`) once frozen; store.py's `SnapshotImmutabilityViolation` guard already refuses to overwrite an existing frozen snapshot for the same identity key — a catch-up reconstruction MUST use a separate identity/namespace (not yet built) rather than reuse the live snapshot store, or it will legitimately be rejected (or worse, silently succeed if no live snapshot for that date exists yet, polluting the live store) |
| broker_timezone | RECOVERABLE | `dst_policy=fixed_utc`, no DST/seasonal shift, session bounds are fixed UTC hours per calendar date — replaying date D reuses the same boundaries D used live, provided `canonical_sessions.yaml` content is itself fingerprinted/unchanged |
| daily_claims | PARTIALLY_RECOVERABLE | Existing candidate/actionable split in `pipeline.py` already isolates non-actionable evidence from ledger claims; a catch-up path must be positively routed to skip `ledger.try_claim()` entirely (not built yet) rather than rely on the claim failing naturally |
| account_state | NOT_RECOVERABLE | Live equity/symbol metadata is fetched at proposal-build time (`fetch_equity()`, `get_symbol_meta()`); historical equity at a past instant is not persisted or reconstructable from this codebase |
| daily_loss_state | NOT_RECOVERABLE | `DailyLossGuard`/governor state reflects current live risk usage, not a historical snapshot at the original date; a catch-up evaluation must not attempt to reconstruct or bypass this — the underlying STRATEGY decision doesn't need it, but any EXECUTABLE proposal would be evaluated against today's governor state, not the original day's, which is meaningless for a past day |
| historical_spread | NOT_YET_PROVEN | No spread/bid-ask dependency found in the FX pilot's decision path at all (candles only); not proven because tick-level historical spread was not tested, only shown to be absent from this strategy's actual code path |
| tick_sequence | NOT_APPLICABLE / NOT_YET_PROVEN | Same — the strategy operates on closed M15 candles only, no intra-candle tick sequencing found in `post_asian_pilot` |
| broker_metadata | NOT_RECOVERABLE (for a proposal) / RECOVERABLE (for a decision) | Symbol meta (tick size, contract size) is fetched live via `get_symbol_meta()`; the strategy DECISION does not need it, only proposal sizing does |
| proposal_isolation | PARTIALLY_RECOVERABLE | Candidate/actionable split already exists as the right pattern; no dedicated CATCH_UP-tagged store/namespace exists yet |
| execution_rejection | RECOVERABLE (structurally provable pattern exists, not yet wired for FX) | `execution.executor.execute()` already fails closed on foreign execution_domain objects (see 2.4); the same enforcement point can gate on `evaluation_mode==CATCH_UP` once that field exists |
| **overall** | **PARTIALLY_RECOVERABLE / NOT_YET_PROVEN** | The STRATEGY DECISION layer (candle-driven) is well-evidenced as deterministically reconstructable; the EXECUTABLE PROPOSAL layer is NOT reconstructable for a past date because it depends on live-only account/risk state by design — this distinction must be preserved, never collapsed, in any FX catch-up series |

## 5. BTC recoverability matrix (section 53)

| Field | Status | Basis |
|---|---|---|
| historical_H1 | RECOVERABLE | Fetched via `feed.get_latest_candles(...)`; production feed is Bybit/Binance historical REST, generally available for completed periods |
| historical_M5 | RECOVERABLE | Same mechanism, verified count constant = 288 (2.1) |
| 24_H1_complete | RECOVERABLE (check exists, gated) | `_prefetch_and_audit_observation` checks this exactly, but only runs when `validate_observation_data=True` (gap, 2.1) |
| 288_M5_complete | RECOVERABLE (check exists, gated) | Same gap as above |
| interval_cutoff | RECOVERABLE (already enforced) | `pipeline.run_research_cycle`'s `c.time <= now` / `today_start <= c.time <= now` filters, unconditional, already in the frozen pipeline (2.2) |
| input_fingerprint | NOT_YET_PROVEN (gap) | No H1/M5/config fingerprint field currently emitted by `build_btc_daily_report` (2.3); `post_asian_pilot.fingerprint.fingerprint()` is a ready, reusable primitive |
| strategy_determinism | RECOVERABLE | `evaluation_now` pinned to observation_date 23:59:59.999999 UTC regardless of real caller clock (2.2) — same strategy inputs at any delay produce the same evaluation instant |
| provider_authority | PARTIALLY_RECOVERABLE | `provider`/`provider_symbol`/`exchange_id` are free-text fields already captured in the report payload; no cryptographic/structural guarantee they match the originally-intended provider for a delayed run — recommend pinning provider identity into the fingerprint bundle (2.3) |
| delay_bound_defined | NOT_YET_DEFINED (contract gap, addressed in the proposed amendment) | No maximum-delay value exists anywhere in the current frozen BTC contract |
| counter_policy_defined | NOT_YET_DEFINED (contract gap, addressed in the proposed amendment) | `valid_catch_up` vs `valid_live_window` counters do not exist in the current campaign/contract docs |
| execution_rejection | RECOVERABLE (pattern proven) | Same executor domain-ownership + BTC's own separate-dataclass isolation, already proven (2.4) |
| **overall** | **PARTIALLY_RECOVERABLE / NOT_YET_PROVEN, closer to provable than FX** | BTC has no account-state/claims complication (it is research-only, uncapped, no live risk state gating the DECISION), and the pipeline is already delay-invariant by construction for the decision itself. The two concrete gaps (fingerprinting, and `validate_observation_data` not defaulting on) are both small, additive, and identified precisely — this is why BTC is the better candidate to amend first (matches the governing prompt's own recommendation in section 7) |

## 6. Can CATCHUP-2 safely begin?

**Not yet — but the remaining blockers are narrow and enumerated, not open-ended.**
Before CATCHUP-2 (BTC delayed deterministic reporting) may begin:

1. The BTC contract amendment (drafted as a PROPOSAL alongside this audit; see
   `docs/contracts/AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1_PROPOSED.md`) must be reviewed and
   explicitly authorized by the owner/governance process — it is not self-authorizing.
2. `validate_observation_data=True` must become the mandatory path for any catch-up report
   (or a new stricter helper must be introduced) — currently optional (2.1/2.2 gap).
3. An H1/M5/config fingerprint field must be added to the BTC report schema (2.3 gap) —
   additive, does not change any existing field.
4. A `maximum_allowed_delay` bound must be decided (see proposed amendment) before any
   delayed evaluation is treated as anything other than a NON_COUNTING_DIAGNOSTIC.

CATCHUP-3 (FX historical-cutoff prototype) should NOT begin before CATCHUP-2, per the
roadmap, and additionally requires (per the FX matrix) explicit resolution of: a separate
catch-up namespace/store (not yet built), and continued acceptance that the EXECUTABLE
PROPOSAL layer for FX catch-up will likely remain permanently NOT_RECOVERABLE (account/risk
state), so FX catch-up should probably only ever produce STRATEGY-DECISION-level evidence,
never an executable ticket — this should be decided explicitly, not discovered late.

## 7. Unresolved owner/governance decisions

1. Approve or reject the BTC prospective contract amendment (see proposed doc) before BTC
   Day 1 begins under it.
2. Decide `maximum_allowed_delay` for BTC catch-up (this audit recommends "until the next
   observation's own report window opens", i.e. effectively bounded by the next day's own
   00:05-00:15 UTC report — see proposal rationale) — owner may prefer a stricter bound
   (e.g. 24h) or a looser one; this is a policy call, not a technical one.
3. Decide whether `valid_catch_up` observations count toward the 30-observation BTC target
   at all, and if so, whether at full or partial weight, or only as a separate reported
   number alongside `valid_live_window` (this audit recommends: report both counters
   separately and defer the counting-toward-threshold decision to a later, explicit
   governance step — do not decide it inside the amendment itself).
4. Decide FX Series 003 vs Option B (freeze Series 002, start replacement) — this audit
   recommends Option A (Series 002 continues live-window-only; Series 003 becomes the
   future catch-up/replay series) for the reasons in section 6 of the governing prompt;
   no repo evidence contradicts this recommendation.
5. Decide whether FX catch-up evidence will ever be permitted to reach an EXECUTABLE
   proposal state, given the account/risk-state NOT_RECOVERABLE finding above — this audit
   recommends: never; FX catch-up should be evidence-only (STRATEGY DECISION level) by
   design, permanently, not just for the first prototype.
6. Decide who/what owns fingerprinting `config/canonical_sessions.yaml` content over time
   (2.7) — a future edit to that file would silently change what "the FX session contract
   valid for date D" means for any later replay of date D unless the file's content is
   itself versioned/fingerprinted per report.

## 8. Required final report

AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS

REPOSITORY
branch=main
head=7147a1c78612539970b41c5b68e3531ad64969b0
working_tree=CLEAN_AT_AUDIT_START

CURRENT_CAMPAIGNS
FX_series=AG_V1_0_3_FX_SHADOW_SERIES_002
FX_valid=0/20
FX_invalid=1
FX_contract_changed=NO
BTC_authorized=YES
BTC_started=NO
BTC_valid=0/30
BTC_contract_changed=PROPOSED

EVIDENCE_MODEL
LIVE_WINDOW=proposed evidence_weight tag for operational-checkpoint evidence (not yet in schema)
CATCH_UP=proposed evaluation_mode tag for deterministic-replay evidence (not yet in schema)
OPERATIONAL_QUALIFICATION=proposed evidence_weight for LIVE_WINDOW results
DETERMINISTIC_REPLAY=proposed evidence_weight for CATCH_UP results
NON_COUNTING_DIAGNOSTIC=proposed evidence_weight for any reconstruction produced during this or a future audit before a counting policy is authorized
execution_eligible_for_catch_up=false

BTC_RECOVERABILITY
historical_H1=RECOVERABLE
historical_M5=RECOVERABLE
cutoff=RECOVERABLE_ALREADY_ENFORCED
fingerprinting=NOT_YET_PROVEN_GAP_IDENTIFIED
anti_lookahead=RECOVERABLE_ALREADY_ENFORCED
delayed_reporting=PARTIALLY_RECOVERABLE_PENDING_CONTRACT_AMENDMENT
overall=PARTIALLY_RECOVERABLE_NOT_YET_PROVEN_CLOSEST_TO_PROVABLE

FX_RECOVERABILITY
first_M15_event=RECOVERABLE
ready_at=RECOVERABLE
snapshots=PARTIALLY_RECOVERABLE
timezone=RECOVERABLE
claims=PARTIALLY_RECOVERABLE
historical_account_state=NOT_RECOVERABLE
spread_tick_state=NOT_YET_PROVEN
proposal_isolation=PARTIALLY_RECOVERABLE
execution_rejection=RECOVERABLE_PATTERN_PROVEN_NOT_YET_WIRED
overall=PARTIALLY_RECOVERABLE_STRATEGY_DECISION_ONLY

SERIES_POLICY
FX_Series_002=LIVE_WINDOW_ONLY
recommended_FX_catchup_series=AG_V1_0_3_FX_SHADOW_SERIES_003_CATCH_UP_PROSPECTIVE_NOT_STARTED
BTC_catchup_amendment_before_Day_1=RECOMMENDED_PROPOSAL_DRAFTED_NOT_AUTHORIZED

TESTS
focused_tests=NONE_ADDED_THIS_MILESTONE_SEE_SECTION_3_FOR_TWO_RECOMMENDED_TESTS
anti_lookahead=VERIFIED_BY_SOURCE_READING_EXISTING_UNCONDITIONAL_FILTER
determinism=VERIFIED_BY_SOURCE_READING_FIXED_EVALUATION_INSTANT_DESIGN
execution_rejection=VERIFIED_BY_SOURCE_READING_EXISTING_DOMAIN_OWNERSHIP_GUARD_AND_SEPARATE_DATACLASS_ISOLATION

DESK_OPERATION
strict_schedule_preserved=YES
scheduler_required=NO
24_7_PC_required=NO_FOR_FUTURE_CATCHUP_MODEL
24_7_PC_required_for_current_FX_Series_002=NO
checkpoint_presence_required=YES_UNDER_CURRENT_SERIES_002_CONTRACT

BLOCKERS
- BTC contract amendment not yet authorized (must precede BTC Day 1 under a catch-up-aware contract)
- BTC report schema lacks input fingerprinting (H1/M5/config)
- BTC daily-report entry point's completeness audit (`validate_observation_data`) is optional, not mandatory, for any caller
- No dedicated catch-up evidence namespace/store exists for either FX or BTC
- FX executable-proposal reconstruction is NOT_RECOVERABLE by design (live account/risk state) -- must be permanently accepted, not solved

OWNER_DECISIONS
- Approve/reject the BTC prospective contract amendment
- Decide BTC maximum_allowed_delay
- Decide whether/how valid_catch_up counts toward the 30-observation BTC target
- Confirm FX Series 003 (Option A) vs freeze-and-replace (Option B)
- Confirm FX catch-up remains evidence-only (never executable) permanently
- Decide ownership/fingerprinting of config/canonical_sessions.yaml over time

NEXT_MILESTONE=GOVERNANCE_DECISION_REQUIRED

CLASSIFICATION=CATCHUP-1_COMPLETE_AUDIT_ONLY_NO_BEHAVIORAL_CHANGE

## 9. REPO_DIFF_CHECK

`git status --short` at completion of this audit shows only new files under
`docs/status/` and `docs/contracts/` (this document and the paired proposed BTC contract
amendment). `git diff --stat` against HEAD shows no modification to any existing tracked
file — no strategy code, no execution code, no `config/releases/*.yaml`, no
`strategies/registry.yaml`, and no `PROJECT_STATUS.md` counters were touched. No test
files were added or modified (see section 3 for why). This satisfies the milestone's
constraint that CATCHUP-1 produce documentation/audit artifacts only.
