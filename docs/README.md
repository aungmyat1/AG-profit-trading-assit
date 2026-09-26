# Documentation Index

This directory contains design contracts, implementation architecture, setup guidance,
and dated verification evidence. Read documents according to their authority, not just
their age. For the shortest path to the active objective, start with the repo priority
plan in [REPO_CLEANUP_AND_OBJECTIVE.md](REPO_CLEANUP_AND_OBJECTIVE.md) and then use
[PROJECT_STATUS.md](../PROJECT_STATUS.md) as the live source of truth.

The [SVOS Virtual Demo Engine V1 Cycle 1 design](svos/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE1_DESIGN.md)
and its linked time, exchange, account, ledger, campaign, qualification, and component
map contracts are design-only references. They grant no campaign or trading authority.
The [Cycle 2 Virtual Time and Feed status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE2_STATUS.md)
records the unit-tested historical clock/feed implementation and its limits.
The [Cycle 3A execution adjudication](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3A_STATUS.md)
links the EURUSD input authority inventory and draft profile; it does not authorize
an integrated exchange or economic campaign.
The [Cycle 3B exchange core status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3B_STATUS.md)
records the isolated deterministic fixture engine and its non-economic limits.
The [Cycle 3C canonical SSC bridge status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3C_STATUS.md)
records the non-mutating SSC-to-virtual-order handoff and its readiness boundary.
The [Cycle 4A account core status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE4A_STATUS.md)
records normalized position/account state and the explicit economic boundary.
The [Cycle 4B ledger parity status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE4B_STATUS.md)
records append-only evidence and deterministic account reconstruction.
The [Cycle 5 orchestration status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE5_STATUS.md)
records end-to-end composition, checkpoints, and determinism boundaries.
The [Cycle 6A reality authority status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_STATUS.md)
records broker/account evidence and the economic readiness boundary.
The [Cycle 6A-R remediation status](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_R_STATUS.md)
records the bounded read-only refresh and residual blocker classification.
The [Strategy Capacity VD Cycle 1 status](status/VD_STRATEGY_CAPACITY_CYCLE1_STATUS.md)
records the context-decision boundary and simulator readiness blockers.
The [Strategy Capacity VD Cycle 2 status](status/VD_STRATEGY_CAPACITY_CYCLE2_STATUS.md)
records canonical SSC binding, later-event virtual orders, checkpoint reconstruction,
and the remaining lifecycle and campaign boundaries.

## Start here

The [repository structure audit](REPO_STRUCTURE_AUDIT.md) records the current layout,
safe cache cleanup, and the recommended archival policy for historical documents and
generated evidence.

1. [`../README.md`](../README.md) — project purpose, safety model, quick start, and map.
2. [`../AGENTS.md`](../AGENTS.md) — mandatory rules for agents working in this repository.
3. [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) — current implementation state,
   safety gates, known gaps, latest regression baseline, and rolling classification
   against the master readiness gates.
4. [`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md) — authoritative Master Project Readiness
   Plan V3: R0–R9 capability gates from safe research watch through canonical
   proposals, edge validation, Demo execution validation, and separately authorized
   controlled Live operation.
5. [`plans/AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1.md`](plans/AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1.md)
   — current priority implementation plan for the authoritative R2-R4 market-truth,
   canonical-decision, and persistent-proposal pipeline; ends at natural read-only
   proof and `AG_PROPOSAL_OPERATION_READY_V1`.
6. [`plans/AG_POST_R4_EXPANSION_AND_DELIVERY_PLAN_V1.md`](plans/AG_POST_R4_EXPANSION_AND_DELIVERY_PLAN_V1.md)
   — deferred follow-on plan for R4 operational hardening, evidence export/reporting,
   informational Telegram delivery, and independently contracted USDJPY/XAUUSD shadow
   coverage.
7. [`plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`](plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md)
   — retained supporting plan for exactly-once delivery work under R4; it is no longer
   the master milestone.
8. [`plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md`](plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md)
   — program-level plan index and handoff map; its original 2026-09-08 stage plan is
   retained as historical context beneath the current plan stack.
9. [`plans/BEST_MONEY_MAKING_PATHS_AND_TICKET_DELIVERY_ACTION_PLAN_V1.md`](plans/BEST_MONEY_MAKING_PATHS_AND_TICKET_DELIVERY_ACTION_PLAN_V1.md)
   — owner-directed commercialization paths and gated action plan for exactly-once
   Major FX, BTCUSDT, and later XAUUSD delivery; includes the independent watcher,
   proposal, and execution-authority dimensions, `STRATEGY_UNMATCHED`, lifecycle
   timestamps, next-required evidence, reuse-first SMC watcher recovery, a downstream
   read-only Opportunity Board, outcome/funnel evidence, campaigns, prospective
   promotion, and cost-stress requirements; planning only and non-authorizing.
10. [`setup/MT5_MCP_SETUP.md`](setup/MT5_MCP_SETUP.md) — local MT5 integration setup.
11. [`status/LIVE_STATUS_MAINTENANCE.md`](status/LIVE_STATUS_MAINTENANCE.md) — required
   update procedure for rolling status, dated evidence, strategy authorization, and
   live-validation claims.
   [`status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md`](status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md)
   — TD-8 six-timeframe historical replay implementation and verification evidence;
   records the fail-closed session-reference limitation and unchanged trading authority.
   [`status/TD8B_DERIVED_CACHE_INTEGRATION_REVIEW_STATUS.md`](status/TD8B_DERIVED_CACHE_INTEGRATION_REVIEW_STATUS.md)
   — frozen TD-8B structure-only derived-cache review and verification evidence.
   [`status/TD8C_SESSION_REFERENCE_REPLAY_PARITY_STATUS.md`](status/TD8C_SESSION_REFERENCE_REPLAY_PARITY_STATUS.md)
   — uncommitted TD-8C shared session-reference replay parity and readiness assessment.
   [`status/TD8D_CANONICAL_MARKETSNAPSHOT_REPLAY_BRIDGE_STATUS.md`](status/TD8D_CANONICAL_MARKETSNAPSHOT_REPLAY_BRIDGE_STATUS.md)
   — canonical replay MarketSnapshot bridge and its dated readiness assessment.
   [`status/TD8E_FINAL_INTEGRATION_RESUME_STATUS.md`](status/TD8E_FINAL_INTEGRATION_RESUME_STATUS.md)
   — shared replay context, actual-consumer integration, and non-counting DEV_002 evidence.
12. [`PROJECT_CAPABILITY_COMPLETENESS.md`](PROJECT_CAPABILITY_COMPLETENESS.md) — a
   non-authorizing capability-completeness audit and navigation matrix (Section A
   trading edge, Section B operations/execution/platform, execution-authority matrix,
   qualification counters). It does not replace `PROJECT_STATUS.md`,
   `strategies/registry.yaml` / `strategies/STRATEGY_LEDGER.md`,
   `docs/VERSION_HISTORY.md`, or dated `docs/status/*.md` evidence — see its own top
   section for which source is authoritative for which claim.
13. [`status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md`](status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md)
   — owner authorization to begin the read-only 30-valid-observation BTC campaign;
   records the zero-count starting state and preserves all execution prohibitions.
14. [`status/AG_BTC_DAILY_REPORT_WINDOW_AMENDMENT_V1_STATUS.md`](status/AG_BTC_DAILY_REPORT_WINDOW_AMENDMENT_V1_STATUS.md)
   — prospective owner-approved move of the BTC report window to 13:00-13:15 MMT
   (06:30-06:45 UTC); no observation, execution, or scheduler activation.
15. [`status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md`](status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md)
16. [`market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE1_DESIGN.md`](market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE1_DESIGN.md),
    [`market_intelligence/MI_AUTHORITY_INVENTORY.json`](market_intelligence/MI_AUTHORITY_INVENTORY.json),
    [`market_intelligence/MI_V1_CONTRACT.md`](market_intelligence/MI_V1_CONTRACT.md),
    [`market_intelligence/MI_V1_INVARIANTS.md`](market_intelligence/MI_V1_INVARIANTS.md), and
    [`market_intelligence/MI_V1_MIGRATION_PLAN.md`](market_intelligence/MI_V1_MIGRATION_PLAN.md) — Cycle 1 MI design
    artifacts; design-only and non-authorizing.
17. [`market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE2_STATUS.md`](market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE2_STATUS.md)
    — Cycle 2 immutable MI core implementation and verification status.
18. [`market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE3_STATUS.md`](market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE3_STATUS.md)
    — Cycle 3 parity, temporal isolation, provenance, and fallback proof.
19. [`market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE4_STATUS.md`](market_intelligence/AG_MARKET_INTELLIGENCE_V1_CYCLE4_STATUS.md)
    — controlled SSC compatibility integration and decision parity evidence.
20. [`market_intelligence/AG_MARKET_INTELLIGENCE_V1_FREEZE_STATUS.md`](market_intelligence/AG_MARKET_INTELLIGENCE_V1_FREEZE_STATUS.md)
    and [`market_intelligence/MI_V1_RELEASE_MANIFEST.json`](market_intelligence/MI_V1_RELEASE_MANIFEST.json) — frozen
    MI V1 release contract and machine-readable manifest.
   — preflight architecture review and authorization packet for the next, separately
   authorized WP7 task (real Telegram message delivery); does not itself authorize
   `MESSAGE_DELIVERY` or any send.
16. [`status/AG_FRONTEND_SIMULATION_BOUNDARY_V1_STATUS.md`](status/AG_FRONTEND_SIMULATION_BOUNDARY_V1_STATUS.md)
   — records the frontend's explicit mock/real mode boundary, fail-closed legacy
   controls, verification limits, and unchanged trading authority.
17. [`status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md`](status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md)
   — verifies WP7 runtime is actually implemented (retry, attempt journal, conditional
   message-delivery closure), corrects stale "WP7 NOT STARTED" claims elsewhere,
   confirms `ARCHIVE_ONLY`/empty destination allow-list/zero real sends unchanged, and
   prepares (without executing) the next owner activation decisions.
18. [`status/AG_DETERMINISTIC_TRADING_SKILLS_REFACTOR_V1_STATUS.md`](status/AG_DETERMINISTIC_TRADING_SKILLS_REFACTOR_V1_STATUS.md)
   — records the observation-only skill classification/interface refactor and focused
   compatibility evidence.

## SVOS (Strategy Validation Operating System)

- [`svos/SVOS_AUTHORITY_MAP.md`](svos/SVOS_AUTHORITY_MAP.md) — P1 authority map:
  every SVOS domain resolved to its existing canonical authority (REUSE/EXTEND/CREATE).
- [`svos/SVOS_LIFECYCLE_AND_GATES.md`](svos/SVOS_LIFECYCLE_AND_GATES.md) — P2/P18
  lifecycle reconciliation onto `AG_VALIDATION_G0_G10_V1`, the full flow, and the
  required `BACKTEST≠FORWARD`, `VIRTUAL_FORWARD≠MT5_DEMO`, `PROPOSAL≠ORDER`,
  `DEMO_ELIGIBLE≠DEMO_EXECUTED` distinctions.
- [`status/AG_SSC_V1_0_1_SVOS_G2_POPULATION_STATUS.md`](status/AG_SSC_V1_0_1_SVOS_G2_POPULATION_STATUS.md)
  — SSC v1.0.1 one-shot G2 historical population over `SSC_V1_0_1_G2_DEV_002`
  (`POPULATION_V1` frozen, 22 occurrences, deterministic; G3 economic gate
  NOT_EVALUATED_UNSIGNED_CONTRACT; DEVELOPMENT evidence only).
- [`status/AG_SSC_V1_0_1_SVOS_G2_FAILURE_DECOMPOSITION_STATUS.md`](status/AG_SSC_V1_0_1_SVOS_G2_FAILURE_DECOMPOSITION_STATUS.md)
  — read-only, evidence-first failure decomposition of the frozen G2 population
  (`PRIMARY_ALPHA_DEFICIT` + `SECONDARY_AMPLIFIER` friction; no hypothesis justified).
- [`status/AG_SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md`](status/AG_SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md)
  — SSC v1.0.1 independent development replication admission preflight
  (`BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA`; DEV_003 not creatable).
- [`status/AG_SSC_V1_0_1_POST_G2_AUTHORITY_SYNC_STATUS.md`](status/AG_SSC_V1_0_1_POST_G2_AUTHORITY_SYNC_STATUS.md)
  — SSC v1.0.1 post-G2 authority synchronization (`AUTHORITY_SYNCHRONIZED`: registry
  DEV_002 = CONSUMED, SVOS context `G2 = POPULATION_FROZEN`, generator fail-closed).
- [`status/SSC_V1_0_1_ONE_YEAR_HISTORICAL_BACKTEST_STATUS.md`](status/SSC_V1_0_1_ONE_YEAR_HISTORICAL_BACKTEST_STATUS.md)
  — SSC v1.0.1 one-year historical backtest preflight
  (`BLOCKED_INCOMPLETE_ONE_YEAR_DATA`: no M1 `FILL_RESOLUTION_INPUT` before
  2026-05-18, so 245.3 days of any one-year EURUSD window are unreplayable; no replay,
  no population, `HISTORICAL_RESEARCH_ONLY`).
- [`status/SSC_V1_0_1_ONE_YEAR_M1_SOURCE_ADMISSION_STATUS.md`](status/SSC_V1_0_1_ONE_YEAR_M1_SOURCE_ADMISSION_STATUS.md)
  — admission search for that missing M1 leg (`NO_SUITABLE_LOCAL_SOURCE` →
  `OWNER_EXTERNAL_SOURCE_AUTHORIZATION_REQUIRED`: the broker's M1 retention no longer
  reaches 2025-09-15…2026-05-18 while M5/M15/H1 still do, so the blocker is M1-specific
  and no local file of any kind covers the interval).
- [`status/SSC_V1_0_1_ONE_YEAR_M1_ACQUISITION_STATUS.md`](status/SSC_V1_0_1_ONE_YEAR_M1_ACQUISITION_STATUS.md)
  — the acquisition that resolved that blocker (`READY_FOR_ONE_YEAR_REPLAY`): the blocker
  was the terminal's `MaxBars=100000` setting, not broker retention; after the owner
  raised it, the M1 leg was acquired from the same Vantage account, parity-proven
  `PASS_EXACT` against canonical M1 (43 292/43 292) with per-week seasonal offset
  resolution (`UTC+2/UTC+3`), and the canonical audit now returns
  `DATA_COVERAGE_COMPLETE` for 2025-09-15 → 2026-09-14. The one-year replay was **not**
  run.
- [`status/SSC_V1_0_1_ONE_YEAR_HISTORICAL_REPLAY_STATUS.md`](status/SSC_V1_0_1_ONE_YEAR_HISTORICAL_REPLAY_STATUS.md)
  — the one-year replay mission itself (R0–R17, `BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT`):
  coverage passed but the admissible H1/M15 legs are not in the same time base as the
  canonical M1 leg, so the timezone-consistent three-way intersection is 322.124 days
  instead of 365 and the mission stopped before the contract freeze and the single replay.
  Adds the companion gate
  [`scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py`](../scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py)
  — read-only, arbitrates every H1/M15 leg against the M1 authority and judges alignment
  per DST season; the coverage audit is necessary-but-not-sufficient and this gate is its
  required companion. No replay, no population, no metric, `HISTORICAL_RESEARCH_ONLY`.
- [`status/SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS.md`](status/SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS.md)
  — the remediation that clears that blocker (`CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED`):
  authoritative H1/M15 are derived deterministically from the frozen native MT5 M1
  authority using the repository's own existing `historical_replay.resampler` convention
  (adjudicated `AUTHORIZED`), with exact reference parity **1.000000** and zero unreproduced
  reference bars, so the timezone-consistent intersection spans the full window at zero
  shift. The one deliberate departure — the `NATIVE_FAITHFUL_INCLUSIVE` bucket policy — was
  frozen before generation and justified by native-candle parity (the strict default would
  silently drop 418 real H1 / 452 real M15 bars). Pre-existing DEV_002/GEN_002/HYP_002
  anomalies are recorded, **not** rewritten. No replay ran.
- [`status/SSC_V1_0_1_ONE_YEAR_REPLAY_DATA_AUTHORITY_STATUS.md`](status/SSC_V1_0_1_ONE_YEAR_REPLAY_DATA_AUTHORITY_STATUS.md)
  — Mission 1 (`ONE_YEAR_REPLAY_DATA_AUTHORITY_READY`): freezes
  `ONE_YEAR_REPLAY_STACK_V1` (M1/M15/H1 + a declared `WARMUP_CONTEXT_ONLY` H1 leg) via
  the new `scripts/build_ssc_v1_0_1_one_year_replay_stack.py`, hardens
  `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` in place (zero-shift-only
  admission, a calendar-independent bimodal DST census, season segments split at the two
  real EU DST transitions inside the window, single-season-source exclusion, and a
  conflict-detecting merge that never silently overwrites a disagreeing bar), and proves
  VA2 warm-up convergence (`WARMUP_STABLE`, 4 371 closed H1 bars before the first
  decision). No replay executed; R5/R6 remain a separate mission.

## Validation system

- [`validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1.md`](validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1.md)
  — fail-closed validation contract for friction and machine-testable assurance manifest
  proving contiguous gate ordering, protected-data firewall enforcement, and unavailable-cost
  handling.
- [`../artifacts/validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1_manifest.json`](../artifacts/validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1_manifest.json)
  — machine-testable assurance manifest.
- [`status/AG_VALIDATION_CYCLE_1_FOUNDATION_FREEZE_RECORD.md`](status/AG_VALIDATION_CYCLE_1_FOUNDATION_FREEZE_RECORD.md)
  — VA1 temporal/lookahead integrity freeze record.
- [`status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_R2_STATUS.md`](status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_R2_STATUS.md)
  — SVOS Virtual Demo Cycle 6A-R2: `VD_REALITY_REMEDIATION_READY` (bounded read-only
  EURUSD MT5 check, refreshed Vantage Demo/USD identity and stale spread snapshot).
- [`status/AG_R6_ECONOMIC_GATE_OWNER_REVIEW_V1.md`](status/AG_R6_ECONOMIC_GATE_OWNER_REVIEW_V1.md)
  — proposed economic-gate contract owner review packet (PROPOSED, unsigned).
- [`status/AG_R5_EVIDENCE_PIPELINE_STATUS.md`](status/AG_R5_EVIDENCE_PIPELINE_STATUS.md)
  and [`status/AG_R5_R6_READINESS_AUDIT_STATUS.md`](status/AG_R5_R6_READINESS_AUDIT_STATUS.md)
  — R5 evidence pipeline and R5/R6 readiness audit evidence.
- [`status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md`](status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md)
  — R2–R4 baseline reconciliation, WP0–WP12 acceptance, and platform-finalization
  remediation evidence.
- [`status/AG_DETERMINISTIC_TRADING_SKILLS_REFACTOR_V1_STATUS.md`](status/AG_DETERMINISTIC_TRADING_SKILLS_REFACTOR_V1_STATUS.md)
  — observation-only skill classification/interface refactor and compatibility evidence.
- [`status/AG_FRONTEND_SIMULATION_BOUNDARY_V1_STATUS.md`](status/AG_FRONTEND_SIMULATION_BOUNDARY_V1_STATUS.md)
  — frontend mock/real mode boundary and fail-closed legacy controls.
- [`status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md`](status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md)
  — WP7 runtime verification, attempt journal, conditional message-delivery closure.
- [`status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`](status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md)
  — WP1/WP3/WP6 core ticket-delivery foundation (identity, archive, delivery journal).
- [`status/AG_EXTERNAL_CANDIDATE_VALIDATION_LAYER_V1_STATUS.md`](status/AG_EXTERNAL_CANDIDATE_VALIDATION_LAYER_V1_STATUS.md)
  — external-candidate validation layer and research-factory governance hardening.
- [`status/AG_SVOS_HISTORICAL_TO_VIRTUAL_FORWARD_V1_STATUS.md`](status/AG_SVOS_HISTORICAL_TO_VIRTUAL_FORWARD_V1_STATUS.md)
  — SVOS historical→optimization→virtual-forward flow implementation and verification.
- [`status/AG_AGENT_CONTEXT_V1_FREEZE_STATUS.md`](status/AG_AGENT_CONTEXT_V1_FREEZE_STATUS.md)
  — agent context V1 freeze and routing manifest.
- [`status/AG_DAILY_OPPORTUNITY_SCHEDULER_V2_STATUS.md`](status/AG_DAILY_OPPORTUNITY_SCHEDULER_V2_STATUS.md)
  — daily opportunity scheduler V2 status.
- [`status/AG_POST_ASIAN_LONDON_PILOT_V1_STATUS.md`](status/AG_POST_ASIAN_LONDON_PILOT_V1_STATUS.md)
  — post-Asian London pilot V1 status.
- [`status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md`](status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md)
  and [`status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md`](status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md)
  — multi-strategy operational baseline and version promotion.
- [`status/AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1_STATUS.md`](status/AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1_STATUS.md)
  — two-stage golden vertical slice V1 status.
- [`status/AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md`](status/AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md)
  — ST_ASIAN_SWEEP_V1 governed SL geometry reconciliation.
- [`status/AG_LARGE_SMC_EURUSD_FRICTION_CAMPAIGN_WP3A1_STATUS.md`](status/AG_LARGE_SMC_EURUSD_FRICTION_CAMPAIGN_WP3A1_STATUS.md)
  and [`status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md`](status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md)
  — Large-SMC EURUSD friction campaign WP3A/3A.1 evidence.
- [`status/AG_LARGE_SMC_V1_FORWARD_OBSERVATION_RUNNER_IMPLEMENTATION_PLAN_STATUS.md`](status/AG_LARGE_SMC_V1_FORWARD_OBSERVATION_RUNNER_IMPLEMENTATION_PLAN_STATUS.md)
  and [`status/AG_LARGE_SMC_V1_FORWARD_RESEARCH_PROMOTION_STATUS.md`](status/AG_LARGE_SMC_V1_FORWARD_RESEARCH_PROMOTION_STATUS.md)
  — Large-SMC forward observation runner and research promotion.
- [`status/AG_LARGE_SMC_V1_FORWARD_TO_SHADOW_EVIDENCE_CONTRACT_V1_STATUS.md`](status/AG_LARGE_SMC_V1_FORWARD_TO_SHADOW_EVIDENCE_CONTRACT_V1_STATUS.md)
  — Large-SMC forward-to-shadow evidence contract.
- [`status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2_STATUS.md`](status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2_STATUS.md)
  and [`status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md`](status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md)
  — Large-SMC C10 stop-policy owner decision packets V2/V3.
- [`status/AG_BTC_VANTAGE_ECONOMIC_RECONCILIATION_V1_STATUS.md`](status/AG_BTC_VANTAGE_ECONOMIC_RECONCILIATION_V1_STATUS.md)
  — BTC Vantage economic reconciliation.
- [`status/AG_VANTAGE_MT5_CRYPTO_VENUE_V1.md`](status/AG_VANTAGE_MT5_CRYPTO_VENUE_V1.md)
  — Vantage MT5 crypto venue discovery.
- [`status/AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_E1_STATUS.md`](status/AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_E1_STATUS.md)
  — Vantage Markets crypto MT5 execution compatibility.
- [`status/AG_FRONTEND_OWNER_DECISION_REWIRE_STATUS.md`](status/AG_FRONTEND_OWNER_DECISION_REWIRE_STATUS.md)
  — frontend Owner Analysis panel rewired from fictional `/api/owner-analysis/*`
  endpoints to the real canonical proposal / opportunity-analysis / owner-decision
  API; documents the `DECISION_ID_CONTRACT_AMBIGUOUS` finding and its client-side-only
  mitigation, in-memory owner-key auth, and multi-proposal-per-symbol selection UX.
- [`status/AG_PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS_STATUS.md`](status/AG_PANEL_R5C_PROPOSAL_DECISION_UNIQUENESS_STATUS.md)
  — closes the `DECISION_ID_CONTRACT_AMBIGUOUS`/`PROPOSAL_LEVEL_OWNER_DECISION_UNIQUENESS
  = NOT_ENFORCED_BY_BACKEND` gap above: backend proposal-level at-most-one-authority
  invariant inside `owner_decision.bridge.OwnerDecisionStore`, atomic and durable,
  layered on the existing decision_id idempotency ledger.
- [`status/AG_FRONTEND_OWNER_DECISION_REWIRE_R1_REAUDIT_STATUS.md`](status/AG_FRONTEND_OWNER_DECISION_REWIRE_R1_REAUDIT_STATUS.md)
  and [`status/AG_PANEL_R5C_INDEPENDENT_AUDIT_STATUS.md`](status/AG_PANEL_R5C_INDEPENDENT_AUDIT_STATUS.md)
  — independent audit records for the two packages above.
- [`status/AG_MISSING_PLATFORM_PACKAGES_INTEGRATION_STATUS.md`](status/AG_MISSING_PLATFORM_PACKAGES_INTEGRATION_STATUS.md)
  — integration of the frontend rewire and R5C uniqueness into the platform lineage
  (cherry-pick provenance, current-tip semantic review, test and failure attribution).
- [`status/AG_GITHUB_REPOSITORY_SYNC_STATUS.md`](status/AG_GITHUB_REPOSITORY_SYNC_STATUS.md)
  — publication of the integrated platform lineage to `origin/main` (publication is
  not strategy, Demo or Live authorization).
- [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_BACKLOG_RECONCILIATION_STATUS.md),
  [`status/AG_ASIAN_SWEEP_RUNTIME_ERROR_PROVENANCE_RECONCILIATION_STATUS.md`](status/AG_ASIAN_SWEEP_RUNTIME_ERROR_PROVENANCE_RECONCILIATION_STATUS.md)
  and [`status/AG_ASIAN_SWEEP_MISSING_MANDATORY_EVIDENCE_STATUS.md`](status/AG_ASIAN_SWEEP_MISSING_MANDATORY_EVIDENCE_STATUS.md)
  — dated 2026-09-23 FX shadow Series 002 snapshots. The last one is the authoritative
  `classify_series` count. The 09-18 `VALID_DAY` claim in the provenance record conflicts
  with the classifier and is open.
- [`status/AG_MULTI_MARKET_STRATEGY_OS_RESOURCE_REUSE_DISCOVERY_V1_STATUS.md`](status/AG_MULTI_MARKET_STRATEGY_OS_RESOURCE_REUSE_DISCOVERY_V1_STATUS.md)
  — multi-market strategy OS resource reuse discovery.
- [`status/AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_STATUS.md`](status/AG_STRATEGY_TECH_SELECTIVE_PORT_AND_REUSE_STATUS.md)
  — strategy tech selective port and reuse.
- [`status/AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_V1_STATUS.md`](status/AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_V1_STATUS.md)
  — two-system architecture and open-source reuse.
- [`status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M0_M1_STATUS.md`](status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M0_M1_STATUS.md)
  and [`status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M2_M3_STATUS.md`](status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M2_M3_STATUS.md)
  — universal market direction architecture M0–M3.
- [`status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md`](status/AG_PROJECT_OBJECTIVE_ACCELERATION_V1_SECURITY_STATUS.md)
  — project objective acceleration security review.
- [`status/AG_RAW_PROSPECTIVE_ARCHIVE_V1_MISSION_STATUS.md`](status/AG_RAW_PROSPECTIVE_ARCHIVE_V1_MISSION_STATUS.md)
  — raw prospective archive V1 mission.
- [`status/AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS.md`](status/AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS.md)
  — intermittent PC catch-up contract audit.
- [`status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`](status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md)
  — Stage 1 catch-up and retry policy decision packet.
- [`status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md`](status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md)
  — WP7 message delivery preflight and authorization packet.
- [`status/AG_TRADE_ASSISTANT_V1_0_1_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_1_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_2_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_2_STATUS.md),
  and [`status/AG_TRADE_ASSISTANT_V1_0_3_BASELINE_FREEZE_BEFORE_FX_SERIES_002_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_BASELINE_FREEZE_BEFORE_FX_SERIES_002_STATUS.md)
  — Trade Assistant V1.0.1/V1.0.2/V1.0.3 baseline freeze evidence.
- [`status/AG_TRADE_ASSISTANT_V1_0_3_DAILY_REPORTING_HISTORY_AND_SCHEDULER_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_DAILY_REPORTING_HISTORY_AND_SCHEDULER_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_COMPLETE_ENTRY_TICKET_WIRING_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_COMPLETE_ENTRY_TICKET_WIRING_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_REMEDIATION_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_REMEDIATION_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_002_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_002_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md),
  [`status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md`](status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md)
  — Trade Assistant V1.0.3 release qualification evidence (daily reporting, entry ticket,
  release identity, report decision-key, shadow days, validation, MT5 data readiness,
  operational preflight, manifest freeze, qualification blockers).
- [`status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md`](status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md)
  and [`status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md`](status/AG_V1_0_3_BTC_OBSERVATION_CAMPAIGN_AUTHORIZATION_STATUS.md)
  — BTC daily operationalization and observation campaign authorization.
- [`status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md`](status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md)
  — Bybit qualification exception and BTC daily decision V3.
- [`status/AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1_STATUS.md`](status/AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1_STATUS.md)
  — BTC daily observation time contract V1.
- [`status/AG_BTC_DAILY_REPORT_WINDOW_AMENDMENT_V1_STATUS.md`](status/AG_BTC_DAILY_REPORT_WINDOW_AMENDMENT_V1_STATUS.md)
  — BTC daily report window amendment V1.
- [`status/AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1_STATUS.md`](status/AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1_STATUS.md)
  — Bybit BTC market data and daily decision V1.
- [`status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`](status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md)
  — Stage 1 exactly-once FX ticket foundation.
- [`status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md`](status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md)
  — Stage 1 WP7 readiness reconciliation.
- [`status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md`](status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md)
  — Stage 1 WP7 message delivery preflight and authorization packet.
- [`status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`](status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md)
  — Stage 1 catch-up and retry policy decision packet.
- [`status/AG_RESEARCH_FACTORY_V1_GOVERNANCE_HARDENING_STATUS.md`](status/AG_RESEARCH_FACTORY_V1_GOVERNANCE_HARDENING_STATUS.md)
  — Research Factory V1 governance hardening.
- [`status/SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1.md`](status/SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1.md)
  — SSC v1.0.1 semantic and replication confound audit.
- [`status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md`](status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md)
  — True Stage 2 oracle reconciliation.
- [`status/LARGE_SMC_FROZEN_CONTRACT_DRIFT_ADJUDICATION_STATUS.md`](status/LARGE_SMC_FROZEN_CONTRACT_DRIFT_ADJUDICATION_STATUS.md)
  and [`status/LARGE_SMC_SHARED_VALIDATION_FREEZE_SCOPE_REMEDIATION_STATUS.md`](status/LARGE_SMC_SHARED_VALIDATION_FREEZE_SCOPE_REMEDIATION_STATUS.md)
  — Large-SMC frozen contract drift adjudication and shared validation freeze scope remediation.
- [`status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md)
  and [`status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md)
  — Large-SMC C10 stop-loss and pending-entry expiry decision packets.
- [`status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`](status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md)
  — Large-SMC outcome lifecycle V1.
- [`status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`](status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md)
  and [`status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`](status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md)
  — Large-SMC MT5 symbol metadata replay gap and decoupling fix.
- [`status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`](status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md)
  and [`status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`](status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md)
  — Large-SMC C14 occurrence identity candidate and hardening.
- [`status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`](status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md)
  — Large-SMC research funnel V1.
- [`status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md)
  and [`status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md)
  — Large-SMC C11 contract finalization and C12 expiry contract resolution.
- [`status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md)
  — Large-SMC C14 duplicate reentry contract resolution.
- [`status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md`](status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md)
  — Large-SMC 3x3 variant authority reconciliation.
- [`status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md`](status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md)
  — Large-SMC UC-001 timeframe decision.
- [`status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md`](status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md)
  — Large-SMC strategy specification status.
- [`status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md)
  — Large-SMC C11 target model resolution.
- [`status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md`](status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md)
  — shared evidence strategy architecture.
- [`status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`](status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md)
  — complete trade opportunity V1 remediation.
- [`status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md`](status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md)
  — scheduler and Large-SMC watch hardening.
- [`status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md`](status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md)
  — versioned proposal occurrence identity candidate.
- [`status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md`](status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md)
  — FX occurrence identity promotion readiness.
- [`status/PROJECT_LIVE_STATUS.md`](status/PROJECT_LIVE_STATUS.md)
  — generated live status snapshot (regenerate with `python scripts/generate_live_status.py`).
- [`status/RECONCILIATION_AUDIT_POST_BB6AC0F.md`](status/RECONCILIATION_AUDIT_POST_BB6AC0F.md)
  — reconciliation audit post-bb6ac0f.

## Architecture

- [`architecture/TRADE_ASSISTANT_ARCHITECTURE.md`](architecture/TRADE_ASSISTANT_ARCHITECTURE.md)
  — system responsibilities, execution authority, and runtime flow.
- [`architecture/ARCHITECTURE_CONFLICT_AUDIT.md`](architecture/ARCHITECTURE_CONFLICT_AUDIT.md)
  — recorded architecture conflicts and their disposition.
- [`architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`](architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md)
  — D-drive strategy provenance and agent-skill workflow organization.
- [`architecture/DETERMINISTIC_TRADING_SKILLS.md`](architecture/DETERMINISTIC_TRADING_SKILLS.md)
  — canonical separation of deterministic observations, strategy decisions, AI diagnostics,
  governance, and authorized execution.

Architecture descriptions do not override Strategy YAML, frozen specifications, or
the execution gates in code and configuration.

## Specifications

The `specs/` directory contains behavior contracts. The most useful entry points are:

- [`specs/AG_RESEARCH_FACTORY_V1_GOVERNANCE_SPEC.md`](specs/AG_RESEARCH_FACTORY_V1_GOVERNANCE_SPEC.md)
  — normative physical-candidate persistence, one-shot Holdout, canonical-import, parity,
  and authorization-separation contract.

- [`specs/SESSION_TRADE_V1_SPEC.md`](specs/SESSION_TRADE_V1_SPEC.md)
- [`specs/LARGE_SMC_V1_SPEC.md`](specs/LARGE_SMC_V1_SPEC.md)
- [`specs/TRADE_MANAGEMENT_V1_SPEC.md`](specs/TRADE_MANAGEMENT_V1_SPEC.md)
- [`specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md`](specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md)
- [`specs/SMC_ASSISTANT_RUNTIME_V1_SPEC.md`](specs/SMC_ASSISTANT_RUNTIME_V1_SPEC.md)
- [`specs/SMC_CONDITIONAL_ENTRY_V2_RUNTIME_SPEC.md`](specs/SMC_CONDITIONAL_ENTRY_V2_RUNTIME_SPEC.md)
- [`specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md`](specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md)
- [`specs/ENTRY_CONFIRMATION_V1_SPEC.md`](specs/ENTRY_CONFIRMATION_V1_SPEC.md),
  [`specs/ENTRY_CONFIRMATION_V2_SPEC.md`](specs/ENTRY_CONFIRMATION_V2_SPEC.md), and
  [`specs/ENTRY_CONFIRMATION_V2_1_SPEC.md`](specs/ENTRY_CONFIRMATION_V2_1_SPEC.md)

Versioned specifications coexist intentionally. Check `PROJECT_STATUS.md` and the
matching status document before assuming a version is active or frozen.

## Status and evidence

Files in `status/` are dated evidence snapshots. They preserve the test counts and
observations from the named milestone; they are not rolling dashboards.

- [`status/AG_PROJECT_AUDIT_AND_CLEANUP_2026-09-25.md`](status/AG_PROJECT_AUDIT_AND_CLEANUP_2026-09-25.md)
  — repository health audit, test-failure classification, root-file relocation map
  (root MI/V2/validation docs now live under `market_intelligence/`, `v2/`,
  `validation/`), and the recommended fastest path to the R5/R6 objective.
- [`status/AG_POST_MERGE_DEMO_VERTICAL_SLICE_QUALIFICATION_STATUS.md`](status/AG_POST_MERGE_DEMO_VERTICAL_SLICE_QUALIFICATION_STATUS.md)
  — prepare-only post-merge qualification (2026-09-25): discovered and fixed a
  PR #4 merge gap (10 resolved review threads whose fix commit never reached
  `main`, closed by PR #5), security/diagnostic check PASS, 71/71 focused
  regression PASS. Runtime/real-MT5/execution/reconciliation phases explicitly
  deferred (`POST_MERGE_RUNTIME_BLOCKED`, by scope choice, not failure); flags
  the still-live legacy `/api/execution/manual-demo` route as a P0 blocker for
  any future real Demo order submission.
- [`status/AG_MANUAL_DEMO_ROUTE_CONTAINMENT_FINAL_STATUS.md`](status/AG_MANUAL_DEMO_ROUTE_CONTAINMENT_FINAL_STATUS.md)
  — Gate 1 of post-merge demo qualification (2026-09-25): retires the
  `/api/execution/manual-demo` P0 bypass flagged above (410
  `EXECUTION_ROUTE_RETIRED`, 12-case HTTP containment matrix, sentinel positive
  control, bypass-surface audit finding 0 unsafe routes). Not yet published.

> **Index completeness note (2026-09-21):** The `docs/status/` directory contains
> ~140 status documents. This index lists the most commonly referenced entries but
> is not exhaustive. For a complete listing, see the directory itself. The
> authoritative current state is always `PROJECT_STATUS.md`; individual status
> documents are historical evidence. Key documents referenced from the current
> rolling classification are listed below; older or superseded documents may not
> appear here but remain valid historical evidence.

- Runtime: [`status/ASSISTANT_RUNTIME_V1.md`](status/ASSISTANT_RUNTIME_V1.md),
  [`status/ASSISTANT_RUNTIME_V1_STATUS.md`](status/ASSISTANT_RUNTIME_V1_STATUS.md), and
  [`status/FIVE_SKILL_ASSISTANT_RUNTIME_STATUS.md`](status/FIVE_SKILL_ASSISTANT_RUNTIME_STATUS.md)
- SMC validation: [`status/SMC_SKILL_VALIDATION.md`](status/SMC_SKILL_VALIDATION.md),
  [`status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md`](status/SMC_ASSISTANT_READY_TO_USE_V1_STATUS.md),
  [`status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md`](status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md),
  and [`status/SMC_TRAP_GUARD_V1_STATUS.md`](status/SMC_TRAP_GUARD_V1_STATUS.md)
- Frozen phases: [`status/PHASE_1_4_FREEZE_STATUS.md`](status/PHASE_1_4_FREEZE_STATUS.md)
  and [`status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`](status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md)
- Session Sweep Continuation research validation
  (`ST_SESSION_SWEEP_CONTINUATION_V1`):
  [`status/AG_SSC_HYP001_CONTROL_ARM_COMPARABILITY_AMENDMENT_STATUS.md`](status/AG_SSC_HYP001_CONTROL_ARM_COMPARABILITY_AMENDMENT_STATUS.md),
  [`status/AG_SSC_HYP001_LINEAGE_AUDIT_STATUS.md`](status/AG_SSC_HYP001_LINEAGE_AUDIT_STATUS.md),
  [`status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md`](status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md),
  [`status/AG_SSC_HYP002_SETUP_SELECTIVITY_VALIDATION_STATUS.md`](status/AG_SSC_HYP002_SETUP_SELECTIVITY_VALIDATION_STATUS.md)
  (first preregistered hypothesis completed and falsified on GEN_002; HYP_002 closed
  `VALIDATED_NEGATIVE`, duplicate HYP_003 declined),
  [`status/AG_SSC_SVOS_G0_G8_EVIDENCE_RECONCILIATION_STATUS.md`](status/AG_SSC_SVOS_G0_G8_EVIDENCE_RECONCILIATION_STATUS.md),
  [`status/AG_SSC_V1_0_1_SVOS_G2_POPULATION_STATUS.md`](status/AG_SSC_V1_0_1_SVOS_G2_POPULATION_STATUS.md)
  (G2 population frozen: 22 occurrences, deterministic),
  [`status/AG_SSC_V1_0_1_SVOS_G2_FAILURE_DECOMPOSITION_STATUS.md`](status/AG_SSC_V1_0_1_SVOS_G2_FAILURE_DECOMPOSITION_STATUS.md)
  (PRIMARY_ALPHA_DEFICIT + SECONDARY_AMPLIFIER friction; no hypothesis justified),
  [`status/AG_SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md`](status/AG_SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md)
  (BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA),
  [`status/AG_SSC_V1_0_1_POST_G2_AUTHORITY_SYNC_STATUS.md`](status/AG_SSC_V1_0_1_POST_G2_AUTHORITY_SYNC_STATUS.md)
  (AUTHORITY_SYNCHRONIZED)
- Registry and skills: [`status/STRATEGY_REGISTRY_STATUS.md`](status/STRATEGY_REGISTRY_STATUS.md),
  [`status/LARGE_SMC_V1_REGISTRATION_STATUS.md`](status/LARGE_SMC_V1_REGISTRATION_STATUS.md),
  [`status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md`](status/STRATEGY_WORKFLOW_RESOURCE_AUDIT_STATUS.md),
  and [`status/SKILL_OPTIMIZATION_STATUS.md`](status/SKILL_OPTIMIZATION_STATUS.md)
- Large-SMC contract resolution (`ST_LARGE_SMC_V1`, still `RESEARCH_DRAFT`):
  [`status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md`](status/AG_SHARED_EVIDENCE_STRATEGY_ARCHITECTURE_V1_STATUS.md),
  [`status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md`](status/ST_LARGE_SMC_V1_STRATEGY_SPECIFICATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md`](status/ST_LARGE_SMC_V1_UC_001_TIMEFRAME_DECISION.md),
  [`status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md`](status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`](status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`](status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md),
  [`status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`](status/ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md) (correction: C14 downgraded to `PARTIALLY_RESOLVED`),
  [`status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`](status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md) (M-candidate identity implemented, Option B),
  [`status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`](status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md) (research-only engine, v1.0.5),
  [`status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md), and
  [`status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`](status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md) (C10 still unsigned; pending-entry expiry resolved as of v1.0.6, see below),
  [`status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`](status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md) (v1.0.6, pending-entry lifecycle), and
  [`status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`](status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md) (discovered gap, resolved same day), and
  [`status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`](status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md) (the fix, parity proof, corrected-replay evidence)
- Scheduler + Large-SMC watch hardening (2026-09-20):
  [`status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md`](status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md)
  (weekday window-bounded FX `--once` scheduling with fail-closed gates and frozen
  friction-window protection; duplicate-proposal identity-layer audit; confirmed
  broker-time-alignment and non-incremental-watch defects fixed research-only with
  native-broker D1/H4 parity tests; watch lifecycle as a canonical projection)
- Versioned proposal occurrence identity (2026-09-20):
  [`status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md`](status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md)
  (`AG_PROPOSAL_OCCURRENCE_IDENTITY_V1` candidate, **unwired**: occurrence-scoped
  proposal identity so repeated M15 observations of one unchanged setup resolve to one
  occurrence; authoritative-identity-only with fail-closed families; read-time expiry
  presentation; four distinct reporting metrics. Promotion not recommended yet — see the
  document's own promotion section)
- FX occurrence identity promotion readiness (2026-09-20):
  [`status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md`](status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md)
  (`FX_IDENTITY_PROMOTION_READY_FOR_SCOPED_WIRING`: `setup_id` authority proven structural
  end to end through the real producers; occurrence parity proven for all nine required
  cases; forward-only cutover designed with an explicit version marker; expiry-corrected
  count promoted into the runtime status probe; six distinct metrics with one consistent
  identity gate; SSC left fail-closed. Candidate still **not wired** into FX proposal
  production)
- Opportunity coverage: [`status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`](status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md)
  (FX `LONDON_NEWYORK` pilot activation; BTC Binance USDT-M market-data adapter,
  multi-occurrence research collection, and execution-domain gate)
- BTC daily production path: [`contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`](contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md),
  [`status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md`](status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md), and
  [`status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md`](status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md)
  (frozen UTC contract, public/read-only Bybit adapter, production-data-connectivity-confirmed scheduler-ready
  daily decision and informational proposal-ticket path; crypto execution disabled)

When a historical test total differs from the current baseline, retain the historical
number and use `PROJECT_STATUS.md` for the latest result.

`PROJECT_STATUS.md` is the only rolling status page. A dated status document may be
superseded, but it must not be silently rewritten to look current. Follow
[`status/LIVE_STATUS_MAINTENANCE.md`](status/LIVE_STATUS_MAINTENANCE.md) whenever code,
configuration, execution authority, or validation evidence changes operational status.

## Strategy documentation

[`../strategies/STRATEGY_LEDGER.md`](../strategies/STRATEGY_LEDGER.md) indexes registered
strategies and unresolved strategy-authorship decisions. Strategy YAML remains the
authoritative machine-readable source.
# Status evidence

- [AG V2 pre-architecture baseline + core contracts](status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md)
  (additive `src/opportunity/` contracts: MarketEvent, funnel vocabulary,
  OpportunityCandidate, ProposalEligibilityDecision, StrategyBinding, shared
  evidence contracts; no canonical duplication, no authority change; see also
  `v2/AG_V2_BASELINE_MANIFEST_V1.json`)
- [AG V2-2A/V2-2B pure funnel engine + candidate store](status/AG_V2_2A_2B_IMPLEMENTATION_STATUS.md)
  (`VERIFIED`, 2026-09-21: identity continuity, semantic no-op detection, terminal
  stickiness, restart-safe persistence)
- [AG V2-3A/V2-3B Large-SMC + SSC shadow adapters and parity checkpoint](status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md)
  (`IMPLEMENTED_AND_LOCALLY_VERIFIED`, 2026-09-22: thin adapters over each
  strategy's existing canonical authority, semantic parity evidence, known
  mapping-decision debt; parity checkpoint `READY_FOR_INDEPENDENT_AUDIT`,
  `SAFE_TO_ADVANCE_TO_V2_4 = NO` pending that audit)
- [Web-to-Vantage Demo execution bridge](status/AG_WEB_VANTAGE_DEMO_EXECUTION_BRIDGE_V1.md)
