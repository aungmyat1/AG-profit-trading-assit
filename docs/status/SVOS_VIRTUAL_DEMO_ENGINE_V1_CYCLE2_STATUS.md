# SVOS Virtual Demo Engine V1 Cycle 2 — Virtual Time and Feed

Date: 2026-09-20. Classification: **VD_TIME_FEED_READY** (`UNIT_TESTED` temporal infrastructure only).

## Baseline and scope

HEAD before/after: `415d0622b82a8bedbabdc620d018969cec51c2cb` (uncommitted change set). The MI release manifest pins TD-8E `f4a1045` and MI commits `93586ec`, `cbb6a43`, `2597547`, `c435dba`; ancestry checks passed. Cycle 1 design/contracts and component map were present as uncommitted WIP before Cycle 2 and were left untouched. No other pre-existing WIP was changed. This change adds `src/svos/virtual_time.py`, `tests/test_svos_virtual_time_cycle2.py`, this status, and index/rolling-status entries.

## Authority and behavior

`VirtualClock` owns only bounded monotone UTC T and deterministic end state. `VirtualMarketFeed` accepts only `HistoricalCandleStore`, binds all requested M1/M15/H1 series through TD-8E `ReplayEvaluationContext`, schedules candidate close instants using the existing `timeframe_duration`, and emits **only** candles returned by `context.candles(timeframe)` at that T. TD-8E remains the visibility and dataset-identity authority; MI and SSC semantics are unchanged. Each event preserves symbol, timeframe, source, dataset ID/fingerprint, bar sequence, TD-8E replay event ID, content identity, and full-lineage identity.

Events at a shared T sort by `(availability/close T, source ID, series sequence, event ID)`. The sequence hash includes full dataset lineage; a separate semantic sequence hash uses only visible payloads, allowing future-only mutations to retain visible semantics while changing TD-8E's full-series identity. Playback modes `step`, `accelerated`, and `maximum` use the same step reducer; only an optional wall-clock sleep callback differs. The feed does not import MT5 or live source APIs.

## Proofs

- Incremental M1/M15/H1 closure and shared-time ordering were compared with fresh TD-8E contexts at each emitted T. No event candle appeared before its close.
- Two fixtures equal through T=01:00 UTC but different afterward produced equal event times/payloads and semantic sequence hashes through T; dataset lineage/sequence hashes differed as TD-8E requires. Their admitted context candles and MI quality agreed; MI provenance retained differing dataset identities.
- Three playback modes produced identical count, order, virtual timestamps, payload IDs, final T, and sequence hash.
- Reversing historical series load order left the event sequence hash unchanged.
- End of data is idempotent and ends at configured T. Missing requested series, invalid clock bounds, and bound-series replacement fail closed. The existing historical store states that gap audits are a caller precondition; this cycle does not claim a new gap-quality certification.
- Monkeypatched raw/live MT5 `get_candles`, `get_latest_candles`, and `get_tick` recorded zero calls.

## Verification

Windows PowerShell, Python/pytest, controlled in-memory fixtures, no broker account or venue.

- `python -m pytest -q tests/test_svos_virtual_time_cycle2.py` → **8 passed**.
- `python -m pytest -q tests/test_td8e_evaluation_context.py tests/test_td8e_ssc_reference_completeness.py tests/test_td8e_shared_consumer_integration.py tests/test_market_intelligence_v1_core.py tests/test_market_intelligence_v1_cycle3_parity.py tests/test_market_intelligence_v1_cycle4_ssc.py` → **31 passed**.

## Unresolved and safety

Only sourced candle close is available as publication time in the current TD-8E store. Source-specific publication lag and external quality manifests must be admitted before a sealed campaign. Gap/completeness certification remains upstream data-quality work. No VirtualExchange, fill, account, P&L, economic metric, optimization, qualification access/campaign, protected dataset, Demo/Live order, MI/TD-8E/SSC semantic change, or execution-authority change occurred.
