---
class: status_evidence
state: IMPLEMENTED
owner_reviewed: null
review_by: 2026-11-07
---

# Import-resolution audit — 2026-10-10

Audited origin/main `7f3e75d8bbb4a7c119a9be7279bf6d2f5badd003`; 478 tracked Python files. Includes nested, conditional, try/except, and literal dynamic imports. Tracked module/package initializers are graph edges. Stdlib and declared distributions (including Windows-only MetaTrader5 in pyproject.toml) are excluded. The graph starts at scripts/host/live_candles_smoke.py and conservatively includes all imports in its four mode paths; it is import reachability, not proof that a function is called. No unknown computed dynamic-import targets found.

DEPLOY_BLOCKER chains:
- assistant.market_data: scripts/host/live_candles_smoke.py → src/large_smc_watch/watch.py → src/large_smc_watch/detect.py → src/supply_demand/__init__.py → src/supply_demand/native_zones.py → assistant.market_data
- historical_replay.data_source_patch: scripts/host/live_candles_smoke.py → src/v1_tickets/crypto.py → src/strategy_engine/sweep_retest/engine.py → src/market_structure/__init__.py → src/market_structure/analyzer.py → historical_replay.data_source_patch
- historical_replay.dataset_identity: scripts/host/live_candles_smoke.py → src/v1_tickets/crypto.py → src/strategy_engine/sweep_retest/engine.py → src/market_structure/__init__.py → src/market_structure/analyzer.py → historical_replay.dataset_identity

The table includes every importing location, not only one example per module. DEAD_IMPORT means unreachable from this runner, not globally unused. No dead import was fixed and this PR remains draft.

| Module | Importer | Reachable | Classification |
|---|---|---|---|
| `alerting.sink` | `scripts/run_daytrading_runtime.py:24` | no | DEAD_IMPORT |
| `assistant.analysis_models` | `scripts/analyze_trade.py:26` | no | DEAD_IMPORT |
| `assistant.assessment` | `scripts/analyze_trade.py:27` | no | DEAD_IMPORT |
| `assistant.canonical_state` | `scripts/analyze_trade.py:28` | no | DEAD_IMPORT |
| `assistant.market_data` | `src/supply_demand/native_zones.py:31` | yes | DEPLOY_BLOCKER |
| `assistant.technique_router` | `scripts/analyze_trade.py:29` | no | DEAD_IMPORT |
| `backtesting` | `research_external/adapters/backtesting_py.py:23` | no | DEAD_IMPORT |
| `backtesting` | `research_external/run_s2r_baseline.py:319` | no | DEAD_IMPORT |
| `canonical_experiments` | `scripts/run_canonical_experiments.py:15` | no | DEAD_IMPORT |
| `canonical_experiments.population` | `scripts/run_canonical_experiments.py:16` | no | DEAD_IMPORT |
| `canonical_experiments.runner` | `scripts/run_canonical_experiments.py:17` | no | DEAD_IMPORT |
| `canonical_experiments.splits` | `scripts/run_canonical_experiments.py:18` | no | DEAD_IMPORT |
| `daytrading.models` | `scripts/analyze_trade.py:30` | no | DEAD_IMPORT |
| `daytrading_runtime.conditional_entry_snapshot` | `scripts/run_eligibility_reconstruction.py:25` | no | DEAD_IMPORT |
| `daytrading_runtime.coordinator` | `scripts/run_daytrading_runtime.py:25` | no | DEAD_IMPORT |
| `daytrading_workflow.universe` | `scripts/run_daytrading_runtime.py:26` | no | DEAD_IMPORT |
| `execution.executor` | `scripts/execute_trade.py:37` | no | DEAD_IMPORT |
| `execution.models` | `scripts/execute_trade.py:38` | no | DEAD_IMPORT |
| `execution.risk` | `scripts/replay_candidate_model_a_session_range_25.py:51` | no | DEAD_IMPORT |
| `execution.runtime_context` | `scripts/run_ag_execution_runtime.py:32` | no | DEAD_IMPORT |
| `execution_runtime.cycle` | `scripts/run_ag_execution_runtime.py:34` | no | DEAD_IMPORT |
| `execution_runtime.data_provider` | `scripts/run_ag_execution_runtime.py:33` | no | DEAD_IMPORT |
| `execution_runtime.startup` | `scripts/run_ag_execution_runtime.py:35` | no | DEAD_IMPORT |
| `fx_friction_research.c10_friction_ratios` | `scripts/aggregate_eurusd_friction_campaign.py:20` | no | DEAD_IMPORT |
| `fx_friction_research.cost_model` | `scripts/generate_fx_friction_stress_evidence.py:34` | no | DEAD_IMPORT |
| `fx_friction_research.provenance` | `scripts/generate_fx_friction_stress_evidence.py:35` | no | DEAD_IMPORT |
| `fx_friction_research.spread_evidence` | `scripts/aggregate_eurusd_friction_campaign.py:21` | no | DEAD_IMPORT |
| `fx_friction_research.spread_evidence` | `scripts/collect_eurusd_spread_evidence.py:22` | no | DEAD_IMPORT |
| `fx_friction_research.spread_evidence` | `scripts/run_eurusd_friction_campaign_window.py:21` | no | DEAD_IMPORT |
| `historical_replay` | `scripts/run_directional_liquidity_reconstruction.py:19` | no | DEAD_IMPORT |
| `historical_replay` | `scripts/run_discovery_backtest.py:24` | no | DEAD_IMPORT |
| `historical_replay` | `scripts/run_eligibility_reconstruction.py:26` | no | DEAD_IMPORT |
| `historical_replay` | `scripts/run_historical_replay.py:21` | no | DEAD_IMPORT |
| `historical_replay.candle_store` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/build_ssc_v1_0_1_one_year_replay_stack.py:51` | no | DEAD_IMPORT |
| `historical_replay.candle_store` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_warmup_convergence_gate.py:33` | no | DEAD_IMPORT |
| `historical_replay.candle_store` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:41` | no | DEAD_IMPORT |
| `historical_replay.candle_store` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:35` | no | DEAD_IMPORT |
| `historical_replay.data_source_patch` | `scripts/generate_determinism_evidence.py:178` | no | DEAD_IMPORT |
| `historical_replay.data_source_patch` | `scripts/run_directional_liquidity_reconstruction.py:20` | no | DEAD_IMPORT |
| `historical_replay.data_source_patch` | `scripts/run_eligibility_reconstruction.py:27` | no | DEAD_IMPORT |
| `historical_replay.data_source_patch` | `src/market_structure/analyzer.py:42` | yes | DEPLOY_BLOCKER |
| `historical_replay.dataset_identity` | `src/market_structure/analyzer.py:43` | yes | DEPLOY_BLOCKER |
| `historical_replay.m1_derivation` | `scripts/derive_ssc_one_year_h1_m15_from_m1.py:35` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/acquire_ssc_one_year_m1_mt5.py:45` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py:50` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/build_ssc_v1_0_1_one_year_replay_stack.py:35` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/derive_ssc_one_year_h1_m15_from_m1.py:44` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:42` | no | DEAD_IMPORT |
| `historical_replay.mt5_export_loader` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:36` | no | DEAD_IMPORT |
| `historical_replay.orchestrator` | `scripts/run_directional_liquidity_reconstruction.py:21` | no | DEAD_IMPORT |
| `historical_replay.orchestrator` | `scripts/run_discovery_backtest.py:25` | no | DEAD_IMPORT |
| `historical_replay.orchestrator` | `scripts/run_eligibility_reconstruction.py:28` | no | DEAD_IMPORT |
| `historical_replay.orchestrator` | `scripts/run_historical_replay.py:22` | no | DEAD_IMPORT |
| `historical_replay.stage1` | `scripts/build_native_stage1.py:14` | no | DEAD_IMPORT |
| `historical_replay.stage2` | `scripts/run_directional_liquidity_reconstruction.py:22` | no | DEAD_IMPORT |
| `historical_replay.symbol_metadata_manifest` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_warmup_convergence_gate.py:34` | no | DEAD_IMPORT |
| `historical_replay.symbol_metadata_manifest` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:43` | no | DEAD_IMPORT |
| `historical_replay.symbol_metadata_manifest` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:37` | no | DEAD_IMPORT |
| `historical_replay.timebase_arbiter` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/build_ssc_v1_0_1_one_year_replay_stack.py:52` | no | DEAD_IMPORT |
| `historical_replay.timebase_arbiter` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_cross_leg_timebase_gate.py:22` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/build_ssc_v1_0_1_one_year_replay_stack.py:50` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_warmup_convergence_gate.py:35` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/acquire_ssc_one_year_m1_mt5.py:46` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/adjudicate_ssc_1y_m1_gap_source.py:45` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:38` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py:51` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py:50` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/build_ssc_v1_0_1_g2_dev_002.py:26` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/build_ssc_v1_0_1_one_year_replay_stack.py:36` | no | DEAD_IMPORT |
| `historical_replay.utc_export_csv_loader` | `scripts/derive_ssc_one_year_h1_m15_from_m1.py:45` | no | DEAD_IMPORT |
| `historical_replay.warmup_merge` | `scripts/build_ssc_v1_0_1_one_year_replay_stack.py:37` | no | DEAD_IMPORT |
| `historical_replay.warmup_readiness` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/build_ssc_v1_0_1_one_year_replay_stack.py:53` | no | DEAD_IMPORT |
| `historical_replay.warmup_readiness` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_warmup_convergence_gate.py:36` | no | DEAD_IMPORT |
| `historical_replay.warmup_readiness` | `scripts/build_ssc_v1_0_1_g2_dev_002.py:27` | no | DEAD_IMPORT |
| `historical_replay.warmup_readiness` | `scripts/build_ssc_v1_0_1_one_year_replay_stack.py:38` | no | DEAD_IMPORT |
| `large_smc_research.engine` | `scripts/generate_determinism_evidence.py:179` | no | DEAD_IMPORT |
| `market_data_readiness.scanner` | `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py:51` | no | DEAD_IMPORT |
| `mt5.account` | `scripts/check_mt5.py:22` | no | DEAD_IMPORT |
| `mt5.account` | `scripts/manage_trade.py:19` | no | DEAD_IMPORT |
| `mt5.connection` | `research_external/tooling/mt5_capture.py:22` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/analyze_structure.py:22` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/analyze_trade.py:32` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/check_mt5.py:23` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/collect_eurusd_spread_evidence.py:21` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/execute_trade.py:39` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/manage_positions.py:27` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/manage_trade.py:20` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/replay_candidate_model_a_session_range_25.py:48` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/resolve_forward_shadow_outcomes.py:96` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/run_ag_execution_runtime.py:36` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/run_daytrading_runtime.py:27` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/run_eurusd_friction_campaign_window.py:20` | no | DEAD_IMPORT |
| `mt5.connection` | `scripts/run_fx_session_daytrade.py:39` | no | DEAD_IMPORT |
| `performance.adapters.fx_adapter` | `scripts/generate_economic_evidence_report.py:24` | no | DEAD_IMPORT |
| `performance.calculator` | `research_external/run_s2r_baseline.py:29` | no | DEAD_IMPORT |
| `performance.calculator` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:32` | no | DEAD_IMPORT |
| `performance.calculator` | `scripts/generate_economic_evidence_report.py:25` | no | DEAD_IMPORT |
| `performance.calculator` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:42` | no | DEAD_IMPORT |
| `performance.cost_model` | `scripts/generate_economic_evidence_report.py:26` | no | DEAD_IMPORT |
| `performance.models` | `research_external/run_s2r_baseline.py:30` | no | DEAD_IMPORT |
| `performance.models` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:33` | no | DEAD_IMPORT |
| `performance.models` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:43` | no | DEAD_IMPORT |
| `post_asian_pilot.daily_fx_report` | `scripts/run_fx_daily_report.py:31` | no | DEAD_IMPORT |
| `post_asian_pilot.fingerprint` | `research_external/run_s2r_baseline.py:28` | no | DEAD_IMPORT |
| `post_asian_pilot.fingerprint` | `research_external/tools/partitions.py:10` | no | DEAD_IMPORT |
| `post_asian_pilot.fingerprint` | `scripts/generate_determinism_evidence.py:36` | no | DEAD_IMPORT |
| `post_asian_pilot.pipeline` | `scripts/run_fx_session_daytrade.py:40` | no | DEAD_IMPORT |
| `post_asian_pilot.preflight` | `scripts/run_fx_session_daytrade.py:41` | no | DEAD_IMPORT |
| `post_asian_pilot.report` | `scripts/run_fx_session_daytrade.py:42` | no | DEAD_IMPORT |
| `proposals.identity` | `scripts/run_eligibility_reconstruction.py:31` | no | DEAD_IMPORT |
| `research.session_lifecycle` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:34` | no | DEAD_IMPORT |
| `research.session_lifecycle` | `scripts/export_ssc_svos_context.py:167` | no | DEAD_IMPORT |
| `research.session_lifecycle` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:44` | no | DEAD_IMPORT |
| `session_sweep_continuation` | `scripts/export_ssc_svos_context.py:39` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/adjudicate_ssc_1y_m1_gap_source.py:46` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:35` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py:57` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/build_ssc_v1_0_1_g2_dev_002.py:28` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:48` | no | DEAD_IMPORT |
| `session_sweep_continuation.config` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:47` | no | DEAD_IMPORT |
| `session_sweep_continuation.h1_bias` | `docs/plans/AG_mission1_extract/AG_mission1_package/mission1_materials/code/test_warmup_convergence_gate.py:37` | no | DEAD_IMPORT |
| `session_sweep_continuation.h1_bias` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:49` | no | DEAD_IMPORT |
| `session_sweep_continuation.h1_bias` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:48` | no | DEAD_IMPORT |
| `session_sweep_continuation.regime` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:36` | no | DEAD_IMPORT |
| `session_sweep_continuation.replay` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:50` | no | DEAD_IMPORT |
| `session_sweep_continuation.replay` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:49` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/adjudicate_ssc_1y_m1_gap_source.py:47` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py:37` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py:58` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/build_ssc_v1_0_1_g2_dev_002.py:29` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/reconstruct_route_b_phase1_occurrence_population.py:51` | no | DEAD_IMPORT |
| `session_sweep_continuation.sessions` | `scripts/run_first_canonical_session_sweep_continuation_replay.py:50` | no | DEAD_IMPORT |
| `session_trading_source_v1` | `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S3_BLIND_REPLAY/run_blind_replay.py:11` | no | DEAD_IMPORT |
| `session_trading_source_v1.asian_range` | `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S3_BLIND_REPLAY/run_blind_replay.py:7` | no | DEAD_IMPORT |
| `session_trading_source_v1.models` | `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S3_BLIND_REPLAY/run_blind_replay.py:8` | no | DEAD_IMPORT |
| `session_trading_source_v1.occurrence` | `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S3_BLIND_REPLAY/run_blind_replay.py:10` | no | DEAD_IMPORT |
| `session_trading_source_v1.sweep` | `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S3_BLIND_REPLAY/run_blind_replay.py:9` | no | DEAD_IMPORT |
| `strategy_engine.session.candidate_stop_models` | `scripts/replay_candidate_model_a_session_range_25.py:52` | no | DEAD_IMPORT |
| `test_golden_vertical_slice` | `scripts/generate_determinism_evidence.py:177` | no | DEAD_IMPORT |
| `trade_management.claims` | `scripts/manage_positions.py:28` | no | DEAD_IMPORT |
| `trade_management.claims` | `scripts/manage_trade.py:22` | no | DEAD_IMPORT |
| `trade_management.manager` | `scripts/manage_positions.py:29` | no | DEAD_IMPORT |
| `trade_management.position_monitor` | `scripts/manage_trade.py:23` | no | DEAD_IMPORT |
| `validation_framework.adapters.btc_adapter` | `scripts/generate_economic_evidence_report.py:27` | no | DEAD_IMPORT |
| `validation_framework.adapters.btc_adapter` | `scripts/generate_validation_ledger_snapshot.py:28` | no | DEAD_IMPORT |
| `validation_framework.adapters.fx_adapter` | `scripts/generate_economic_evidence_report.py:28` | no | DEAD_IMPORT |
| `validation_framework.adapters.fx_adapter` | `scripts/generate_fx_friction_stress_evidence.py:36` | no | DEAD_IMPORT |
| `validation_framework.adapters.fx_adapter` | `scripts/generate_validation_ledger_snapshot.py:29` | no | DEAD_IMPORT |
| `validation_framework.adapters.large_smc_adapter` | `scripts/generate_economic_evidence_report.py:29` | no | DEAD_IMPORT |
| `validation_framework.adapters.large_smc_adapter` | `scripts/generate_validation_ledger_snapshot.py:30` | no | DEAD_IMPORT |
| `validation_framework.ag_validation_methodology` | `scripts/onboard_large_smc_eurusd_admission_wp2.py:26` | no | DEAD_IMPORT |
| `validation_framework.ag_validation_methodology` | `scripts/onboard_large_smc_portability_wp1.py:38` | no | DEAD_IMPORT |
| `validation_framework.evidence_reconciliation` | `scripts/export_ssc_svos_context.py:31` | no | DEAD_IMPORT |
| `validation_framework.ledger` | `scripts/generate_validation_ledger_snapshot.py:31` | no | DEAD_IMPORT |
| `validation_framework.svos_context_export` | `scripts/export_ssc_svos_context.py:37` | no | DEAD_IMPORT |
| `validation_framework.svos_contracts` | `scripts/export_ssc_svos_context.py:36` | no | DEAD_IMPORT |
| `validation_framework.svos_contracts` | `scripts/onboard_large_smc_eurusd_admission_wp2.py:27` | no | DEAD_IMPORT |
| `validation_framework.svos_contracts` | `scripts/onboard_large_smc_portability_wp1.py:39` | no | DEAD_IMPORT |
| `validation_framework.validation_admission` | `scripts/onboard_large_smc_eurusd_admission_wp2.py:28` | no | DEAD_IMPORT |
| `validation_framework.validation_admission` | `scripts/onboard_large_smc_portability_wp1.py:40` | no | DEAD_IMPORT |
| `validation_framework.validation_gate_state` | `scripts/export_ssc_svos_context.py:38` | no | DEAD_IMPORT |

Verdict: NOT_DEPLOY_READY. Three reachable unresolved imports; 158 unreachable import locations.

## Guard and deletion history

All three modules are absent in both 9419b21d66eaf026dce29b4218eaaed3cdde73a0 and
audited main. Their files exist in 3f1f955^ and are deleted by
3f1f9550dd23740bc5e0fb996e5a281ae0531658 (`git show --name-status`):
- src/assistant/market_data.py
- src/historical_replay/data_source_patch.py
- src/historical_replay/dataset_identity.py

3f1f955 is on 9419b21's first-parent history. GitHub's commit-to-PR endpoint
`/repos/aungmyat1/AG-profit-trading-assit/commits/3f1f955/pulls` returns `[]`.
No PR is associated by that API; a deletion PR is UNVERIFIED. The commit message
is `feat: initialize project structure` and describes project configuration,
trading domain types/service mocks, and Tailwind/UI foundations. It does not
explain removal of these Python modules. Intentional deletion vs mistake is
UNVERIFIED; do not infer intent from a broad commit title.

`assistant.market_data`: deferred HARD import in `session_zone`,
src/supply_demand/native_zones.py:31, outside any try/except. Missing import raises;
it provides no ZoneResult fallback. Recommendation OWNER_DECISION: restoration
may be appropriate, but deletion intent and the desired session-zone authority
are not established. No runtime code changed.

`historical_replay.data_source_patch` and `historical_replay.dataset_identity`:
hard imports in `_structure_cache_key` (src/market_structure/analyzer.py:42-43),
but its only call is guarded by try/except Exception at :102-109. On import
failure cache_key becomes None; execution continues through fresh candle-to-dataframe
and SMC calculation (:111-144), skips cache storage (:146), and returns the
fresh result (:151). This changes caching, not the computation of analyzer facts
for the same fetched candles/config. It does not construct fallback zone output.
Recommendation REMOVE_DEPENDENCY in a separate reviewed change: remove the cache
helper's dependency on the absent replay package and preserve the existing fresh
computation path. No runtime code changed or economic authority inferred here.

Under the owner's conservative static-graph rule, all three remain DEPLOY_BLOCKER
because conditional/deferred imports are included. Two guarded cache imports are
not hard startup failures; the hard session-zone import raises if that function
is invoked. The shared graph is a union across fx/crypto/lsmc/lsmc-weekend, not
a function-call graph or evidence of an actual broker invocation.

## Tech-debt recording

158 unreachable importing locations are recorded in the strategy ledger as
DEAD_IMPORT technical debt with this table as the complete location inventory.
Their reachability classification is limited to this entry point. They are not
claimed globally unused and no code fixes are included.
