# MISSION A8 — Independent Freeze Audit: FX Opportunity Platform V2

**Verdict:** `FX_OPPORTUNITY_PLATFORM_V2_AUDIT_PASS_WITH_CAVEATS`
**Auditor:** Independent audit agent (Arena). Claude built the platform; this audit verifies it independently — Claude's own report was NOT trusted.
**Method:** Read-only. Isolated detached git worktree at candidate `6fdc921a`. No broker connection; capture/replay fixtures only. origin/main left untouched.
**Date:** 2026-09-29.

---

## §3 — Lineage validity

| Field | Value |
|---|---|
| `AUDITED_SHA` | `6fdc921a` (audit branch `audit/vt-spread-evidence-p6-r2` tip) |
| `AUDITED_TREE` | `cf6112e9` |
| `ORIGIN_MAIN` | `4bbba319` (untouched; audit created no commits on it) |
| `MERGE_BASE(main, candidate)` | `4bbba319` |
| `AHEAD / BEHIND` | 29 ahead / 0 behind |
| `MERGE_COMMITS` | 0 (linear history) |
| `HISTORY_REWRITE` | NONE — main is a strict ancestor of the candidate; no force-push/rebase of shared history detected |
| `LINEAGE_VALID` | **YES** |
| Live-verify milestone `1e265339` (P6-R1) | Ancestor of candidate = **YES** |
| Collector V2 `76348c72` | **UNFETCHABLE** ("not our ref") → **EXCLUDED** from freeze candidate |

`ORIGIN_MAIN_DIFFERS = YES`. The audited evidence branch is **not** merged mainline and must not be treated as such.

---

## §4 — Scope classification of candidate changes (vs `4bbba319`)

| Class | Surfaces |
|---|---|
| **REQUIRED_PLATFORM** | `src/fx_opportunity/*` (instruments, market_state, scanner, runner); `src/mt5/{time_authority,market_data,broker_time}.py`; `src/opportunity/asian_sweep_adapter.py` + imported funnel (`candidate_store, registry_binding, contracts, engine, proposal_eligibility, transitions, stages`); `src/post_asian_pilot/*` (byte-exact restore from `2b75bbf`, imported by runner); `src/shared_cache/*`; `src/runtime_state/store.py`; `config/instruments/fx_opportunity_instruments.yaml`; `config/pilot/AG_POST_{ASIAN_LONDON,LONDON_NEWYORK}_PILOT_V1_0_1.yaml`; `strategies/{registry.yaml, ST_ASIAN_SWEEP_5R_V1.yaml}`; `scripts/{run_fx_opportunity_once,replay_fx_opportunity}.py`; the platform test suite. |
| **EVIDENCE_ONLY** | `artifacts/validation/VT_MARKETS_FRICTION_EVIDENCE/*` (+ `.gitattributes` byte-pin); `src/fx_friction_capture/*`; `scripts/capture_vt_spread_evidence.py`; P6-R1 live-verification status doc; A6 friction capture tests. |
| **RESEARCH_ONLY** (exclude from freeze) | `src/fx_discovery/*`; `src/outcome_resolution/*`; `config/governance/{AG_OUTCOME_RESOLUTION_CONTRACT_V2, ..._FRICTION_GATE_CONTRACT_DRAFT, AG_SEALED_OOS_REGISTRY}.yaml`; `config/research/*`; `data/research/*`; `artifacts/research/*`; `docs/research/*`; related tests. Confirmed **not** on the platform runtime import path. |
| **UNRELATED** | None introduced by the platform. Pre-existing crypto/Bybit surface (`execution_runtime.bybit_linear_perp_feed`, `crypto_opportunity_scanner`) is unrelated and unaffected. |
| **SECURITY_SENSITIVE** | **None.** No `.env` tracked; secret-scan of added lines returned only guard code (`assert_secret_free`, forbidden-key lists `login/password/account/passwd/investor`), no credentials. CLI never reads the login/account number. |

---

## §5 — Three-pair semantics (pips)

| Symbol | pip size | digits | Status |
|---|---|---|---|
| EURUSD | 0.0001 | 5 | Bound, verified |
| GBPUSD | 0.0001 | 5 | Bound, verified |
| USDJPY | **0.01** | 3 | Supported spec; **UNBOUND** at runtime |

No generic `0.0001` assumption: `Instrument.price_to_pips` is per-instrument; USDJPY pip = 0.01. Broker-spec mismatch fails closed (`check_broker_spec`). **PASS.**

---

## §6 / §13 — Runtime strategy & USDJPY → NO_COMPATIBLE

- Runtime strategy = **`ST_ASIAN_SWEEP_5R_V1` @ `1.1.1`** (`asian_sweep_adapter.STRATEGY_ID/STRATEGY_VERSION`; yaml `version: 1.1.1`). The `1.2.0-CANDIDATE` is research-only and not on the runtime path.
- Both pilot universes = `[EURUSD, GBPUSD]` (strategy_version `1.1.1`). USDJPY is supported-but-unbound → resolves to **`NO_COMPATIBLE_OPPORTUNITY_STRATEGY`** with **no fallback** and **no fabricated candidate**.
- `strategies/registry.yaml`: `demo_authorized = false`, `live_authorized = false`.
- **PASS**, with **CAVEAT-1** below.

---

## §7 — Server-time authority (`mt5/time_authority.py`)

Verified as a **shared server property**, not a one-symbol largest-gap:

- Offset resolved into **weekly effective periods** keyed by true-UTC reopen instant (`TimeAuthorityPeriod`); DST changes are **data-derived**, never a hardcoded `+3`.
- **Whole-hour evidence requirement**: a reopen reading that does not resolve to a whole-hour offset is REJECTED (`REJECTED_NOT_WHOLE_HOUR`); missing bars never redefine the clock and history is never back-filled.
- **Same-server consensus**: evidence pooled across symbols of the same server; disagreement within a period → `TimeAuthorityConflict` (no majority vote). Bounded local fallback (`SYMBOL_LOCAL`) is labelled distinctly.
- **Missing authority** → `TimeAuthorityUnavailable` (fail closed).
- **Week-boundary leakage prevented**: `coverage_end()` never spans an unobserved next week (`WEEK_BOUND`); a period does not inherit its offset into an unobserved week.
- **DST ambiguity** at reopen resolved by `at_broker` selecting the latest already-reopened period.
- Pure module (no MT5 import).

Test evidence (all passing): `test_winter_offset_is_derived_not_assumed` (+2), `test_offset_changes_across_dst_transition` (spring/autumn, +2↔+3), `test_incomplete_reopen_is_rejected_as_evidence_not_interpreted` (USDJPY 00:15 case), `test_same_server_authority_covers_usdjpy_incomplete_week`, `test_symbol_local_only_leaves_the_incomplete_week_uncovered`, `test_same_week_disagreement_fails_closed`, `test_no_weekend_evidence_is_unavailable`, `test_period_never_spans_an_unobserved_week`, `test_previously_validated_authority_conflict_fails_closed`, `test_dst_transition_maps_each_bar_through_its_own_period`. **PASS.**

---

## §8 — Legacy largest-gap NOT reachable from Opportunity runtime

- `broker_time.detect_broker_utc_offset_hours` (legacy largest-gap) is consumed **only** by `scripts/acquire_ssc_v1_0_1_g2_dev_001.py` (acquisition script).
- The runtime path (`market_data.py`) imports only `BrokerTimeError` from `broker_time` and routes all offset conversion through `time_authority` / `server_time_timeline`. `time_authority` imports only `MIN_WEEKEND_GAP, BrokerTimeError, offset_from_reopen`.
- `LEGACY_TIME_PATH_RUNTIME_REACHABLE = NO`. **PASS.**

---

## §9 — Broker / server / environment gating (fail-closed)

CLI `scripts/run_fx_opportunity_once.py` enforces, in order, before any scan:

1. Real-package guard (see §10).
2. `initialize()` with **no credentials** (attach to running terminal); failure → `LIVE_MT5_AUTH_BLOCKED` / `DATA_UNAVAILABLE`, exit 2.
3. `account_info()` None → `LIVE_MT5_AUTH_BLOCKED`.
4. **DEMO gate**: `trade_mode == ACCOUNT_TRADE_MODE_DEMO` else `ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO`, exit 2.
5. **Server allowlist**: `server ∈ broker.servers` (default broker `VTMARKETS` → `VTMarkets-Demo`) else `BROKER_SERVER_MISMATCH`, exit 2.
6. Login/account number is **never** read into output; only broker canonical name, server string, and DEMO/NOT_VERIFIED_DEMO.

Historical VANTAGE identities are **not rewritten** (kept as a separate broker with empty servers, USDJPY `verified:false`). Vantage vs VT Markets evidence never mixed. **PASS.**

---

## §10 — Real-package-or-fail-closed vs repo-root stub

- `is_stub()` flags the module if its `__file__` is under the repo root **OR** it exposes `MT5StubOperationAttempted`. On stub → emits `MT5_REAL_PACKAGE_UNAVAILABLE` (reason `MT5_STUB_MODULE`), `market_data_mode`/`source` never claim REAL, exit 2.
- `market_data._require_connected` independently fails when `terminal_info()` is None.
- Registry (`registry_binding.py`) is read-only, only `SESSION_TRADE_V1` dispatchable, `execution_authority = NONE`.
- **PASS.**

---

## §11 — MarketState (`fx_opportunity/market_state.py`)

- Facts/provenance only: no direction, signal, execute/authorized flag, or broker handle → capability-zero.
- **Closed-bars-only**: `closed_only` keeps bars with `close ≤ min(now, end)`; `build_market_state` **raises** `ValueError` on any forming bar (`bar.time + M15 > now`).
- **Fixed forming-bar / dropped-row fingerprint bug**: dropped/forming/future-bar counts are held in the runner `provenance`, **not** in the fingerprinted `fields` dict. The MarketState `fingerprint` is over closed-bar facts only, so the mere presence (or later mutation) of forming/future bars in a feed cannot change the state or its fingerprint.
- Deterministic `fingerprint(fields)`, pure. Server-time periods recorded in `server_clock` and fingerprinted.
- **PASS.**

---

## §12 — OpportunityCandidate capability-zero

`opportunity/contracts.py` `OpportunityCandidate` docstring states it is "not execution decisions, strategy profitability, or Demo/Live authorization." Fields are identity/stage/outcome/fingerprint/strategy_version only; `CanonicalProposal` remains separate and is never substituted; `ProposalEligibilityDecision.authorization_status` defaults `NOT_EVALUATED`. **PASS.**

---

## §14 / §15 — Containment (no runtime route to Proposal/TradeTicket/execution; zero broker mutations)

| Check | Result |
|---|---|
| Static AST scan (`src/{fx_opportunity,opportunity,mt5}`) for order_send/order_check/positions/orders/trade_* | **0 mutation calls** (docstrings only) |
| Static scan for execution-module imports | none (FORBIDDEN_ROOTS/MODULES absent) |
| Fresh-interpreter transitive import of scanner+runner | loads only funnel + mt5 + shared_cache + post_asian_pilot + runtime_state.store; **no** execution/scheduler/governor/telegram/proposal/pipeline modules |
| Execution packages restored on branch | **absent** (`test_execution_packages_are_not_restored`) |
| **Runtime sentinel** (`test_runtime_zero_broker_mutation_three_pairs_both_cycles`) | `BROKER_ORDER_CHECK_CALLS=0`, `ORDER_SEND=0`, `OTHER_MUTATIONS=0` across 3 pairs × both cycles; every summary `trade_ticket=NOT_CREATED`, `proposal=NO_PROPOSAL_AUTHORITY`; statuses include `NO_COMPATIBLE_OPPORTUNITY_STRATEGY` |
| CLI runtime | all mutation APIs monkey-blocked with counters, printed as `broker_mutation_calls`; output hardcodes `proposal_authority=NONE`, `trade_ticket=NOT_CREATED` |

`proposal_eligibility` exposes only `evaluate_proposal_eligibility` → eligibility evidence; it creates no proposal. **PASS.**

---

## §16 — Persistence (dedup / restart / symbol+cycle separation)

- Candidate identity keyed by `strategy:symbol:pair:trading_date` → EURUSD and GBPUSD cannot collide; repeated polls are idempotent (`test_same_occurrence_keeps_identity_and_repeated_poll_is_idempotent`).
- USDJPY never reaches `evaluate_fx_opportunity` (NO_COMPATIBLE), so **no fake candidate** is persisted.
- **PASS.**

---

## §17 — Determinism

`test_three_pair_scan_is_deterministic`, `test_identical_input_replays_identically`, `test_bound_symbols_reach_the_same_scale_invariant_decision`: identical fixtures → identical fingerprint/status/ID, for both cycles and all three symbols. **PASS.**

---

## §18 — Look-ahead

`test_market_state_ignores_forming_and_future_bars`, `test_build_market_state_rejects_a_forming_bar`, `test_forming_candle_is_never_evaluated`, `test_future_candle_mutation_does_not_change_result` (mutate data after T → result unchanged). Hard gate honored. **PASS.**

---

## §19 — P6-R1 live evidence review (no broker connection)

`docs/status/AG_FX_OPPORTUNITY_PLATFORM_V2_LIVE_VERIFICATION_STATUS.md` reviewed as a document only; broker was **not** contacted. Live milestone `1e265339` confirmed to be an ancestor of the candidate. Evidence is consistent with the audited code paths above. VT capture `VT_SPREAD_20260928T190357Z_18ee81e6` is the A6-audited artifact (byte-pinned via `.gitattributes * -text`).

---

## §20 — Test execution & baseline-failure classification

- Focused platform suites: **182 passed, 4 skipped**.
- Full suite excluding the unrelated crypto/Bybit surface: **577 passed, 4 skipped**.
- The 4 skips are live-terminal-only tests (`requires a running MT5 terminal`) — expected offline, not failures.
- **Classified-separate baseline condition:** `tests/test_bybit_linear_perp_feed.py` and `tests/test_crypto_opportunity_scanner.py` fail at **collection** because `execution_runtime.bybit_linear_perp_feed` imports `requests`, absent in the audit sandbox. This is an **unrelated surface / missing optional dependency**, not a platform regression, and is not required to be green for the freeze (per mission constraint).
- Audit-sandbox test deps installed disposably (`pyyaml`, `pytest`, `numpy` via `--break-system-packages`); no change to the platform or its runtime dependencies.

---

## §21 — Freeze readiness

The platform delivers exactly the certified capability boundary: real read-only MT5 → canonical broker-time normalization → MarketState → Opportunity evaluation → deterministic persisted Opportunity state → **STOP**. No scheduler, no Proposal authority, no TradeTicket, no execution is present or reachable. **Freeze-ready as a read-only Opportunity baseline.**

---

## §22 — Merge recommendation

**Do NOT merge `audit/vt-spread-evidence-p6-r2` wholesale.** The branch commingles REQUIRED_PLATFORM, EVIDENCE_ONLY, and RESEARCH_ONLY commits.

Recommended: a **bounded platform PR / audited recovery merge** carrying only the REQUIRED_PLATFORM set (§4) plus the EVIDENCE_ONLY artifacts needed for provenance, explicitly **excluding** RESEARCH_ONLY surfaces (`fx_discovery`, `outcome_resolution`, research configs/data/docs) and the unfetchable Collector V2 (`76348c72`). This minimizes resurrecting unrelated/obsolete code while preserving the P1–P6 / R1 platform lineage. origin/main (`4bbba319`) must remain the merge base of record.

---

## §23 — Verdict & caveats

**`FX_OPPORTUNITY_PLATFORM_V2_AUDIT_PASS_WITH_CAVEATS`**

Success criterion met: the platform can safely become the stable read-only Opportunity baseline even though strategy economics are unresolved, Proposal authority is NONE, the TradeTicket is not created, and friction research is incomplete.

**Caveats / hardening notes:**

1. **Single-layer USDJPY exclusion.** `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` `instruments:` still lists `USDJPY` (and AUDUSD, XAUUSD). The runtime NO_COMPATIBLE guarantee holds solely because both pilot universes are `[EURUSD, GBPUSD]`. Harden to defense-in-depth by removing unbound symbols from the strategy `instruments` list or adding an assertion that the runtime universe ⊆ pilot universe.
2. **Collector V2 (`76348c72`) excluded** as unfetchable; any live-collection improvements it holds are NOT part of this audited baseline.
3. **Branch commingling** (see §22) — bounded PR required, not wholesale merge.
4. **A6 residual** carried in the VT capture evidence: `ZERO_SPREAD = OBSERVED_UNEXPLAINED`. Does not affect the platform capability boundary; noted for evidence provenance.
5. **Audit-sandbox dependencies** (`pyyaml`, `pytest`, `numpy`) were installed disposably to run tests; the unrelated crypto/Bybit tests need `requests` and were classified as a separate, pre-existing baseline condition.
6. Live P6-R1 evidence reviewed as documentation only; no broker connection was made (per constraint).
