---
name: breakeven-manager
description: Decide whether the runner's stop should move to breakeven, only after the TP1 partial close is broker-confirmed. Use when asked if breakeven has/should trigger.
---

# Breakeven Manager

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
`trade_management.rules.evaluate_breakeven()`.

## Decision rule

- Only eligible once state is `TP1_PARTIAL_DONE` -- a broker-confirmed partial, not
  merely "price touched TP1". If state is still `MANAGED_OPEN`/`TP1_PENDING` -> HOLD
  (`PARTIAL_NOT_CONFIRMED`).
- If breakeven already applied (state `BREAKEVEN_DONE`/`RUNNER_ACTIVE`) -> HOLD
  (`BREAKEVEN_ALREADY_DONE`), never re-fire.
- Otherwise -> `MOVE_SL` to the Claim's original `entry_price` exactly. No pip buffer
  unless a strategy explicitly defines one (none does in V1).

## Guardrails

- **THIS SKILL DOES NOT OPEN TRADES.**
- Never move the stop before the partial is broker-confirmed (see
  `trade_management.state.reconcile()` -- volume mismatch blocks this).
- `trade_management.validator.validate()` additionally refuses any `MOVE_SL` that
  would widen risk beyond the claim's original `initial_sl` -- breakeven never violates
  this since it moves toward entry, but the check applies uniformly.
- Never call `mt5.management_gateway.modify_position_sl()` directly from this skill.
