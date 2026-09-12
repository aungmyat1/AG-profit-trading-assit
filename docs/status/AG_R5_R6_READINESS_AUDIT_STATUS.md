# R5/R6 Readiness Audit — Existing Infrastructure and Evidence

Recorded: 2026-09-11
Scope: non-invasive audit per the readiness program's own rule (section 15) — "audit
before building," permitted even before R4/WP12 natural-READY passes since it cannot
affect WP12. No code was written or modified for this entry.

## 1. What already exists (reuse-first inventory)

| Area | Status | Location |
|---|---|---|
| Outcome resolution | **PARTIAL** — FX only | `scripts/resolve_forward_shadow_outcomes.py` (`AG_TRADE_OUTCOME_RESOLVER_V1`, owner-signed 2026-09-09). No general resolver exists; Large-SMC explicitly has none (`tests/test_performance_large_smc_adapter.py::test_no_resolved_trade_samples_until_an_outcome_resolver_exists`). |
| Canonical trade export | **FULLY_EXISTS** (schema+calculator), **PARTIAL** (adapters) | `src/performance/models.py::ResolvedTradeSample`, `src/performance/calculator.py`. FX adapter works; Large-SMC adapter stubbed pending a resolver. |
| Validation/evidence framework | **FULLY_EXISTS**, actively used | `src/validation_framework/` (AG_EGSVF_V1), ledger snapshots in `artifacts/validation_ledger/`, readiness snapshots in `artifacts/readiness/`. `src/validation_diagnostics/` for advisory failure-mode analysis. |
| Friction/cost model | **PARTIAL**, not live-wired | `src/performance/cost_model.py` — only one signed scenario (`CONTRACT_CEILING`); BASE/SEVERE explicitly `NOT_AVAILABLE_NO_SIGNED_ASSUMPTION`. Every resolved FX record still self-declares `cost_status: NOT_INCLUDED` (gross R only). |
| Historical replay | **PARTIAL** | `src/historical_replay/fill_simulator.py` does entry-fill simulation only, not win/loss resolution. |
| **Economic/promotion thresholds** | **MISSING** | No signed minimum profit factor / expectancy / sample size exists anywhere in `config/` or `docs/`. The only numbers found (`_MIN_RESOLVED_SAMPLE=20`, `_MIN_CLASSIFIED_SHADOW_DAYS=5` in `src/validation_diagnostics/adapters/session_trade.py`) are explicitly self-documented as "diagnostic-only judgment calls... never affect any GateStatus," not governance. |

**Consequence per the readiness program's own rule (section 26):** even with complete
resolved-outcome evidence, `ECONOMIC_GATE = NOT_EVALUABLE` until an owner signs a real
threshold. This is a governance gap, not an implementation gap — it is not something
this session can close by choosing a number itself.

## 2. Material finding: existing FX shadow evidence is real and already negative

`artifacts/outcome_resolution/records/` already contains **13 real, resolved
ST_ASIAN_SWEEP_5R_V1 trades** (both ASIAN_LONDON and LONDON_NEWYORK cycles,
2026-09-01 through 2026-09-04), produced by the existing, owner-signed
`AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED` resolver — independent of this session's
WP12/canonical-pipeline work.

```
sample size = 13
wins = 0
losses = 13
realized_R sum = -13.0
terminal_state = RESOLVED_SL for all 13
cost_status = NOT_INCLUDED (gross R only, pre-friction; real net performance likely worse)
evidence_quality = MODERATE (self-declared, all 13)
```

This is **13/13 losses, gross, for the exact strategy (`ST_ASIAN_SWEEP_5R_V1`) this
session's WP12 canonical pipeline is built around.** Per the readiness program's own
rule (section 27, "do not erase or ignore existing historical evidence... do not
cherry-pick only new favorable observations"), this is recorded here in full, not
softened. Sample size is below even the diagnostic-only 20-sample reference and there
is no signed threshold to evaluate it against, so no formal `EDGE_REJECTED` verdict is
possible yet — but this is a real, material, sobering signal, not implementation
noise, and it should inform any decision to keep collecting evidence for this
particular strategy versus prioritizing another.

## 3. Historical "Session Trade" negative evidence referenced in the readiness prompt

The readiness program prompt (section 27) referenced a previously-resolved "Session
Trade" sample with materially negative performance. Searched the live tree: no
resolved-trade dataset or negative-result status doc for `SESSION_TRADE_V1` was found
in `docs/status/` or `artifacts/` on this branch (only stale copies exist under
`.claude/worktrees/*`, not part of the working tree). If that evidence is expected to
exist, it may live in the separate, unvendored `D:\ddev\Session Trade Codex` repository
(consistent with `strategies/session_trade/contract.yaml`'s own note that
`SESSION_TRADE_V1`'s implementation lives entirely there) — flagging this discrepancy
rather than fabricating a record to match the prompt's assumption.

## Reconciliation with this session's WP12 work

This audit does not change or touch WP12. `AG_PROPOSAL_OPERATION_READY_V1` remains
`NOT_YET_PASS` pending a natural READY. The pre-existing FX resolved-trade evidence
above comes from a **separate, already-operating pilot/shadow-validation track**
(`AG_TRADE_ASSISTANT_V1_0_3`, `scripts/resolve_forward_shadow_outcomes.py`), not from
this session's new canonical `proposal_envelope`/`ProposalLedger` pipeline — the two
are related (same strategy, same broker) but structurally independent right now. Once
a natural WP12 READY occurs and R4 passes, a future task should decide whether to
route new canonical proposals into the *existing* outcome-resolution/performance
pipeline (reuse) rather than building a second one — matching the disposition already
established for proposal identity in the WP0 reconciliation.
