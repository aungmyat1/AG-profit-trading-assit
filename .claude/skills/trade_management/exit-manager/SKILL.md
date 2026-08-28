---
name: exit-manager
description: Decide whether the runner should close at its final R target, and detect externally-closed positions. Use when asked whether the runner should exit yet, or why a claimed position disappeared.
---

# Exit Manager

Phase 6 (Trade Management, manual-entry only). Wraps
`trade_management.rules.evaluate_exit()` and `trade_management.state.reconcile()`'s
externally-closed detection.

## Decision rule

- Only eligible once the runner is active (state `BREAKEVEN_DONE`/`RUNNER_ACTIVE`); if
  the partial/breakeven steps haven't completed -> HOLD (`RUNNER_NOT_ELIGIBLE`).
- Computes current R from the Claim's frozen `initial_r_distance` (never a distance
  recomputed from the moved breakeven stop) and compares against `claim.final_r_multiple`
  (5 in the V1 baseline, spec Rule 5).
- Below target -> HOLD (`FINAL_TARGET_REACHED_PENDING`). At/above target -> `CLOSE` the
  full remaining volume, reason `FINAL_TARGET_REACHED`.
- If MT5 no longer reports the position at all (SL hit, broker close, manual close),
  `trade_management.state.reconcile()` marks it `CLOSED` with
  `POSITION_CLOSED_EXTERNALLY` -- this skill does not attempt to recreate or contest
  that; it just reports it.

## Guardrails

- **THIS SKILL DOES NOT OPEN TRADES.**
- Never invent a target other than the claim's own `final_r_multiple`.
- Never call `mt5.management_gateway.close_position()` directly from this skill; only
  `trade_management.manager` does that, after `trade_management.validator.validate()`.
