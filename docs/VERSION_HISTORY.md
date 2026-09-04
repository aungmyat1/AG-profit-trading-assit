# AG Profit Trading — Version History

## Current Capability and Upgrade Report (2026-09-03)

This report describes the Trade Assistant as source/runtime software. Windows desktop
packaging is outside the current scope. `IMPLEMENTED`, `VERIFIED`, and `ENABLED` remain
separate states: implemented code is not automatically authorized to trade.

### Application versions and usable capabilities

| Application version | Release state | Capabilities that can be used | Important limits |
|---|---|---|---|
| `AG_TRADE_ASSISTANT_V1_0` | FROZEN | Proposal-only post-Asian/London evaluation for EURUSD and GBPUSD. | Original single-slot pilot; no execution wiring. |
| `AG_TRADE_ASSISTANT_V1_0_1` | IMPLEMENTED | Two independent daily FX opportunity slots, one per symbol; deterministic selection, risk limits, atomic ledger claims and portfolio guards. | Asian/London cycle only. |
| `AG_TRADE_ASSISTANT_V1_0_2` | CURRENT DOCUMENTED RELEASE | Restart recovery, immutable session snapshots, preflight checks, event-driven watch mode, complete entry-ticket rendering, end-of-window reporting and monitoring counters. | Proposal runtime remains separate from broker execution. |
| `AG_TRADE_ASSISTANT_V1_0_3` | RELEASE CANDIDATE — manifest frozen | Everything in V1.0.2 plus the proposal-only London/New York FX pilot; BTCUSDT Binance USDT-M research data/runtime; multi-occurrence BTC research ledger; explicit qualification-versus-tradability reporting; Large-SMC historical metadata decoupling and corrected replay baseline; hardened rejection of research proposals by the FX executor; read-only MT5-demo and Binance Futures Testnet discovery evidence; a combined FX daily decision report/append-only archive; the already-existing complete Entry Ticket renderer (unchanged, carried over from V1.0.2) now wired into per-cycle `--once`/`--status`/`--watch` operational output for any READY proposal, informational only (execution remains disabled) — reporting/output wiring, not a new strategy, execution, or broker capability. | Manifest frozen at `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`; release qualification (shadow/observation evidence) is still pending, so status remains RELEASE CANDIDATE, not RELEASED. New York FX is unit-tested but not yet shadow-validated. BTC is research/proposal-only; production market-data authority is owner-frozen as Bybit (2026-09-03), adapter not yet implemented, environment-blocked (HTTP 403) same as Binance (HTTP 451) from this development environment. Crypto execution is not implemented. Large-SMC C10 conceptual stop model owner-frozen as AG_NATIVE_INVALIDATION (2026-09-03); implementation still pending, engine unchanged. Credential rotation for Binance/MEXC/Bybit is owner-confirmed complete; withdrawal permission is owner-confirmed restricted (2026-09-03); IP-restriction status remains unresolved. Operational preflight closed 2026-09-03: `PREFLIGHT_PASS_SHADOW_READY`. The initial run that same day returned `HOLD` — every configuration/isolation/execution-boundary check passed, but live MT5 market-data connectivity could not be verified from that development environment ("No IPC connection") — see `docs/status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md` (preserved as historically accurate for that environment). Re-run from the intended operator environment (connected MT5 terminal, confirmed demo account) closed the blocker: EURUSD/GBPUSD both resolve with exchange-verified metadata and well-formed recent closed M15 bars (the pipeline's only required timeframe), session/clock contract validates, no broker mutation performed — see `docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md`. Shadow-day/observation-day collection has not started; release remains RELEASE CANDIDATE. |

The recommended next documentation-only release action is to formalize
`AG_TRADE_ASSISTANT_V1_0_3` from the current tested source baseline. This assignment
does not change a strategy version, enable an order gate, or authorize trading.

### What is usable now

| Feature | Implementation | Verification | Enabled/authority |
|---|---|---|---|
| Market analysis and explicit decision states | IMPLEMENTED | Regression-tested | AVAILABLE |
| Asian/London EURUSD+GBPUSD proposals | IMPLEMENTED | Runtime evidence exists | PROPOSAL_ONLY |
| London/New York EURUSD+GBPUSD proposals | IMPLEMENTED | Unit-tested | PROPOSAL_ONLY; shadow validation pending |
| MT5 demo open/close execution | IMPLEMENTED | Prior demo evidence exists | Disabled by default; every send requires a fresh explicit user command |
| MT5 live/real execution | IMPLEMENTED behind gates | Not authorized as a live service | DISABLED |
| BTCUSDT market-data adapter | IMPLEMENTED | Offline tests plus Binance Futures Testnet connectivity evidence | Production endpoint blocked from this environment |
| BTCUSDT sweep/retest research proposals | IMPLEMENTED | Unit-tested | RESEARCH_ONLY; execution authority disabled |
| Binance Futures Testnet account reads | IMPLEMENTED as discovery evidence | Authentication, balance, position and metadata reads verified | Read-only; existing external testnet positions must be preserved |
| Binance crypto order execution | NOT IMPLEMENTED | N/A | DISABLED |
| Large-SMC replay and research funnel | IMPLEMENTED | Corrected replay baseline recorded | RESEARCH_ONLY; C10 remains blocked |

Latest recorded project regression evidence belongs to the dated status documents and
must be quoted with its tested working-tree state. The rolling project snapshot reports
`1356 passed / 1 skipped / 0 failed` for the 2026-09-02/03 trade-opportunity remediation
milestone; this report does not rerun or independently replace that evidence.

### Required upgrades

#### Complete `AG_TRADE_ASSISTANT_V1_0_3`

- Release manifest added — `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` — pinning
  the Asian/London and London/New York proposal-only runtimes, BTC research-only
  runtime, Large-SMC research boundary, effective configuration references and safety
  posture. Status remains RELEASE_CANDIDATE; release qualification gates are recorded,
  not completed.
- Reconcile `README.md`, `docs/README.md` with the manifest as needed (not yet done;
  `PROJECT_STATUS.md` reconciled).
- Run operational preflight and begin 20-trading-day FX shadow validation.
- Run 30-calendar-day BTC observation only after a production-quality BTCUSDT market-data
  source is available from an authorized environment. Binance Testnet prices must not be
  treated as real-market strategy evidence.
- Rotate previously exposed exchange credentials and remove withdrawal permission before
  any further authenticated broker validation.

#### Proposed `AG_TRADE_ASSISTANT_V1_1_0` — demo execution integration

- Implement an offline-tested `CryptoTradeCommand`, explicit broker/environment router,
  exchange-filter refresh, quantity/price normalization, journal, atomic idempotency and
  restart reconciliation.
- Require an explicit account environment; never default or fall back between DEMO and
  REAL.
- Add Binance server-time correction and secret-safe authenticated error handling.
- Validate against Binance Futures Testnet with rotated credentials. An actual testnet
  order remains a separate, freshly confirmed user action.
- Preserve all existing FX behavior and leave all real-money sends disabled by default.

#### Proposed `AG_TRADE_ASSISTANT_V1_2_0` — Large-SMC proposal readiness

- Resolve and freeze C10A structural invalidation and C10B simulated broker-stop rules
  without optimizing against the four corrected research occurrences.
- Complete causal stop/target/ambiguity outcome simulation, wider discovery and robustness
  validation.
- Authorize proposal generation only through a separate registry/ledger decision after
  the evidence passes. Demo/live authority remains independent.

#### Future major release — real trading operations

- Complete dedicated deployment, credential rotation, monitoring, account reconciliation,
  incident recovery and broker-specific live validation.
- Prefer isolated MT5 terminal instances per account/environment over automatic switching
  of one shared terminal.
- Require separate owner authorization for each strategy and broker domain. Code
  availability or API-key trading permission must never imply live authorization.

### Versioning boundary

Application versions cover runtime, reporting, persistence, broker adapters and operating
controls. Strategy versions change only when signal, entry, stop, target, session or risk
semantics change. The V1.0.3 release candidate therefore continues to use
`ST_ASIAN_SWEEP_5R_V1 v1.1.1`, `ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0`, and
`ST_LARGE_SMC_V1 v1.0.6`; it does not silently promote any strategy's execution authority.

Two independent version histories are maintained. **Application/release version
changes (reporting, persistence, runtime operations, recovery, CLI, journaling,
monitoring, execution plumbing) do NOT imply a strategy semantics change, and vice
versa.** A strategy version bump is required only when setup qualification, sweep
definition, direction, entry, confirmation, stop, targets, or session strategy logic
itself changes — never for logging, reporting, persistence, restart recovery, CLI
changes, journal hygiene, or release manifests.

## Application Release History

| Release | Status | Purpose | Manifest |
|---|---|---|---|
| `AG_TRADE_ASSISTANT_V1_0` | FROZEN | First operational release: post-Asian London pilot for EURUSD+GBPUSD, single-slot selection, PROPOSAL_ONLY. | `config/releases/AG_TRADE_ASSISTANT_V1_0.yaml` |
| `AG_TRADE_ASSISTANT_V1_0_1` | IMPLEMENTED | Portfolio/daily-ledger hardening: `ready_at` (qualifying closed M15, never wall-clock) selection ordering, two-slot daily opportunity ledger (max 2/day, 1/symbol) with cross-process atomic claims, `max_open_positions=2` with a 1.0% aggregate-open-risk gate, `-1R` realized strategy loss lock layered on the unmodified project-wide `-2R` guard. | `config/releases/AG_TRADE_ASSISTANT_V1_0_1.yaml` |
| `AG_TRADE_ASSISTANT_V1_0_2` | CURRENT DOCUMENTED RELEASE | Operational observability + restart recovery: fixed READY-decision restart reconstruction (previously downgraded to NOT_READY on reload), immutable Asian snapshots (fail-closed on conflicting rewrite), a dedicated `--preflight` CLI, event-driven `--watch` output, a complete Entry Ticket renderer, a journal-grounded end-of-window report, and lightweight monitoring counters. Execution integration remains `NOT_WIRED`. | `config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml` |
| `AG_TRADE_ASSISTANT_V1_0_3` | RELEASE CANDIDATE | Current source baseline described in the capability report above: London/New York FX proposal pilot, BTCUSDT research runtime, multi-occurrence research evidence, Large-SMC replay correction, execution-boundary hardening, and read-only broker/testnet discovery. Scope is frozen for validation; defects may be fixed, but unrelated features are deferred. | `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` |
| `AG_TRADE_ASSISTANT_V1_1_0` | PROPOSED | Crypto demo-execution infrastructure, kept independent from Large-SMC research readiness. | — |
| `AG_TRADE_ASSISTANT_V1_2_0` | PROPOSED | Large-SMC proposal-readiness evidence after C10A/C10B contract resolution. | — |

The earlier `AG_TRADE_ASSISTANT_V1_1` “SMC advisory context” entry was a roadmap
placeholder only. It was never released and is superseded by the explicit, independently
scoped V1.1.0 and V1.2.0 roadmap entries above.

**`ST_ASIAN_SWEEP_5R_V1` v1.1.1** remains the FX Asian/London strategy authority across
these application releases. Other strategy and research runtimes listed for V1.0.3 retain
their own independent registration, proposal, demo, and live authority states. An
application release never implies a strategy semantic or authorization change.

## Strategy Version History

| Strategy | Version | Status | Used by application releases |
|---|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1` | 1.1.1 | ACTIVE, `SOLE_DAY_TRADING_AUTHORITY` (pilot-scoped) | V1.0, V1.0.1, V1.0.2, V1.0.3 release candidate |
| `ST_LIQUIDITY_SWEEP_RETEST_V1` | 2.0.0 | `ACTIVE_INCUBATION`, BTCUSDT research/proposal-only; crypto execution disabled | V1.0.3 release candidate only |
| `ST_LARGE_SMC_V1` | 1.0.6 | `RESEARCH_DRAFT`, advisory-only, fail-closed (`proposal_generation_authorized: false`, engine `src/large_smc_research/` RESEARCH_ONLY) | V1.0.3 research component only; no proposal authority |

`ST_LARGE_SMC_V1` is a fully independent strategy family (`strategies/ST_LARGE_SMC_V1.yaml`,
spec `docs/specs/LARGE_SMC_V1_SPEC.md`) — it does not inherit `ST_ASIAN_SWEEP_5R_V1`'s,
`SMC_3R_V1`'s, or `ST_LIQUIDITY_SWEEP_RETEST_V1`'s rules, authorization, or validation
evidence, and it does not appear in any `AG_TRADE_ASSISTANT_V1_0*` release manifest.

- **v1.0.1 (2026-09-01):** UC-001 (timeframe roles) resolved by owner to D1/H1/M5,
  matching AG's own frozen E1/E2/E3 + M1/M2/M3 research pipeline; C11 (target model)
  resolved by owner (Candidate 2, `HYBRID_WITH_STRUCTURAL_FALLBACK`) and frozen as a
  `CONTRACT_ONLY` `target_model:` block. Still `RESEARCH_DRAFT`; no engine, proposal,
  or execution authority added. See `docs/specs/LARGE_SMC_V1_SPEC.md` and
  `docs/status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`.
- **v1.0.2 (2026-09-01):** C12 (candidate expiry/lifecycle) resolved by reuse — no
  independent M1/M2/M3 clock exists anywhere in AG; validity is governed entirely by
  the already-implemented, shared `QualifiedEEvent.is_eligible_at()` E-context window.
  Frozen as a `CONTRACT_ONLY` `candidate_lifecycle:` block. Still `RESEARCH_DRAFT`; no
  engine, proposal, or execution authority added. See
  `docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`.
- **v1.0.3 (2026-09-01):** C14 (duplicate/re-entry, candidate identity) claimed
  resolved by reuse via `src/proposals/identity.py`'s `setup_id()`/`reference_key_for()`
  and `src/proposals/lifecycle.py`'s lifecycle machinery. **Correction, same day
  (`ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY`):** this overclaimed —
  `setup_id` is a setup-*family* identity only (one `event_id`/`setup_id` legitimately
  spans multiple eligibility intervals); no canonical M-candidate structural identity
  existed anywhere, and the lifecycle store (keyed only by `setup_id`) was shown to
  overwrite terminal records rather than preserve them. `candidate_identity.authority`
  was downgraded to `PARTIALLY_RESOLVED`, no version bump for the correction itself.
  See `docs/status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`
  and `..._C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`.
- **v1.0.4 (2026-09-01, `ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING`,
  owner-selected Option B):** the C14A gap closed by implementation. Additive
  `source_id` fields added to `M1Result`/`M2Result`/`M3Result`
  (`src/entry_confirmation/`), computed from already-existing structural evidence
  (`liquidity.level_id` / new `supply_demand.zone_id` + a confirming timestamp), no
  new detection logic. New `src/proposals/occurrence_identity.py` composes
  `eligibility_interval_id()` + `candidate_occurrence_id()` — additive, unit-tested,
  **not** wired into `proposals/lifecycle.py`'s live store (that migration is shared
  with the live `SMC_CONDITIONAL_ENTRY_V2` watcher, deferred as
  `SHARED_CHANGE_REQUIRED`). 172 pre-existing tests plus the golden vertical slice
  (7) and Stage1/Stage2 identity tests (21) pass unchanged, proving backward
  compatibility. Still `RESEARCH_DRAFT`; no engine, proposal, or execution authority
  added. See
  `docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`.
- **v1.0.5 (2026-09-02, `RESEARCH_ONLY_FUNNEL_V1`):** minimum research-only two-part
  funnel (data collection -> decision making) implemented as `src/large_smc_research/`
  -- thin orchestration over the already-frozen `historical_replay.stage2` boundary,
  zero E/M redetection. C01 (instruments -> `[EURUSD]`), C16 (warmup -> reuse of
  `D1=60/H1=50/M5=200`), C11 target-model adapter (`IMPLEMENTED`, formula unchanged),
  and C18 (simultaneous-combination selection -> `RECORD_ALL_INDEPENDENTLY`, reuse of
  C14) all resolved. `decision_states` dropped placeholder `READY` for
  `RESEARCH_QUALIFIED`/`INVALIDATED`. C10 (broker stop-loss) and post-READY
  pending-entry expiry deliberately remain unsigned by owner decision -- the engine
  fails closed to `BLOCKED` rather than guessing either; two decision-packet documents
  record unselected candidate options. Still `RESEARCH_DRAFT`; no proposal, demo,
  live, execution, or risk-sizing authority added. See
  `docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`.
- **v1.0.6 (2026-09-02, `OUTCOME_LIFECYCLE_V1`):** post-READY pending-entry expiry
  `RESOLVED_BY_REUSE` (`historical_replay/fill_simulator.py`, exact reuse, no new
  clock/formula). C10 remains `UNSIGNED`/`BLOCKED`. Discovered, disclosed, and worked
  around (not fixed) a separate gap: C11's target-model adapter and pre-existing M1
  inducement detection require live MT5 symbol metadata unavailable during historical
  replay -- now fails closed to `DATA_ERROR` instead of a misleading `NO_TRADE`.
  Recommendation: `HOLD`. See
  `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`.
- **`REPLAY_METADATA_DECOUPLING_V1` (2026-09-02, replay-infrastructure fix, no strategy
  version bump per this table's own policy below):** the MT5-symbol-metadata replay
  gap is resolved via an owner-approved, dataset-fingerprint-bound historical
  `tick_size` manifest -- no entry/confirmation/stop/target/session logic changed.
  Corrected September 2025 replay isolates the effect to exactly one combination cell
  (E1M1, previously starved), classified a metadata correction, not a regression. C10
  remains the sole open blocker; recommendation `GO_TO_C10_DECISION`. See
  `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`.

A strategy version bump is required if a change affects: setup qualification, sweep
definition, direction, entry, confirmation, stop, targets, session strategy logic, or
intrinsic trade eligibility logic — including SMC or order-flow becoming strategy
authority. It is **not** required for logging, reporting, persistence, restart
recovery, CLI changes, journal hygiene, release manifests, or operator status views.
