# ES-R1 Economic Gate Contract

## Minimum population requirements (P7)

- `MIN_TOTAL_OCCURRENCES >= 30` for a candidate to receive any economic interpretation at all.
- Preferred: `MIN_RESOLVED_TRADES >= 30` (i.e. terminal states only — `STOPPED_FULL_POSITION`, `RUNNER_TP2`, `RUNNER_BE_EXIT`; excludes `OPEN`/`UNRESOLVED`).
- If ambiguity (`INTRABAR_ORDER_UNRESOLVED`, still-`OPEN` at window end) materially reduces resolved N below the total, this must be reported separately, never converted to a WIN or LOSS.
- Subgroup claims (e.g. session-specific performance under R-H04's diagnostic stratification) require their own separately documented minimum N — no subgroup conclusion may be drawn from a tiny sample.

## Minimum advancement requirements (all three required)

1. `POST_FRICTION_EXPECTANCY > 0` (high-cost friction scenario, per `FRICTION_CONTRACT.md`)
2. `POST_FRICTION_PROFIT_FACTOR > 1` (same scenario)
3. Minimum population requirement satisfied (above)

## Required reporting for every candidate (advancing or not)

- Total R (gross and post-friction)
- Expectancy R/trade (gross and post-friction)
- Profit factor (gross and post-friction)
- Win rate
- Max drawdown R
- Consecutive losses
- Ambiguity rate (`UNRESOLVED` + still-`OPEN` / total occurrences)
- Trade frequency
- Session distribution (diagnostic, per R-H04)
- Long/short distribution

**Candidates are not ranked solely by maximum expectancy or profit factor** — see `CANDIDATE_SELECTION_POLICY.md`.
