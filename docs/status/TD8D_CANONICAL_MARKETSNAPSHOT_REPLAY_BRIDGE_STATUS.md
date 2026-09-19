# TD-8D canonical MarketSnapshot replay bridge — 2026-09-19

Status: `COMPLETE_SCOPED`, uncommitted for owner review. TD-8C freeze commit:
`d4f2aa785a92fd15fbb0bf9e9541daca6a90948d`.

`strategy_contract.replay_bridge.build_replay_market_snapshot` is the single small
adapter from the frozen replay context to the existing canonical
`strategy_contract.MarketSnapshot`. It requires a loaded `HistoricalCandleStore`, a
timezone-aware caller `as_of_time`, and an identity for the requested symbol and
timeframe. It reads one genuinely closed candle at T inside
`historical_data_context`, constructs the existing `MarketSnapshot` in `REPLAY`
mode, and attaches the shared TD-8C session snapshots for Asian, London AM, and New
York AM at that same T. It creates no new snapshot contract, clock, replay store, or
session detector.

The immutable `ReplayMarketSnapshot` carries the canonical snapshot, the TD-8
dataset token, T, and session facts. Its deterministic identity includes dataset,
symbol, timeframe, T, and the visible candle fingerprint. `deliver()` passes the
same object instance to any independent consumer callbacks, proving input identity
without requiring output agreement. Future dataset changes after T can alter
provenance, but cannot alter the visible snapshot or session facts. Missing data,
forming bars, and naive T fail closed. Replay never calls live MT5 through the
existing TD-8C context.

The bridge has no imports from proposal, risk, execution, Telegram, frontend,
Market Intelligence, or strategy decision modules. The Asian Sweep and SSC frozen
contracts remain consumers with their own strategy-specific reference/trade rules;
the bridge only supplies shared canonical state and does not normalize their windows.

Focused TD-8D tests cover same-object two-consumer delivery, same-T future mutation,
dataset provenance isolation, changed-T identity, missing/naive input rejection,
session-fact association, and the import firewall. The existing TD-8C and TD-8B
tests remain required gates. Market Intelligence implementation remains out of scope.

The foundation gate is now `MI_FOUNDATION_READY` for the eight TD-8D prerequisites:
one canonical replay snapshot can reach multiple consumers; T is caller-controlled;
closed-data visibility and session parity are enforced; dataset provenance and
semantic boundaries are explicit; future changes are invisible at T; and replay has
zero live fallback. This is a readiness result only and does not begin
`AG_MARKET_INTELLIGENCE_V1`.

Verification on 2026-09-19, Windows / Python 3.14:

- `python -m pytest -q --disable-warnings tests/test_td8d_replay_market_snapshot_bridge.py tests/test_td8c_session_replay_parity.py tests/test_td8b_structure_derived_cache.py tests/test_historical_replay_no_lookahead.py`: **35 passed**.
- The immediately preceding TD-8C/TD-8B/affected regression gate passed **491 passed,
  4 skipped across 38 files**; TD-8D adds only the bridge package and focused tests.

No live broker, holdout data, strategy population, proposal, risk, or execution path
was accessed.
