# TD-8B derived cache integration review — 2026-09-19

Status: `COMPLETE_SCOPED`, owner-approved for freeze. Branch `main`; starting
HEAD `4a04a47bf116c5c9888922f29fb739fb25fe89eb`. No trading authority changed.

## Audit

TD-6's `derived_fact_cache.build_key` previously used `(symbol, timeframe,
closed_bar_identity, authority_definition_id, feature_version, parameters)` and was
unwired. This could collide across live and replay, across replay datasets with the
same timestamps, and across changed candle content with the same last bar time.
TD-8B makes `source_dataset_identity` required and uses a closed-data identity
containing the actual last fetched candle time and SHA-256 of the entire fetched
OHLCV population. Replay also carries the caller's as-of boundary. The existing
`BoundedCache` remains the sole derived-cache store.

## Authority classification

| Authority | Classification | Inputs and reason |
| --- | --- | --- |
| `market_structure.analyze_structure` | `CACHE_SAFE_NOW` | Shared `SMC_MARKET_STRUCTURE_V1`; closed candles, effective count/fetch count, swing length, close-break, config default, smc version, source and replay clock can be keyed completely. Live and replay both use the same detector. Only `VALID` results are stored. |
| `liquidity.liquidity_result` | `DEFER` | Tick, symbol metadata, nested structure, three sessions, previous day/week, and current reference price affect output. Session replay parity is incomplete. |
| `supply_demand.fair_value_gaps_for` | `CACHE_SAFE_AFTER_ADAPTER` | Closed candles and `join_consecutive` can be keyed, but its own semantic/version identity and complete query adapter are not yet integrated. |
| `supply_demand.validated_order_blocks_for` | `CACHE_SAFE_AFTER_ADAPTER` | Closed candles, structure swing length, mitigation mode, FVG candidates and every `AGOrderBlockConfig` field must be keyed. No adapter was added in this scope. |
| `supply_demand.native_zones.session_zone` and session references | `DEFER` | Wall-clock driven `session_snapshot` remains unavailable in historical replay (`TD8_SESSION_REFERENCE_REPLAY_PARITY`). |

The cache is below strategy interpretation. `SMC_MARKET_STRUCTURE_V1`, SSC structure,
and Sweep-Retest MSS remain distinct; no strategy-owned detector is imported into
shared cache code.

## Integrated key and failure policy

`source_dataset_identity`: `LIVE_MT5` or `REPLAY:` plus TD-8's per-series
`ReplayDatasetIdentity` token (including the content SHA-256 fingerprint).
`symbol` and `timeframe`: explicit. `closed_data_identity`: actual last candle open
time, as-of boundary for replay, and SHA-256 of the fetched candle window. The
fingerprint covers time, OHLC, and volume, so timestamp-only collisions do not reuse
results. `authority_definition_id`: `SMC_MARKET_STRUCTURE_V1`.
`feature_version`: `MARKET_STRUCTURE_ANALYZER_TD8B_V1`.
`parameters`: effective analysis count, fetch count, swing length, close-break,
default analysis count, and installed smartmoneyconcepts version. Code changes require
a feature-version increment before a same-process reload; normal process restart
starts with an empty cache.

The authority fetches candles before lookup. A failed fetch or insufficient-history
result is never cached. Unexpected key/lookup/storage failures fall back to normal
computation or return the already computed result; the cache cannot authorize or
fabricate a market fact. `StructureResult` is immutable.

## Proof and limits

Focused tests establish miss then hit for identical live and replay calls, one
derived computation instead of two, input/content/parameter/version/boundary misses,
live-versus-replay and replay-A-versus-replay-B isolation, future-candle invisibility,
cache-failure recomputation, and unchanged result equality. The prior H1 target made
two structure computations from one raw fetch; it now makes one of each for identical
requests. Other H1 context construction remains duplicated (`TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE`).
Verification on 2026-09-19, Windows / Python 3.14:

- `python -m pytest -q --disable-warnings tests/test_td8b_structure_derived_cache.py`:
  3 passed.
- `python -m pytest -q --disable-warnings tests/test_shared_cache_derived_fact_cache.py tests/test_shared_cache_no_strategy_import_guard.py tests/test_td6_deterministic_dedup_targets.py tests/test_td8b_structure_derived_cache.py tests/test_topdown_composer_replay.py tests/test_historical_replay_no_lookahead.py`:
  68 passed (before the two additional key-contract assertions were added).
- `python -c "import glob,subprocess,sys; prefixes=('market_structure','liquidity','supply_demand','topdown','mtf_context','historical_replay','shared_cache','td6','td8b'); p=sum((glob.glob('tests/test_'+x+'*.py') for x in prefixes),[]); print('files',len(p),flush=True); sys.exit(subprocess.call([sys.executable,'-m','pytest','-q','--disable-warnings',*p]))"`:
  404 passed, 1 skipped across 31 files. This includes the final key-contract tests,
  TD-8 temporal/replay tests, strategy-adjacent liquidity tests, and the import guard.

No live broker or holdout data was used for this proof. Live behavior was exercised
with synthetic candles and mocked MT5 boundaries; it is unit-tested, not live-verified.

Carried forward: `TD8_SESSION_REFERENCE_REPLAY_PARITY`,
`TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE`, `TD4_CONTEXT_FEATURE_VERSION_REVIEW`,
`FULL_SWING_HISTORY_LIMITATION`, `FX_FRIDAY_CLOSE_TEST_GUARD`, and
`ST_LARGE_SMC_BASELINE_MISMATCH`.

Next: TD-8C session-reference replay parity review. TD-9 has not begun.
