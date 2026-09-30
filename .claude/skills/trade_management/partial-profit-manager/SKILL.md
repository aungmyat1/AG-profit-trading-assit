---
name: partial-profit-manager
description: Decide whether TP1 has been reached and a 75% partial close should be requested for a claimed manual position. Use when asked whether a partial should fire, or to explain why it hasn't.
---

# Partial Profit Manager

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
`trade_management.rules.evaluate_partial_profit()`.

## Inputs

Claim (entry, initial SL/R, TP1), current NormalizedPosition, current management
StateRecord, broker SymbolMeta.

## Decision rule

- If TP1 is undefined on the claim -> HOLD (`TP1_UNDEFINED`). Never invent a TP1.
- If price hasn't reached TP1 -> HOLD (`TP1_NOT_REACHED`).
- If already past this stage (state is not `MANAGED_OPEN`/`TP1_PENDING`) -> HOLD
  (`TP1_ALREADY_HANDLED`) -- never re-fire.
- If TP1 reached -> close 75% of current volume, normalized to the broker's real
  `volume_step`/`volume_min` (`trade_management.risk.normalize_partial_close_volume`).
  If that normalization fails (illegal remainder / below-min), HOLD with that reason
  instead of forcing an ad hoc size.

## Outputs

A `ManagementIntent` (`PARTIAL_CLOSE` with `requested_volume`, or `HOLD` with a reason
code) -- always passed through `trade_management.validator.validate()` and then
`mt5.management_gateway.partial_close_position()` before anything reaches the broker.
Price reached TP1 is not the same as the partial being done: the state only advances to
`TP1_PARTIAL_DONE` once the gateway confirms the close.

## Guardrails

- **THIS SKILL DOES NOT OPEN TRADES.**
- Never close more than 75% or a different milestone than TP1 -- that's a separate,
  signed rule change, not this skill's discretion.
- Never call `mt5.management_gateway` directly; only `trade_management.manager`
  sequences that, after validation.
