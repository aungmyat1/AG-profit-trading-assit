---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# PR #94 follow-up — S01 strategy identity, S02 digest source match (2026-10-09)

This is the corrective follow-up to merged PR #94 (STALE-FIX-1, merge `205832a`). It
resolves the two open review findings on that PR. It makes no change to execution or
broker behavior. `strategies/` and `src/strategy_engine/` are untouched.

## S01 — strategy identity (classification: TICKET-LAYER; owner confirmation pending)

| Question | Evidence | Finding |
|---|---|---|
| Did #94 change the strategy engine or contract? | `git diff --stat d7b4995 205832a -- src/strategy_engine strategies` is empty | No. `TradeSignal` output for identical candles is unchanged. |
| Does the v1.1.1 contract define a signal time? | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` has no signal-time, expiry or TREND entry rule. Phase B row B-REGIME records that the YAML declares sweep entries only. | The removed `post_session_candles[0].time` fallback was a ticket-builder invention, not a contract rule. |
| Who sets `signal_timestamp=None`? | `src/strategy_engine/session/setups.py` (box-direction TREND, `entry_1`), intentionally | The engine says "no signal time". The ticket layer now reports that truthfully (`DATA_ERROR` / `SIGNAL_TIME_UNAVAILABLE`) instead of fabricating a time. |
| Is historical evidence reattributed? | Tickets since #94 carry `signal_time_source` (`ENGINE` / `MISSING` / `NOT_APPLICABLE`). Records written before #94 lack the field. | Records without `signal_time_source` stay attributed to the pre-#94 application version and are not rewritten or regraded. |

**Recommendation:** a ticket-layer correctness fix. No new strategy version is needed,
because strategy semantics (engine and contract) are unchanged. This recommendation is not
a decision. The owner register records it as **`REG-S01-SIGNAL-TIME` (PENDING_OWNER)**.
If the owner instead rules it a contract change, the remedy is a candidate strategy version
under admission governance, and nothing here pre-empts that.

## S02 — digest reason matches the selected record's source

**Defect.** `build_session_summary` chose the reason event by `(ticket_id, decision)` only.
When LIVE and REPLAY rows share a ticket id and decision, `_latest_record` picks the LIVE
row. However, if the REPLAY event was recorded last, the digest still reported the REPLAY
event's reason.

**Fix** (`scripts/host/canonical_fx_delivery.py`):

- Reason lookup now uses a second index keyed by `(ticket_id, decision, source)` and matches
  the selected row's own source.
- When no event matches that source, the reason falls back to the selected record's
  `block_reasons`, never to another source's event.
- Delivery-state accounting is unchanged.

## Tests (2026-10-09, Linux cloud container)

`python -m pytest -q tests/test_stale_fix_1_signal_time.py`: 9 passed, of which 2 are new:

- LIVE and REPLAY rows share a ticket id, decision and timestamp, with different reasons and
  the REPLAY event appended last. The digest reports the LIVE reason.
- A REPLAY-only event never lends its reason to the LIVE record.

With `canonical_fx_delivery.py` reverted to `main`, both new tests fail (2 failed, 7 passed),
so they detect the defect. The full-suite result is in the PR body.
