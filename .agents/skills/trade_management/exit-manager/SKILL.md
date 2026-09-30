---
name: exit-manager
description: Decide whether the runner should close at its final R target, and detect externally-closed positions. Use when asked whether the runner should exit yet, or why a claimed position disappeared.
---

# Exit Manager

## Token minimum usage policy (owner rule, applies to every task)
- Do only what the task asks; no extra features, refactors or docs.
- No polling, scheduled check-ins or PR subscriptions unless explicitly asked.
- Don't ask questions mid-task: make conservative choices, record them, continue.
- Read only files needed; prefer grep/targeted reads over full-file or repo-wide dumps.
- Don't re-run unchanged failing steps; report the blocker once and stop.
- Batch tool calls; avoid repeated verification of the same fact.
- Reports: concise — status, key results, blockers, next step. No restating the prompt,
  no long learning sections unless asked.
- Stop immediately when the task is done.

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
