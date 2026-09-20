# AG_MARKET_INTELLIGENCE_V1 — Cycle 4 controlled SSC integration

`FINAL_CLASSIFICATION = MI_V1_INTEGRATION_READY`

## Baseline and canonical identity

- Branch: `main`
- HEAD before: `727a2a4` (contains MI Cycle 3 `2597547`)
- TD-8E `f4a1045`, Cycle 1 `93586ec`, Cycle 2 `cbb6a43`, and Cycle 3 `2597547` are ancestors.
- Canonical SSC: `ST_SESSION_SWEEP_CONTINUATION_V1@1.0.1`.
- Canonical decision implementation: `session_sweep_continuation.replay.run_replay`.
- HEAD after: the scoped Cycle 4 integration commit.
- Unrelated WIP remained untouched.

## SSC consumption map

| SSC input | Classification | Evidence |
|---|---|---|
| M15 replay candles | MI_ADAPTED_AUTHORITATIVE | Read from the admitted TD-8E context; no recalculation |
| Optional M1 outcome candles | MI_ADAPTED_AUTHORITATIVE | Read only when M1 participates in the event |
| H1 MarketBiasResult | MI_ADAPTED_AUTHORITATIVE | Existing H1 bias authority is supplied unchanged |
| M15 RegimeResult | STRATEGY_LOCAL_EXISTING_AUTHORITY | Existing SSC regime skill remains the source |
| Config, session windows, pip semantics | STRATEGY_LOCAL_EXISTING_AUTHORITY | Existing SSC configuration and replay code |
| EMA / cross-strategy regime | UNAVAILABLE_NOT_REQUIRED | Not required by the compatibility adapter |
| Entry, stop, target, risk, execution | STRATEGY_LOCAL_EXISTING_AUTHORITY | Remain inside unchanged `run_replay`; no MI fields added |

## Adapter and parity proof

`build_ssc_compatibility_context()` validates event, symbol, as-of, higher-timeframe
evidence, and bias scope, then passes bound M15/M1 candles and existing bias/regime
objects to unchanged `run_replay`. It does not detect, interpret, or rewrite features.

Representative complete event (infrastructure-only, no economic use): EURUSD DEV_002,
`T = 2026-06-23T11:00:00Z`, with H1/M15/M1 admitted by TD-8E. H1 bias and M15 regime
were observed at the canonical reference close. Legacy `run_replay` and the MI-backed
adapter returned equal `ReplayResult` values, including setup classification, campaign
and direction, rejection fields, and step records.

Failure and safety cases passed: missing MI higher-timeframe evidence rejects;
different context identity rejects; raw MT5 candle APIs were patched to raise and had
zero calls; M1 lineage remained explicit.

## Regression

Focused Cycle 4: `python -m pytest -q tests/test_market_intelligence_v1_cycle4_ssc.py` — **3 passed**.

Combined Cycle 2/3, TD-8E, provenance, session, and SSC canonical regression:
`python -m pytest -q tests/test_market_intelligence.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_market_intelligence_v1_cycle4_ssc.py tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_td8d_replay_market_snapshot_bridge.py tests/test_td8c_session_replay_parity.py tests/test_historical_replay_no_lookahead.py tests/test_historical_replay_dataset_identity.py tests/test_session_sweep_continuation_replay_determinism.py tests/test_session_sweep_continuation_canonical_observations.py` — **117 passed**.

This proves software/context/decision parity only. It does not prove economic edge,
profitability, Demo or Live eligibility, or live/replay runtime parity. No SSC production
cutover occurred. No strategy parameter, entry/stop/target semantic, execution authority,
optimization, DEV_002 economic evidence, population, holdout, or OOS state changed.
