"""AG_TIME_NORMALIZATION_V1 -- the canonical time-normalization contract.

No owner previously froze this in one place; it was implied across market_data.py and
broker_time.py's module docstrings. This module documents it explicitly, strictly from
already-implemented behavior verified during the Phase 1-4 freeze pass (2026-08-27) --
it does not change normalization behavior itself except for the one fix noted below.

RAW MT5 INPUT
=============
`rates[i]["time"]` from `MetaTrader5.copy_rates_*` is a `numpy.int64` epoch-seconds
value (verified live: EURUSD/GBPUSD/USDJPY/XAUUSD all return `numpy.int64`). Verified
empirically (see broker_time.py's module docstring) that this epoch, read naively via
`datetime.utcfromtimestamp()`, reproduces the BROKER'S OWN WALL CLOCK reading of that
bar's open -- it is not already true UTC unless the broker's server happens to run on
UTC. Confusing "epoch seconds" (an absolute instant) with "already-UTC" is exactly the
mistake this contract exists to prevent: the raw int is absolute, but the wall-clock
STRING it decodes to under a naive read is the broker's local reading, not UTC's.

CONVERSION BOUNDARY (single source of truth)
=============================================
Exactly one function performs the broker-wall-clock -> true-UTC conversion for a given
raw epoch: `mt5.market_data`'s inline
    (datetime.utcfromtimestamp(int(r["time"])) - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
repeated identically in `get_candles()`, `get_latest_candles()`, and `get_tick()` --
three call sites, one formula (not three independent implementations that could drift).
`offset` always comes from `mt5.broker_time.detect_broker_utc_offset_hours()`
(memoized per-symbol by `market_data._broker_offset_hours()`), itself the ONLY place
the weekly-reopen-gap heuristic is implemented. No other module reimplements this.

`mt5.market_data._to_broker_epoch()` is the inverse direction (true UTC -> broker-wall-
clock epoch), used only by `get_candles()` to build the request range. It exists
because passing a naive `datetime` straight to `copy_rates_range()` gets silently
reinterpreted through THIS MACHINE's own system timezone by the MetaTrader5 python
module (a distinct, previously-fixed bug -- see market_data.py's module comment) --
passing an integer epoch sidesteps that reinterpretation entirely.

INTERNAL REPRESENTATION
========================
`strategy_engine.session.Candle.time`: a timezone-AWARE `datetime` with
`tzinfo=timezone.utc`, always. Every downstream module (market_structure, supply_demand,
liquidity, session_clock) consumes this field as-is -- none of them re-derive a broker
offset or re-interpret the value. `session_clock.py` builds its own session-boundary
datetimes directly in UTC (`datetime.combine(..., tzinfo=timezone.utc)`) and compares
them against candle/tick times of the same tzinfo; no second conversion authority exists.

TIMEZONE
========
UTC, always, both for the canonical `Candle.time` field and for `Tick.time_utc`. No
naive datetime is allowed to cross the `mt5.market_data` module boundary outward --
`get_candles()` rejects naive `start_utc`/`end_utc` inputs (`NAIVE_DATETIME_REJECTED`).
Naive datetimes are used ONLY transiently, inside `broker_time.py` and inside
`market_data.py`'s two conversion functions, and never escape those modules.

SESSION CONSUMER EXPECTATION
=============================
`session_clock.py` (CANONICAL_SESSION_WINDOWS_V1) assumes every timestamp it is handed
is already true UTC and performs no further conversion -- it is a pure hour-of-day
comparison against `config/canonical_sessions.yaml`. This is only correct because the
market-data layer guarantees UTC-normalized candles/ticks per this contract; if that
guarantee were ever violated, session boundaries would silently misclassify without
either module raising an error (this is exactly why the fix below matters, even though
it does not change the observed offset for currently-fetchable history).

SERIALIZATION
=============
No canonical on-disk/wire serialization format is defined by this contract -- `Candle`
is a project-internal dataclass, not currently serialized to JSON/CSV by any Phase 1-4
module. Not a gap being filled here; simply out of scope until something needs it.

FIX APPLIED THIS PASS (generic, not symbol-specific)
=====================================================
`broker_time.detect_broker_utc_offset_hours()` finds "the weekly reopen gap" as the
largest inter-bar time gap in the fetched history, then derives the offset from the
first bar after it. Before this pass, ties for "largest gap" (routine: an ordinary feed
with no market holidays produces an identically-sized gap every week) resolved to the
OLDEST tied gap, because `max(gaps, key=lambda g: g[0])` keeps the first item it sees
on a tie. Anchoring on an old reopen is a latent correctness risk: if a DST transition
happened between that old week and now, the derived offset would be quietly wrong
without raising any error. Fixed by `_largest_gap()` to prefer the MOST RECENT tied
gap (`key=lambda g: (g[0], g[1])`). This applies identically to every symbol -- it is
not, and must never become, a per-symbol special case.

The one live `TIME_NORMALIZATION_ERROR` observed for USDJPY during the prior Phase 4
pass could not be reproduced across 7+ repeated live calls after this fix (all
succeeded, offset=3 consistently, matching EURUSD/GBPUSD/XAUUSD on the same server).
No second, distinct defect was found in the conversion pipeline itself. See
docs/status/PHASE_1_4_FREEZE_STATUS.md's Root Cause section for the full account, including what
was and wasn't confirmed.
"""

CONTRACT_VERSION = "AG_TIME_NORMALIZATION_V1"
