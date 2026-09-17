# ES-R1 Friction Contract

## Classification (as of this preregistration; to be re-verified at ES-R2 admission, not assumed carried forward automatically)

| Component | Status |
|---|---|
| Spread | `UNAVAILABLE` — no confirmed live/historical spread series has been verified for the candidate development datasets identified in `DEVELOPMENT_DATA_ADMISSION_CONTRACT.md` as of this mission |
| Commission | `UNAVAILABLE` — not yet sourced for this strategy/dataset pairing |
| Slippage | `UNAVAILABLE` — not yet sourced |

## Required bounded-friction scenarios (since exact execution friction is unavailable)

Rather than silently assuming zero friction, ES-R2+ must evaluate at least two bounded scenarios:

- `FRICTION_SCENARIO_LOW` — a conservative low-cost assumption (to be fixed with an explicit, cited source before ES-R2, not invented ad hoc)
- `FRICTION_SCENARIO_HIGH` — a conservative high-cost assumption

Both `GROSS` and `POST_FRICTION` (under both scenarios) must be reported separately for every candidate. **Candidate advancement is based primarily on `POST_FRICTION` economics under the high-cost scenario** — gross profitability alone, or profitability only under the low-cost scenario, cannot qualify a candidate.

No specific numeric friction value is fixed in this mission — that is deferred to ES-R2's own dataset-specific admission work, to avoid preregistering a number without a cited source.
