# ST_MTF_CONTROL_SHIFT_V1 — Sample Adequacy Packet

> **UPDATE (AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1, run):** the experiment
> described below has been executed once, under its own new, frozen prereg
> (`research_external/candidate_factory/PREREG_MTF_LONGER_SAMPLE_R1.json`). Result:
> **explanations C and D are REJECTED** for the dominant CONTEXT-stage blocker (D1/H4
> bias-alignment pass rate was ~17% both with bounded 40/80-bar tail windows and with a
> full, ~7.7x longer closed-to-date D1/H4 history). A **new, sharper bottleneck** was
> found one stage later: of the few days that reach `H1_CONTROL_SHIFT`, zero ever pass
> it (0/314 days reach `M15_REFINEMENT` in either cycle). Verdict remains
> `HOLD_SAMPLE_REQUIRED` (0 trades, both cycles) — unchanged, no rule/threshold change.
> Full record: `research_external/candidate_factory/candidates/INT_C002_LONGER_SAMPLE_R1.json`
> and `docs/status/AG_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1_STATUS.md`. The
> remainder of this document is kept as originally written for context.


PR #46 (`research_external/candidate_factory/candidates/INT_C002.json`) reported
`HOLD_SAMPLE_REQUIRED`: ~1 year of EURUSD DEV data (`DEV_EURUSD_H1_M15_HIST1Y_V1`)
produced 0 qualifying signals, dominant reason `HTF_BIAS_NOT_ALIGNED` (252/305 days).
A warm-up-invariance check (doubled tail windows) also produced 0 signals
(`dev_replay/INT_C002_..._WARMUP_2N_CHECK/`). No strategy rule was changed to reach
either result, and none is proposed here.

## Remaining-possible explanations

```
A = strategy genuinely extremely selective      — CONSISTENT with evidence so far (not proven)
B = admitted sample insufficient                 — CONSISTENT (only ~1yr, single symbol)
C = required timeframe derivation/data inadequate — POSSIBLE: D1/H4 in the HIST1Y dataset are
                                                     DERIVED from H1/M15, not native (PR #34 replay
                                                     harness, `run_int_c002_mtf_control_shift.py`) —
                                                     NOT_VERIFIED whether derivation itself biases
                                                     HTF-bias classification
D = adapter/replay mismatch                       — PARTIALLY ADDRESSED: bounded tail windows
                                                     (D1=40,H4=80,H1=60,M15=150 bars) were an explicit
                                                     implementation choice for tractability, documented
                                                     as such; not proven immaterial
E = session restriction removes population        — POSSIBLE: engine only evaluates
                                                     ASIAN_LONDON/LONDON_NEWYORK; untested whether a
                                                     wider session set changes the HTF_BIAS funnel
F = NOT_VERIFIED                                  — default where above don't resolve it
```

No single explanation is ruled in or out; this packet exists to scope the next
experiment, not to pick one.

## Required inputs for the next experiment (prepared only)

- **Admitted dataset**: must stay inside the frozen `PREREG_CANDIDATE_FACTORY_R1`
  identity (`PREREG_SHA256=342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b`)
  or a NEW prereg_id/campaign if duration/symbols change — never an edit to the existing one.
- **Native vs derived timeframes**: identify whether native D1/H4 EURUSD history exists
  anywhere admissible (NOT_VERIFIED this mission — would need a fresh data-capability check,
  not a re-read of the existing matrix, since duration requirements differ from R1).
- **Minimum historical duration**: NOT_VERIFIED; no statistical power calculation performed
  by this mission (would be new work, out of scope for a preparation-only mission).
- **Additional symbols available**: per `data_capability_matrix.json`, GBPUSD has only a
  ~6-week DEV window (too short for this purpose); USDJPY/XAUUSD have no OHLC in this
  checkout at all. EURUSD remains the only symbol with usable multi-month DEV history.
- **Expected diagnostic funnel counts**: to be produced by the experiment itself, not
  assumed in advance.
- **Unchanged prereg identity / unchanged thresholds**: both are hard constraints on any
  follow-up — `min_trade_count=30`, kill policy `AG_CF_R1_DEV_SCREEN_V1`, and all other
  R1 prereg fields must not be edited; a longer-sample experiment needs its own new
  PREREG_ID.

## Required diagnostic funnel for the next run (no optimization, no loosening)

```
CONTEXT → LOCATION → H1 CONTROL SHIFT → M15 REFINEMENT → GEOMETRY → SESSION → TRADE
```

Each stage must report an admitted/rejected count. The experiment's purpose is to find
*where* population reaches zero, not to produce a trade count. No filter may be loosened
after seeing stage counts, and no freeze campaign may be proposed unless the
already-preregistered promotion criteria are independently met.
