# SVOS Authority Map — P1

Permanent Strategy Validation Operating System authority map for the
`HISTORICAL → OPTIMIZATION → VIRTUAL FORWARD → DEMO ELIGIBILITY` flow. Every domain is
resolved to its **existing canonical authority**; nothing here creates a competing one
(`REUSE > EXTEND > CREATE`). The machine-readable version is `src/svos/authority.py`.

## Disposition

No `ARCHITECTURAL_ADJUDICATION_REQUIRED`. The mission's requested lifecycle vocabulary
reconciles to the existing canonical **AG_VALIDATION_G0_G10_V1** gate vocabulary (and
the existing `LifecycleStage` authority). No new authoritative lifecycle label is
introduced. The prior `FUTURE_SVOS_ADR_REQUIRED` item (standalone "BACKTEST" stage) is
resolved **by gates, not by a new stage** — `BASELINE_BACKTESTED` ≡ G2 (Deterministic
Population) + G3 (Economic Gate) evidence.

## Domain map

| Domain | Existing authority | Reuse | Gap / SVOS action |
| --- | --- | --- | --- |
| STRATEGY_CONTRACT | `strategies/<ID>.yaml` + per-strategy native entrypoint | REUSE | historical & forward call the SAME entrypoint (P16) |
| DATA_ADMISSION | `validation_framework.validation_admission` + `svos_contracts.StrategyValidationProfile` | REUSE | none |
| HISTORICAL_REPLAY | per-strategy replay (`session_sweep_continuation.replay.run_replay`, `historical_replay.orchestrator.ChronologicalReplay`) + `performance.calculator` | EXTEND | strategy-neutral runner added → `svos.historical_runner` |
| ECONOMIC_METRICS | `validation_framework.economic_gate`/`g3_gate` (G3) + `performance/calculator.py` | REUSE | G3 fail-closed while contract PROPOSED (owner sign-off) |
| HYPOTHESIS_PREREGISTRATION | `svos_contracts.HypothesisRegistration` + G1 artifacts | EXTEND | optimization contract added → `svos.hypothesis` |
| BOUNDED_OPTIMIZATION | `external_candidate.DatasetRole` + `research_factory_v1.yaml` | CREATE | bounded optimizer added → `svos.optimization` |
| ROBUSTNESS | `external_candidate.walk_forward`/`oos_evaluator`; economic contract robustness block | EXTEND | mapped to canonical G5; no new thresholds |
| HOLDOUT/OOS | `external_candidate.DatasetRole.HOLDOUT` + `HoldoutDeclaration`; `HoldoutState` | REUSE | one-shot firewall in `svos.optimization` |
| PROPOSAL | `proposal_envelope` (CanonicalProposal, ProposalLedger) | REUSE | forward proposals are VirtualBroker orders, never envelopes/orders |
| FRICTION | `performance/cost_model.py`, `fx_friction_research`, per-strategy friction | EXTEND | component-state `FrictionProfile` → `svos.friction_profile` (UNAVAILABLE ≠ zero) |
| EXECUTION | `execution.executor`/`mt5_gateway`, `mt5.management_gateway` | REFERENCE_ONLY | NEVER imported by `src/svos/` (static proof) |
| FORWARD_EVIDENCE | `scripts/resolve_forward_shadow_outcomes.py` (signed outcome contract) | CREATE | `svos.forward` + `svos.virtual_broker` |
| LIFECYCLE_STATE | `LifecycleStage` via `lifecycle_registry`; G0–G10; `research_factory_v1.yaml` | REUSE | mission vocabulary reconciled as gates (`svos.lifecycle`) |

## Conflicts checked

- **Cycle-1 remediation V2 ADR** ("AG must not invent any named pipeline-stage label"):
  honored — `svos.lifecycle.MISSION_STATE_TO_GATE` is a compatibility map, not an enum;
  `LifecycleStage` remains the only lifecycle authority.
- **`economic_gate_contract.yaml` PROPOSED**: unchanged; G3 remains fail-closed.
- **H2 friction campaign**: untouched (`H2_CAMPAIGN_MODIFIED=false`).
- **External `Session-SMC/session-smc-trading-bot` SVOS**: locked research, not adopted.
