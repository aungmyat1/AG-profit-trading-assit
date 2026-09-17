# ES-R1 Candidate Selection Policy (frozen before any result is seen)

Advancement preference order:

1. Economic-floor pass (`ECONOMIC_GATE_CONTRACT.md`)
2. Sufficient sample (`MIN_RESOLVED_TRADES >= 30`, or explicitly bounded if not met)
3. Robustness (`ROBUSTNESS_GATE_CONTRACT.md`, evaluated at ES-R4)
4. Simplicity (fewer/simpler conditions preferred over more complex ones, all else equal)
5. Stability across time/session/direction
6. Lower dependence on precise threshold placement (a candidate that performs similarly across its own parameter neighborhood is preferred over one that only works at one exact value)

**Candidates are never selected merely by highest expectancy or highest profit factor.** If multiple candidates survive the economic floor, all are preserved into robustness testing (ES-R4) rather than prematurely narrowing to one "best" candidate — and the objective is never retrospectively changed to justify a result already seen.
