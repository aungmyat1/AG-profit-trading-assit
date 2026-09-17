# Corrected CONTROL Terminal Vocabulary (frozen before execution)

- **`BASELINE_ESTABLISHED`** — replay completes under the frozen contract with sufficient integrity to characterize corrected v1.0.1 CONTROL. Does **not** require profitability.
- **`BASELINE_INSUFFICIENT`** — replay is technically valid but the evidence population cannot support the intended comparison under preregistered requirements (e.g. sample too small, too many unresolved occurrences).
- **`BASELINE_EXECUTION_ERROR`** — replay cannot complete because of a technical/runtime/data-processing failure (e.g. `GEN_001`'s raw file remaining inaccessible from `main`, per `POPULATION_MANIFEST.md`'s execution-time prerequisite).
- **`BASELINE_CONTRACT_CONFLICT`** — a material semantic/configuration contradiction prevents a valid corrected CONTROL (none found in this preregistration pass — see `OUTCOME_RESOLVER_CONTRACT.md`).

No profitability-dependent status name (e.g. "BASELINE_PROFITABLE"/"BASELINE_UNPROFITABLE") exists in this vocabulary.
