---
name: trend-range-classification
description: Classify a validated frozen M15 session as Trend or Range with canonical ER_ONLY_V2. Use only after the Session Box Skill passes; never mix Sweep, bias, entries, results, future candles, or the older 0.70 model into classification.
---

> **Ownership note (skill taxonomy pass, 2026-08-27):** `ER_ONLY_V2` is a
> **strategy-specific** rule owned by `ST_ASIAN_SWEEP_5R_V1`
> (`strategy_engine/session/classifier.py`), not a universal Trade Assistant
> definition of trend/range. `SESSION_TRADE_V1` uses its own, differently-thresholded
> `classify_session()` (in `Session Trade Codex`) — the two are not interchangeable.
> See `docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md`'s "Strategy-specific skill ownership" section
> and `docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md`. Do not present this classifier as the generic
> `market-structure` trend/range answer.

# ER_ONLY_V2 Trend/Range Classification

Run only after `session-box-drawing` returns a valid frozen session. Invalid or still-forming session data fails closed as `INVALID_SESSION_DATA` and must not receive a classification.

## Canonical calculation

Using completed M15 candles inside the frozen session only:

```text
Displacement = abs(final Close - first Open)
Path Length  = abs(first Close - first Open)
             + sum(abs(current Close - previous Close))
ER           = 0 when Path Length = 0
             = Displacement / Path Length otherwise
```

Classify `ER >= 0.40` as `TREND` and `ER < 0.40` as `RANGE`. Equality belongs to Trend. Zero path belongs to Range.

For Trend only, final Close above first Open is `LONG`, below is `SHORT`, and equality is `UNRESOLVED`. Range direction is not assigned by this skill.

## Isolation and evidence

Return classifier ID, status, threshold, equality policy, zero-path policy, displacement, path length, ER, session type, direction, source window, and candle count.

Sweep, bias, Entry 1/2/3, targets, trade results, and execution-window candles have no input channel and cannot affect classification. Identical frozen data must return an identical result. `0.70` belongs to a different retired model and is forbidden in `ER_ONLY_V2`.

## Frozen contract

```yaml
classifier_id: ER_ONLY_V2
threshold: 0.40
equality: TREND
zero_path: RANGE
status: VALIDATED
```
