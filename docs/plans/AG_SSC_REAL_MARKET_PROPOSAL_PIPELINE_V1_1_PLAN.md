# SSC Real-Market Proposal-Only Pipeline (V1.1)

## Context

Mission V1.1 asks for a REAL-MARKET, PROPOSAL-ONLY pipeline for `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1 (SSC), with two isolated lanes (real-market proposal/forward-evidence vs frozen-dataset canonical validation), explicit quality gates (QG0–QG9), a reuse-first WP0 audit, and a stricter final-report contract (READY / READY_WITH_DOCUMENTED_LIMITATIONS / BLOCKED_&lt;reason&gt;). It supersedes the V1 mission text but targets the same repository state; two rounds of read-only preflight (Explore agents + direct file reads) are already done and inform this plan.

**Repository authority verified at HEAD (`2300d00`)**: canonical SSC is `src/session_sweep_continuation/` (isolated package, S1/S2/S3 setups in `setups.py`, deterministic replay driver in `replay.py::run_replay`). `config/governance/strategy_lifecycle.yaml:35-37` and `src/validation_framework/adapters/session_sweep_continuation_adapter.py:29` both authoritatively declare `semantic_version="1.0.1"` (the v1.0.1 partial-target-direction fix is already live in `outcome_resolution.py`, frozen by commits `02d7b29`→`2300d00`). Only `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml:22` still says `version: 1.0.0` — a stale label, not a semantic conflict (no parameter differs). **Resolution**: treat 1.0.1 as canonical (per the lifecycle registry + adapter + code, the actual authorities), correct the YAML label as a metadata fix, not a semantic rewrite. This is not a BLOCKED condition.

The frozen HYP_001/CONFIRM_001/CORRECTED_CONTROL artifacts under `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/` are validated as fully isolated from this work: this pipeline only calls `run_replay` (unmodified) and writes to `state/proposal_ledger/proposal_ledger.json` (a separate, pre-existing store) — no code path touches `artifacts/validation/**`.

## WP0 — Reuse audit result (REUSE / EXTEND / MISSING / CONFLICT)

| Capability | Status | Where |
|---|---|---|
| Strategy registry | REUSE | `strategies/registry.yaml`, `config/governance/strategy_lifecycle.yaml` |
| Canonical SSC engine | REUSE | `src/session_sweep_continuation/replay.py::run_replay` (unmodified) |
| MarketSnapshot (REAL/REPLAY/SYNTHETIC) | REUSE | `src/strategy_contract/market_snapshot.py` |
| Real closed-candle fetch | REUSE | `src/mt5/market_data.py::get_candles` |
| StrategyDecision | REUSE (SSC path exists but SHADOW_ONLY, see WP1) | `src/strategy_contract/decision.py` |
| Proposal envelope schema | EXTEND | `src/proposal_envelope/models.py::CanonicalProposal` (add governance fields, §WP4) |
| Formation gate (QG0/QG1 enforcement) | REUSE | `src/proposal_envelope/formation_gate.py::apply_formation_gate` |
| Proposal ledger (persistence, QG8/restart) | REUSE | `src/proposal_envelope/ledger.py::ProposalLedger` |
| SSC → CanonicalProposal adapter | MISSING → BUILD | new `src/proposal_envelope/adapters/ssc_adapter.py` |
| SSC live orchestration (fetch→bias→replay→adapter→gate→ledger) | MISSING → BUILD | new `src/session_sweep_continuation_pilot/` |
| Live H1 bias for SSC | MISSING (SSC's own `h1_bias.py` is historical-replay-only, gated on an `OWNER_APPROVED_DATASET_MANIFEST` that EURUSD does not have) → BUILD thin live wrapper reusing existing generic live bias functions | see §WP1 |
| `/api/proposals`, `/api/canonical-proposals` | REUSE (GET-only, already read persistent ledger state) | `src/api/app.py:266-330` |
| Frontend | REUSE, no changes | read-only "AG Backend" tab already exists per prior work; no execution button added |
| Execution gateway isolation | REUSE, verify only | `src/execution/mt5_gateway.py`, `src/mt5/management_gateway.py` (sole order_send callers); `web/server.ts` real-mode execution routes already retired (HTTP 410) |
| Risk authority | AUDITED, resolved non-ambiguous for SSC — see §WP5 | |

No parallel implementation of any REUSE-classified capability will be created.

## WP1 — Canonical parity contract

Chain: **real closed MT5 candles → `MarketSnapshot.from_real_candle` → `run_replay` (canonical SSC engine, unmodified) → per-accepted-setup `CanonicalProposal` → `apply_formation_gate` → `ProposalLedger`**.

No new S1/S2/S3 evaluator, stop model, or "live SSC" logic is written. `src/session_sweep_continuation/canonical_observations.py`/`canonical_consumer.py` (read in full) already prove this exact `run_replay` call is used for validation/shadow evidence via `SessionSweepContinuationCanonicalController.evaluate()` → `strategy_contract.decision.from_session_sweep_continuation_replay(...)`. The new proposal pipeline calls the **same** `run_replay` function with the **same** config-loading path (`session_sweep_continuation.config`) — parity is structural (one function, one caller convention), proven by a new test asserting: given the identical `(candles, config, symbol, session_pair, trading_date, bias_result, regime_result)`, `canonical_consumer.run_canonical_shadow_cycle(...)` and the new pipeline's direct `run_replay(...)` call produce byte-identical `ReplayResult`/`StrategyDecision` (they must, since both are the same pure function — this test is a regression guard, not new logic).

Lineage recorded per proposal: `strategy_id`, `strategy_version` (="1.0.1"), `config_hash` (reused field, serves as `strategy_contract_hash`), `data_provenance.market_data_fingerprint` (MarketSnapshot hash), `source_record_id` (setup/decision identity — campaign_id + setup_model + entry_time).

**Live H1 bias gap**: `session_sweep_continuation/h1_bias.py::resolve_h1_market_bias` only works against `HistoricalCandleStore` + an authorized `HistoricalSymbolMetadataManifest` (EURUSD's is `PENDING_OWNER_AUTHORIZATION`) — not usable live. `src/daytrading/decision/market_bias.py::derive_market_bias()` shows the already-wired **live** equivalent: `market_structure.tiers.analyze_structure_tiers(symbol, "H1")` (live MT5, no historical patch) → `market_intelligence.bias_resolver.resolve_from_structure_tiers(...)`/`resolve_unavailable(...)` — the exact same two generic, strategy-neutral functions `h1_bias.py` itself calls, just fed from live data instead of a historical store. New file `session_sweep_continuation_pilot/bias.py::resolve_live_h1_bias()` reuses these two functions verbatim (no new bias logic, no change to SSC's own M15 `regime.py`). If `tiers.status != "VALID"`, `run_replay` is called with `bias_result=None` → SSC's own existing fail-closed `BIAS_MISSING` rejection path (`bias_gate.py`) applies — never fabricated.

`SSC_CANONICAL_PARITY = PASS` once this test is green; if not achievable, the mission requires reporting FAIL and withholding readiness — flagged as a go/no-go checkpoint before WP4 continues.

## WP2/WP3 — State separation and quality gates (QG0–QG9)

Map required gate names to existing/added enforcement points — no gate is reimplemented if an equivalent already exists:

| Gate | Enforced by |
|---|---|
| QG0_REAL_DATA | `apply_formation_gate` (`market_data_mode != REAL` → `PROPOSAL_BLOCKED`, `REASON_NON_REAL_MARKET_MODE`) |
| QG1_CLOSED_CANDLES | `sessions.py`'s no-future-contamination guard inside `run_replay` (only bars closed as of decision point) |
| QG2_DATA_FRESHNESS | new pipeline: reject/`WAITING` if the latest fetched M15 candle's close is not the current session's newest closed bar (mirrors `post_asian_pilot/pipeline.py`'s `bar_tracker.is_new_bar` pattern) |
| QG3_SESSION_VALID | `sessions.py::session_windows_from_config` + reference-session completeness check inside `run_replay` |
| QG4_STRATEGY_TRIGGER | `setups.py::evaluate_s1/s2/s3_*` (unmodified) — `accepted_setups == []` ⇒ no proposal, decision surfaces `NO_SETUP`/`WAITING` |
| QG5_STOP_GEOMETRY | `stop_engine.py::compute_stop` (unmodified; rejects with `stop_result.accepted=False` on failure) |
| QG6_FRICTION | `friction.py::estimate_friction` (unmodified; cost_status stamped KNOWN/MODELED/UNAVAILABLE, never invented) |
| QG7_RISK_LIMIT | `campaign.py::allocate_risk` against SSC's own frozen `risk_allocation`/`maximum_total_risk_pct` (unmodified) — see §WP5 |
| QG8_DUPLICATE_CHECK | `ProposalLedger.record_proposal` (idempotent on identical geometry for a given deterministic `proposal_envelope_id`) |
| QG9_AUTHORITY | new adapter field block (§WP4) — always sets `execution_authority=NONE`, `execution_eligible=False`, independent of QG0–QG8 passing |

A setup that passes QG0–QG8 but has `demo_authorized=false` still reaches `proposal_state=PROPOSAL_READY` / `proposal_only=true` / `execution_eligible=false` — QG9 never blocks proposal formation, only execution.

## WP4 — Proposal record contract (extend, don't replace)

`src/proposal_envelope/models.py::CanonicalProposal` gets new **additive** fields (defaults preserve current behavior for the existing FX/BTC adapters, which are untouched):
```
economic_edge_established: bool = False
demo_eligible: bool = False
demo_authorized: bool = False
live_authorized: bool = False
proposal_only: bool = True
execution_eligible: bool = False
broker_mutation_blocked: bool = True
lifecycle_stage: Optional[str] = None
```
`config_hash` (existing field) doubles as `strategy_contract_hash`; no duplicate field added. `setup_evidence`/`cost_assumptions` (existing) carry S1/S2/S3 identity, entry/stop/targets, and itemized friction — `CostAssumptions.status`/`missing_fields` already encodes "unknown stays unknown" (existing invariant, reused verbatim, never overridden to fabricate a value).

New helper `src/proposal_envelope/strategy_authority.py::resolve_strategy_authority(strategy_id, semantic_version, repo_root=".")`: reads `validation_framework.lifecycle_registry.get_lifecycle_stage()` (existing, sole reader of `strategy_lifecycle.yaml`, fail-closed) for `lifecycle_stage`; reads `strategies/registry.yaml`'s existing `demo_authorized`/`live_authorized`; reads the strategy YAML's `demo_eligible`. `economic_edge_established` stays hardcoded `False` (no such field/authority exists anywhere in the repo to read instead — inventing promotion criteria is prohibited).

Extend `src/api/schemas.py::CanonicalProposalResponse` + its mapper in `src/api/app.py` additively (new optional response fields only); no route added/removed; existing `GET /api/proposals` (older `ProposalResponse`/ticket system) left untouched — WP7 compatibility preserved.

## WP5 — Risk authority (resolved, not ambiguous, for SSC)

Audited: `config/trading.yaml:31` (`risk_per_trade_pct: 1.0`, unread default) and `config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml:37` (`risk_per_trade_pct: 0.5`, scoped to the FX/Asian pilot only) are **not** SSC's risk authority. SSC has its own, already-frozen, documented-as-hypothesis risk model in `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml:88-98` (`campaign.maximum_total_risk_pct: 1.0`, `risk_allocation: {S1: 0.40, S2: 0.30, S3: 0.30}`), enforced unmodified by `campaign.py::allocate_risk` inside `run_replay`. This **is** repository authority for SSC specifically (not ambiguous) — the mission's 0.50% default applies only where no such frozen authority exists.

Resolution: `PROPOSAL_RISK_PERCENT` per proposal = the actual `risk_pct` `run_replay` computed for that accepted setup (a fraction of the 1.0% campaign budget, per setup weight — e.g. S1 entries carry ≤0.40%). `RISK_AUTHORITY_STATUS = RESOLVED_SSC_CAMPAIGN_ALLOCATION` (not `AMBIGUOUS_EXECUTION_UNCHANGED` — SSC's authority is explicit). No execution config is touched. `RISK_VERSION` = the same `config_hash` already stamped on the proposal (the risk config is part of the versioned strategy YAML).

## WP6 — Forward-evidence lifecycle

Map to existing lifecycle rather than replacing it: `DETECTED`≈`watcher_state` reaching `SETUP_QUALIFIED`; `PROPOSAL_CREATED`/`READY_FOR_REVIEW`≈`proposal_state=PROPOSAL_READY` (ledger write); `OBSERVED`/`OUTCOME_RESOLVED`≈already-existing forward-shadow-outcome machinery referenced by `scripts/resolve_forward_shadow_outcomes.py` (found in WP0 audit; SSC's `outcome_resolution.py` already computes MFE/MAE/partial/runner/net_R — reused, not reimplemented, via `run_replay`'s existing outcome resolution against real subsequent candles once available). No new "FORWARD_SHADOW_EVIDENCE" population/store is created beyond the `ProposalLedger` entries themselves plus whatever `resolve_forward_shadow_outcomes.py` already targets — confirmed structurally isolated from `artifacts/validation/**` (different directory, different store, no shared writer).

## WP7 — API/Frontend

`GET /api/proposals` and `GET /api/canonical-proposals` (`src/api/app.py:266-330`) already read persistent, ledger-backed state — extend response schema additively (§WP4), no new routes, no execution route restored, no execution button added to frontend. Verify at implementation time that `web/server.ts`'s real-mode execution branches remain HTTP 410 (already confirmed retired in WP0 audit) and are not touched.

## WP8 — Secondary strategy audit (read-only; report only, per-strategy fields)

| Strategy | PROPOSAL_CAPABILITY | DATA_AUTHORITY | EDGE_STATUS | BLOCKER | EXECUTION_AUTHORITY |
|---|---|---|---|---|---|
| ST_LARGE_SMC_V1 | NOT_WIRED | MT5 (FX) | FORWARD_RESEARCH, edge not established | No `proposal_envelope` adapter/pipeline exists | demo_authorized=false, live_authorized=false |
| ST_LIQUIDITY_SWEEP_RETEST_V1 (BTC) | ADAPTER_EXISTS_NOT_WIRED | Bybit (canonical) | FORWARD_RESEARCH | `btc_adapter.py` exists but no pipeline calls `ProposalLedger.record_proposal()` for it | demo_authorized=false, live_authorized=false; **no BTC venue substitution performed** |
| ST_ASIAN_SWEEP_5R_V1 | FULLY_WIRED (pre-existing) | MT5 (FX) | OPERATIONAL_SHADOW | none — already live via `post_asian_pilot`, untouched by this work | demo_authorized=false per registry (blocked by open contract gaps), live_authorized=false |
| ST_M15_SESSION_SWEEP_RESEARCH_V1 | NOT_REGISTERED | n/a | n/a | absent from `strategies/registry.yaml` and `strategy_lifecycle.yaml` entirely | n/a — registering it would be a registry promotion, out of scope/prohibited |

## WP9 — Tests (`tests/test_ssc_proposal_pipeline.py`, new)

Reusing fixtures from `tests/test_session_sweep_continuation_replay_determinism.py`, `tests/test_proposal_formation_gate.py`, `tests/test_proposal_ledger.py`:

1. Real closed candles with a known accepted S1/S2/S3 fixture → `run_ssc_cycle` produces `PROPOSAL_READY` in the ledger.
2. Day with `accepted_setups == []` → no ledger entry (`NO_SETUP`/`WAITING`, never fabricated).
3. `demo_authorized=False` does not prevent creation (record exists).
4. `execution_eligible=False` regardless of (3).
5. `canonical_consumer.run_canonical_shadow_cycle(...)` vs pipeline's direct `run_replay(...)` on identical input → identical `ReplayResult`/`StrategyDecision` (WP1 parity proof).
6. `setup_evidence["setup_model"]`/`source_record_id` round-trip S1/S2/S3 identity unchanged.
7. `MarketSnapshot.from_synthetic_candle(...)` through `apply_formation_gate` → `PROPOSAL_BLOCKED`, never reaches the ledger via the pipeline.
8. Running `run_ssc_cycle` twice on identical inputs → exactly one ledger entry (duplicate decisions, QG8).
9. Rebuild `ProposalLedger` from the same JSON store path (restart) → identical `proposal_envelope_id`, no duplicate.
10. Forward-evidence/ledger writes never touch any path under `artifacts/validation/**HYP_001**`, `**CONFIRM_001**`, `**V1_0_1_REMEDIATION**` (isolation).
11. A proposal built from a setup with unmodeled commission/slippage keeps `CostAssumptions.status != ITEMIZED` and the relevant field `None` — never fabricated.
12. Static/behavioral check (mirrors `tests/test_proposal_envelope_execution_boundary.py`): `session_sweep_continuation_pilot` imports nothing from `execution.executor`, `execution.mt5_gateway`, `mt5.management_gateway`.
13. `web/server.ts`'s retired execution routes remain HTTP 410 in real mode (existing behavior, regression-guarded — light check, e.g. grep/static assertion the retirement code paths are untouched by this change's diff).
14. `GET /api/proposals` (older schema) response shape is unchanged (back-compat snapshot test).

Run narrow tests first, then: `tests/test_session_sweep_continuation_*`, `tests/test_proposal_*`, `tests/test_api_canonical_proposals.py`, `tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py`, then full `pytest -q`.

## WP10 — Safety/non-contamination audit (evidenced in final report)

By construction (no code path exists that could do otherwise) + explicit test coverage (WP9 items 7,10,12,13): `BROKER_MUTATION_OCCURRED=false`, `DEMO_ORDER_SUBMITTED=false`, `LIVE_ORDER_SUBMITTED=false`, `HOLDOUT_ACCESSED=false`, `CONFIRM_001_ACCESSED=false`, `CORRECTED_CONTROL_GENERATED=false`, `STRATEGY_SEMANTICS_CHANGED=false` (only a version-label fix), `HYP_001_CHANGED=false`, `REGISTRY_AUTHORITY_PROMOTED=false`. Confirmed via `git status`/diff review before finishing that no file under `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001*`, `CONFIRM_001*`, `V1_0_1_REMEDIATION/` changed.

## Verification

- `pytest tests/test_ssc_proposal_pipeline.py -v`
- `pytest tests/test_session_sweep_continuation_replay_determinism.py tests/test_proposal_formation_gate.py tests/test_proposal_ledger.py tests/test_proposal_envelope_models.py tests/test_proposal_envelope_adapters.py tests/test_proposal_envelope_execution_boundary.py tests/test_api_canonical_proposals.py tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py -v`
- Full suite: `pytest -q`
- `git status`/diff scoped check confirming no `artifacts/validation/**HYP_001**`/`**CONFIRM_001**` changes, and only the intended file set touched.
- If an MT5 connection is available in this environment: one live `run_ssc_cycle()` call, inspect `GET /api/canonical-proposals` for the new SSC entry with `execution_eligible=false`. If unavailable, note this explicitly rather than claiming live verification occurred (feeds `READY_WITH_DOCUMENTED_LIMITATIONS` vs full READY classification).

Final report delivered in the exact WP-numbered structure the V1.1 mission specifies, ending in exactly one of `READY_FOR_REAL_MARKET_PROPOSAL_AND_FORWARD_EVIDENCE` / `READY_WITH_DOCUMENTED_LIMITATIONS` / `BLOCKED_<reason>`.
