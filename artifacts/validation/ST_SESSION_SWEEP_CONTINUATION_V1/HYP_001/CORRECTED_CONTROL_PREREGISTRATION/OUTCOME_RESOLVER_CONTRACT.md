# Outcome Resolver Contract (v1.0.1, frozen, not reopened)

Source: `src/session_sweep_continuation/outcome_resolution.py` (sha256 `2b2480138a7ccc5f0a16023e79f95e5fc8a9ea56a11e00fe63b8dde0b969e414`), `resolve_campaign_entry`.

| Stage | Semantic |
|---|---|
| Entry occurrence | Trigger candle's own close (M15 setup, unchanged) |
| Initial SL | ATR-based (period=14, buffer multiplier=0.20), unchanged |
| Partial target | `OPPOSITE_SESSION_BOUNDARY`: LONG → `reference_high`, SHORT → `reference_low` (corrected v1.0.1 mapping; `INVERSE_BOUNDARY` was the v1.0.0 defect) |
| Partial percentage | 50% (`partial_target_pct=0.50`) |
| BE transition | Remainder's stop moves to entry once the partial target fills |
| Runner target | `runner_target_r` × risk (CONTROL=3.0, TREATMENT=1.5 — frozen, not varied in this mission), `runner_pct=0.50` |
| Session exit | Unchanged trade-session window fallback if neither SL nor runner target is reached |
| Ambiguous ordering | `SAME_BAR_POLICY = AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER` — a candle touching both a stop and a target in the same bar is `AMBIGUOUS_SEQUENCE`, never resolved by assumed order |
| Unresolved occurrence handling | Never converted to a WIN or LOSS; reported as its own outcome category |
| **Fail-closed geometry gate** | A null/invalid partial-target geometry routes the occurrence to `_resolve_full_position_only` — evaluates SL vs. session-exit **only**, never reaches the runner-target evaluation path. This is the exact mechanism the amendment identifies as having silently gated v1.0.0 CONTROL evidence out of ever reaching the 3R leg. |

**Verified this mission:** `OPPOSITE_SESSION_BOUNDARY` is represented consistently across `outcome_resolution.py`, `execution/validator.py` (`leg1_take_profit`/`_leg1_target`), and `scripts/resolve_forward_shadow_outcomes.py:190` — no contradiction found. `BASELINE_PREREGISTRATION_STATUS` is therefore not `BLOCKED_CONTRACT_CONFLICT`.
