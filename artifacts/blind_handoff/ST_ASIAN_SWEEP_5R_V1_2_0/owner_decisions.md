# Frozen Owner Authority — ST_ASIAN_SWEEP_5R_V1@1.2.0

- B-REGIME = A — SWEEP_ONLY
- B-ENTRY = A — CONFIRMED_SWEEP_RECLAIM_CANDLE_CLOSE
- B-STOP = A — REFERENCE_RANGE_TIMES_0_25
- B-WICKCLEAR = A — reject with `SL_DOES_NOT_CLEAR_SWEEP_EXTREME`
- B-TGT-ORDER = A — reject invalid directional target ordering
- B-SPLIT = YES — TP1 exits 75%; remaining 25% moves stop to breakeven and targets TP2 at 5R
- B-EMA = B — REMOVE
- B-RANGECHK = B — REMOVE
- B-MINRANGE = B — NONE
- B-SPREAD = C — both maximum 2.0 pips and maximum 0.15R must pass
- B-EXPIRY = A — 15 minutes; expiry boundary is exclusive
- B-TIMEINV = B — PER_SESSION_END
- B-STRUCT = B — REMOVE_VOLUME_CLAUSE
- ANCHOR = FIXED_UTC
- AUDUSD = EXCLUDE
- RISK = 0.5%; does not affect signal generation
- EXECUTION = PROPOSAL_ONLY

## Confirmed rows

- B-REF — existing deterministic closed reference-session high and low; immutable after close.
- B-TRADE — proposal-only manual ticket; no automatic execution.
- B-SWEEP — strict penetration and close reclaim.
- B-DIR — lower sweep/reclaim maps to LONG; upper sweep/reclaim maps to SHORT.
- B-MAXENTRY — first qualifying closed candle, maximum one entry per session; no numeric threshold.
