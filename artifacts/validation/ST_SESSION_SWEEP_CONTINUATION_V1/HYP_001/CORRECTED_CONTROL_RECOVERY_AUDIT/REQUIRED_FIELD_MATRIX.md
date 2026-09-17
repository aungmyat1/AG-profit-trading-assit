# Required-Field Matrix (P1)

Exact signature audited: `src/session_sweep_continuation/outcome_resolution.py::resolve_campaign_entry(*, campaign_id, setup_model, direction, entry_time, entry_price, stop_price, reference_high, reference_low, runner_target_r, partial_pct, runner_pct, subsequent_candles, session_exit_time, friction)`.

| Field | Classification | Note |
|---|---|---|
| Occurrence ID (`campaign_id`/`trade_id`) | `AVAILABLE_FROZEN` | Present in every population artifact found |
| Symbol | `AVAILABLE_FROZEN` | Stamped per-record and in dataset manifests |
| Setup (`setup_model`) | `RECOVERABLE_FROM_EXISTING_ARTIFACT` | Encoded in `trade_id` suffix (e.g. `_S1_SWEEP_REVERSAL`) and in GEN_002's `setup` field directly |
| Direction | `AVAILABLE_FROZEN` | Present directly |
| Session/date | `AVAILABLE_FROZEN` | `entry_time` date + session_pair encoded in `trade_id` prefix |
| Detection timestamp | `AVAILABLE_FROZEN` | By this strategy's own architecture, detection timestamp == `entry_time` (no separate resting-order phase) |
| Entry timestamp/price | `AVAILABLE_FROZEN` | Present directly |
| Stop (`stop_price`) | `AVAILABLE_FROZEN` | `initial_stop` present directly in GEN_001/GEN_002A records |
| **`reference_high`** | **`MISSING_REQUIRES_FRESH_REPLAY`** | Absent from every population artifact found on `main` or the `refactor/architecture-boundary-hardening-v3` branch (`canonical_population.json`, `canonical_lifecycle_population.json`, `per_trade_results.csv`, `occurrence_level_decomposition.json`) |
| **`reference_low`** | **`MISSING_REQUIRES_FRESH_REPLAY`** | Same as above |
| TP1/opposite boundary | `MISSING_REQUIRES_FRESH_REPLAY` | Directly derived from `reference_high`/`reference_low` — same gap |
| BE transition requirement | `AVAILABLE_FROZEN` (as a rule, not a per-occurrence field) | BE = raw entry price once the partial fills, a fixed code rule (`outcome_resolution.py`), needs no stored field |
| Runner target (`runner_target_r`) | `AVAILABLE_FROZEN` | The experiment parameter itself, frozen by contract (3.0) |
| Session termination (`session_exit_time`) | `DETERMINISTICALLY_DERIVABLE_FROM_FROZEN_RAW_DATA` | Derived from the unchanged `session_pairs`/`trade_session` config plus the occurrence's own known date/session_pair — no raw candle re-scan needed |
| **Post-entry candle sequence (`subsequent_candles`)** | **`MISSING_REQUIRES_FRESH_REPLAY`** | No stored artifact retains the raw M15 candle series for any occurrence's post-entry window |
| Friction inputs | `AVAILABLE_FROZEN` | Unchanged config (`FRICTION_CONTRACT.md`), symbol known, stop distance known |

**Net conclusion:** exactly three related items block direct re-derivation from stored summaries — `reference_high`, `reference_low`, and `subsequent_candles`. Everything else is already available or trivially derivable from unchanged configuration. No value was derived in this pass (per P1's own instruction).
