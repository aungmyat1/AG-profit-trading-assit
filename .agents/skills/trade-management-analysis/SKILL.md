---
name: trade-management-analysis
description: Report and explain the state of an open position — R multiple, whether a partial/breakeven/trailing rule has triggered per the strategy's own config, time/structural invalidation proximity. Use when asked about an open trade's status or whether a management rule fired. Advisory only — cannot modify SL/TP or close a position.
---

# Trade Management Analysis

Top layer of the AG Profit Trading assistant pyramid. Reports against a strategy's own
predefined management rules (e.g. `ST_ASIAN_SWEEP_5R_V1.yaml`'s
`position_split_and_targets` and `invalidation_rules`) once a position exists; it does
not invent discretionary management logic.

## Deterministic capability (TRADE_MANAGEMENT_V1, added 2026-08-28)

`trade_management/` now covers two independent, deterministic products (full contract:
`docs/specs/TRADE_MANAGEMENT_V1_SPEC.md`):

1. **Pre-trade** (`evaluate_trade_management()`, `pretrade_engine.py`) — geometry
   validation, broker-realistic position sizing (tick_size/tick_value based, never a
   hardcoded pip formula), and R/reward geometry for a *proposed* trade, before any
   position exists. Works standalone for a manual trade (no strategy required) or as
   the sizing step a strategy's candidate runs through before becoming a `TradeIntent`.
   Every risk/volume result is one of the explicit statuses in
   `trade_management/models.py` (`READY`, `ACCOUNT_DATA_MISSING`, `RISK_LIMIT_EXCEEDED`,
   `VOLUME_BELOW_MIN`, `VOLUME_ABOVE_MAX`, ...) — never a silent unsafe rounding.
2. **Manual-entry, already-open position** (Phase 6 — `claims`/`state`/`rules`/
   `position_monitor`, unchanged by this pass) — this is what "report the state of an
   open position" already meant before V1 and remains the authoritative, broker-
   reconciled path for a claimed ticket.

Use #1 when the user proposes a trade ("what's the size for this EURUSD long") and #2
when the user asks about an already-open, manually-claimed position. Neither ever calls
`order_send`/`order_check`/position-modify — see the AST-based import/call safety tests
in `tests/test_trade_management_pretrade.py`.

`evaluate_trade_management()` never invents a strategy's own risk %, targets, or
breakeven rule — those arrive as an optional caller-supplied `ManagementPolicy`
(`max_risk_percent`, `breakeven_trigger_r`, `policy_source`/`strategy_id`). Absent a
policy, it validates geometry/sizing only and reports `position_state` as
`NOT_REQUESTED`/`HOLD` rather than guessing a rule.

## Scope

- Compute current R multiple from entry, stop, and current price.
- State whether a leg's target/breakeven/trailing rule has been reached per the
  strategy's own `position_split_and_targets` config (e.g. "leg 1 hit its
  OPPOSITE_SESSION_BOUNDARY target, runner SL should move to breakeven").
- Flag proximity to `invalidation_rules` (time-based or structural) from the strategy config.
- Report exposure: open positions per symbol/strategy, aggregate R at risk.

## Guardrails

- This skill reports and explains; it never calls anything that would modify or close a
  position. Adjusting SL/TP, taking a partial, or closing a trade is delegated to the
  central Trade Assistant execution layer (`mt5.management_gateway`, via
  `execution/executor.py`/`assistant/commands.py`) and requires the strategy's own rule
  to have actually fired, plus explicit user authorization — this skill does not get
  discretion to act "because it looks risky."
- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
- Do not recommend closing a trade, moving a stop, or overriding a target unless the
  strategy's own config explicitly grants that discretion in `invalidation_rules` or
  `position_split_and_targets` — cite the specific rule when reporting that one has
  triggered, don't reason from "price looks like it might reverse."
- If a management rule's trigger condition is ambiguous from the data available, report
  it as unresolved rather than guessing which side it fell on.
- Never silently round a volume up past a risk budget, or cap a size above broker
  `volume_max`, to force a trade through — report `VOLUME_BELOW_MIN`/`VOLUME_ABOVE_MAX`/
  `SIZE_UNAVAILABLE` instead. See `docs/specs/TRADE_MANAGEMENT_V1_SPEC.md`'s "broker normalization" section.
