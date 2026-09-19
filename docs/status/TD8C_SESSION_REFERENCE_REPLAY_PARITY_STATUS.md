# TD-8C session-reference replay parity — 2026-09-19

Status: `COMPLETE_SCOPED`, uncommitted for owner review. TD-8B freeze commit:
`51bb224b375890e25500469441c70b74fee205cf` on `main`.

## Authority audit

`session_clock.py` is the shared authority for `CANONICAL_SESSION_WINDOWS_V1`:
UTC, fixed clock, half-open windows: Asian 00:00–06:00, London AM 06:00–11:00,
New York AM 12:00–15:00. `assistant.market_data.session_snapshot` is the shared
session OHLC/range/completeness authority. `supply_demand.session_zone` delegates to
it; H1/M15 TopDownContext and liquidity consume the resulting reference levels.
Before TD-8C, `session_snapshot` chose a date and completeness from wall clock and
called the live MT5 range API. Replay patched that API to fail closed, so session
ReferenceLevelFacts were absent even when the replay store had complete M15 data.

The two frozen strategy contracts separately define ASIAN_LONDON and
LONDON_NEWYORK. Their reference windows align with canonical Asian and London AM.
ASIAN_LONDON's trade window begins at 07:00, one hour after canonical London AM
begins; LONDON_NEWYORK's trade window is 12:00–15:00. This distinction remains
unchanged. Strategy reference-box calculations remain strategy-owned and receive
the same legally visible closed M15 candle population in the consumer parity tests;
TD-8C does not replace their rules with `session_snapshot` output.

## Parity contract and implementation

Inside `historical_data_context(store, T)`, `session_snapshot` uses T for both its
default UTC date and completeness. Once the canonical session is complete, it reads
the existing `HistoricalCandleStore` through a half-open range method that returns
only M15 candles with `open + 15 minutes <= T`. The existing snapshot calculation
then derives high, low, open, close, midpoint, range, and exact expected-bar status
from that population. It returns `SESSION_INCOMPLETE`, `DATA_MISSING`, or
`INSUFFICIENT_CANDLES` where appropriate, with no live fallback. An unadapted
arbitrary range query remains blocked in replay. The live branch still calls the
same `mt5.market_data.get_candles` function with the same canonical bounds.

The replay dataset's full content fingerprint remains distinct under TD-8; future
bars do not enter a session result at T. Session/reference caching remains `DEFER`:
no session result is stored in TD-6's derived cache, and its complete identity and
invalidation contract have not been separately proven. TD-8B's structure-only cache
is unchanged.

## Proof and limitations

Deterministic tests cover before/during/exact close and the interval through trade
open/during/exact close/after for ASIAN_LONDON and LONDON_NEWYORK; frozen strategy
trade-window boundaries are asserted separately. They cover explicit Friday
reference selection on Saturday, absence of a fabricated Saturday session,
forming-bar exclusion, missing and short replay series, same-T future-candle
mutation, and equal live/replay snapshot fields for the same closed M15 candles.
Both frozen strategy reference consumers produce the same high/low from the same
visible fixture. Existing TD-8/TD-8B temporal and cache tests remain regression
gates. No live broker, holdout data, or strategy population is used.

`AG_MARKET_INTELLIGENCE_V1` foundation status: `MI_FOUNDATION_BLOCKED`.
The shared session-reference fact now has historical parity. The existing canonical
`strategy_contract.market_snapshot.MarketSnapshot` has a replay constructor, but
there is no proven adapter that binds its caller-supplied `source` and `retrieved_at`
to TD-8's `ReplayDatasetIdentity` and T, then supplies that same snapshot together
with the shared session facts to multiple independent models. The two frozen
strategy consumers retain separate configuration and data adapters. This assessment
does not start Market Intelligence work.

Readiness by invariant: canonical snapshot fanout = `BLOCKED`; deterministic T,
closed-data visibility, session/reference replay parity, dataset identity, semantic
authority separation, future-leak protection, and zero live MT5 fallback = `PROVEN`
for the shared TopDown/session replay path. The existing MarketSnapshot contract is
available, but binding and distributing one dataset-identified snapshot to multiple
models is work for the next program, not TD-8C.

Carried forward unchanged: `TD_TECH_DEBT_H1_RAW_CONTEXT_EXPOSURE`,
`TD4_CONTEXT_FEATURE_VERSION_REVIEW`, `FULL_SWING_HISTORY_LIMITATION`,
`FX_FRIDAY_CLOSE_TEST_GUARD`, `ST_LARGE_SMC_BASELINE_MISMATCH`.

Verification on 2026-09-19, Windows / Python 3.14:

- `python -m pytest -q --disable-warnings tests/test_td8c_session_replay_parity.py tests/test_historical_replay_no_lookahead.py tests/test_assistant_market_data.py tests/test_supply_demand.py`:
  39 passed, 3 skipped (before the final trade-window and naive-clock assertions).
- `python -m pytest -q --disable-warnings tests/test_td8c_session_replay_parity.py tests/test_historical_replay_no_lookahead.py tests/test_topdown_composer_replay.py tests/test_td8b_structure_derived_cache.py`:
  60 passed (before the final trade-window and naive-clock assertions).
- `python -c "import glob,subprocess,sys; prefixes=('market_structure','liquidity','supply_demand','topdown','mtf_context','historical_replay','shared_cache','td6','td8b','td8c'); p=sum((glob.glob('tests/test_'+x+'*.py') for x in prefixes),[]); p += ['tests/test_assistant_market_data.py','tests/test_session_clock.py','tests/test_strategy_engine.py','tests/test_strategy_engine_canonical_observations.py','tests/test_session_sweep_continuation_sessions.py','tests/test_session_sweep_continuation_canonical_observations.py']; print('files',len(p),flush=True); sys.exit(subprocess.call([sys.executable,'-m','pytest','-q','--disable-warnings',*p]))"`:
  491 passed, 4 skipped across 38 files. The run began before the final naive-clock
  guard and trade-window assertions; the final focused rerun is recorded below.
- `python -m pytest -q --disable-warnings tests/test_td8c_session_replay_parity.py tests/test_historical_replay_no_lookahead.py`:
  27 passed after the final guard and boundary assertions.

No TD-9 or Market Intelligence implementation was begun.
