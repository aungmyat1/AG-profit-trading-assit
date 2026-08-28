# Strategy Registry Status — 2026-08-27

## Registry implementation

`strategies/registry.yaml` — data-only registry (strategy_id, registered/active/research flags,
demo/live authorization, config source, owning engine). No runtime loader/orchestrator exists
yet (see `docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md`'s "Strategy Manager" section for why that's a
deliberate, not accidental, gap: nothing currently calls one).

`strategies/STRATEGY_LEDGER.md` — narrative registration history, now includes `SESSION_TRADE_V1`
alongside the existing `ST_ASIAN_SWEEP_5R_V1` entry.

## Registered strategies

| strategy_id | registered | active | research | demo_authorized | live_authorized |
|---|---|---|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1` | YES | YES | YES | NO (project-wide execution PAUSED, plus own open gaps — undefined entry order type, unspecified risk %) | NO |
| `SESSION_TRADE_V1` | YES | YES | NO | **PARTIAL** — `ASIAN_LONDON` cycle YES, `LONDON_NEWYORK` cycle NO (`UNSIGNED`) | NO (both cycles, hard block) |
| `SMC_3R_V1` | YES | NO | YES | NO | NO |
| `R8_OBM_V1` | YES | NO | NO | NO (`.ex5`/`.mq5` removed from the MT5 terminal by the owner 2026-08-27; an orphaned position from its prior runs may remain — not tracked here) | NO |

Registration is explicitly separate from execution permission throughout — no strategy's
`registered: true` implies any authorization; each authorization field is set independently per
the actual signed contract for that strategy.

## `SESSION_TRADE_V1` detail

```
REGISTERED         = YES (strategies/session_trade/contract.yaml, this repo)
STRATEGY_CONTRACT   = NOT_FROZEN as a whole (ASIAN_LONDON cycle is FROZEN; LONDON_NEWYORK is not)
ASIAN_LONDON        = ACTIVE (demo)
LONDON_NEWYORK       = UNSIGNED (blocked)
EXECUTION_CRITICAL_UNSIGNED_RULES = 1 cycle (LONDON_NEWYORK's reference window, execution
                                     window, and execution authority — grouped as one unsigned
                                     rule set, not three independent gaps, since they all trace
                                     to the same root cause: no owner-signed window for this cycle)
```

Full field-by-field detail: `docs/specs/SESSION_TRADE_V1_SPEC.md`.
