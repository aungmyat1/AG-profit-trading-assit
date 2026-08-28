---
name: strategy-management
description: Resolve and invoke a registered deterministic strategy (list/inspect status, resolve cycle authority, run required capabilities, return a StrategyResult) through the existing Strategy Manager. Use when the user names a specific registered strategy (e.g. "run SESSION_TRADE_V1 for EURUSD ASIAN_LONDON") rather than asking for generic market analysis. Advisory/orchestration only -- never redefines a strategy's own rules and never calls execution directly.
---

# Strategy Management

Strategy tooling skill (assistant use case, not core trading intelligence -- see
`TRADE_ASSISTANT_ARCHITECTURE.md`'s "Assistant skill taxonomy"). This is the thin,
existing orchestration layer already implemented as `strategy_manager/` +
`assistant/runtime.py` + `scripts/trade_assistant.py` (`ASSISTANT_RUNTIME_V1`). This
skill file documents when/how to invoke that code -- it does not implement or
duplicate any strategy's decision logic.

## When to use

The user names a specific registered strategy and wants it evaluated or its status
inspected, e.g.:

- "Run SESSION_TRADE_V1 on EURUSD for the ASIAN_LONDON cycle."
- "Is ST_ASIAN_SWEEP_5R_V1 demo-authorized?"
- "What's blocking LONDON_NEWYORK?"

Do **not** use this skill for generic requests like "analyze EURUSD structure" --
those go directly to the relevant core skill(s) (`market-structure`, `supply-demand`,
`liquidity`, `entry-confirmation`) without loading any strategy. A strategy must never
be a prerequisite for basic assistant analysis.

## What this skill invokes

```
scripts/trade_assistant.py --strategy <id> --symbol <sym> --cycle <cycle> --mode <mode>
        |
assistant/runtime.py  TradeAssistant.evaluate(...)
        |
strategy_manager/manager.py  registry + contract cycle-authority check + dispatch
        |
strategy_manager/session_trade_adapter.py (SESSION_TRADE_V1 only, in V1)
```

Read `strategies/registry.yaml` and the strategy's own `config_source`
(e.g. `strategies/session_trade/contract.yaml`) before claiming a strategy is
`registered`, `active`, or authorized for a given cycle/mode -- never assume from
memory. `registered: true` never implies execution permission; check
`demo_authorized`/`live_authorized` and the per-cycle `execution_authority`
independently.

## Modes (unchanged, defined in `assistant/runtime.py`)

`ANALYZE_ONLY` (no broker writes) / `SHADOW_DEMO` (`order_check` only) /
`DEMO_EXECUTION` (real `order_send`, three independent gates) / `LIVE`
(hard-blocked, always). Never promote a mode on the user's behalf without an explicit
request matching the mode's own gating requirements.

## What this skill must NOT do

- Must not re-implement or approximate a strategy's classifier, sweep rule, or
  risk/SL/TP formulas -- those stay owned by the strategy (`strategies/session_trade/`,
  `strategy_engine/`, or the relevant contract file).
- Must not silently unblock an `UNSIGNED` cycle (e.g. `LONDON_NEWYORK`) or bypass the
  two independent hard blocks on `LIVE`.
- Must not force unrelated core skills (Structure/Supply-Demand) to run just because a
  strategy is being evaluated -- only run what the strategy's contract actually
  requires.

## Output

Report the `AssistantDecision` fields as-is (`status`, `setup`, `direction`, `entry`,
`stop_loss`, `target`, `reason_codes`) -- these are copied verbatim from the strategy's
own result, never recomputed or rounded differently. See `ASSISTANT_RUNTIME_V1.md` for
the full status-mapping table and `ASSISTANT_RUNTIME_V1_STATUS.md` for live evidence.
