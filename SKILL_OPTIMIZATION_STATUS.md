# Skill Optimization Status — 2026-08-27

Scope: logical skill-boundary optimization of the AG Profit Trading Assistant's
agent-facing skills (`.claude/skills/`, mirrored identically in `.agents/skills/`).
Audit-first, no mass file moves. Evidence gathered by reading actual code
(`strategy_engine/session/`, `strategies/registry.yaml`, package directories) rather
than accepting the previous audit's stale numbers or the mission brief's assumed
strategy ownership at face value. Full taxonomy: `TRADE_ASSISTANT_ARCHITECTURE.md`'s
"Assistant skill taxonomy" section. Reference mapping:
`.claude/skills/SKILL_REGISTRY.yaml`.

## BEFORE — 16 top-level skill directories

```
strategy-specification
session-box-drawing
market-structure-analysis
liquidity-analysis
supply-demand-analysis
entry-confirmation-analysis
trade-management-analysis
trade_management/  (5 sub-skills: breakeven-manager, exit-manager,
                     partial-profit-manager, position-monitor, risk-manager)
trend-range-classification
sweep-detection-range-v2
market-data
market-data-quality
multi-asset-conventions
performance-analysis
risk-position-sizing
backtest-engineering
robustness-validation
```

## AFTER — 9 logical skill families

```
CORE                          FOUNDATION          STRATEGY TOOLING
1. market-structure           6. market-context   7. strategy-development
2. supply-demand                                  8. strategy-validation
3. liquidity                                      9. strategy-management (new)
4. entry-confirmation
5. trade-management
```

## Per-skill classification (evidence-based)

| Skill | Target owner | Action | Evidence |
|---|---|---|---|
| `market-structure-analysis` | `market-structure` | KEEP_TOP_LEVEL | `market_structure/` package, READY, frozen (Phase 2) |
| `supply-demand-analysis` | `supply-demand` | KEEP_TOP_LEVEL | `supply_demand/` package, READY, `AG_ORDER_BLOCK_V1` frozen |
| `liquidity-analysis` | `liquidity` | KEEP_TOP_LEVEL | `liquidity/` package, READY |
| `entry-confirmation-analysis` | `entry-confirmation` | KEEP_TOP_LEVEL | No backing package found anywhere (`grep` for entry-confirmation implementation returned nothing) — confirms `NOT STARTED` |
| `trade-management-analysis` | `trade-management` | MERGE_INTO_CORE_SKILL | Generic open-position advisory text; no package of its own |
| `trade_management/*` (5 sub-skills) | `trade-management` | KEEP_TOP_LEVEL (as implementation modules) | `trade_management/` package exists, READY, Phase 6 (manual-entry, independently gated from `execution/`) |
| `risk-position-sizing` | `trade-management` | MERGE_INTO_CORE_SKILL | Currently framed for backtest/research sizing, not live risk — grouped by domain per mission instruction; framing left unchanged |
| `session-box-drawing` | `market-context` | MERGE_INTO_FOUNDATION | Session box math is foundation-layer, independent of any strategy |
| `market-data` | `market-context` | MERGE_INTO_FOUNDATION | `mt5/` package |
| `market-data-quality` | `market-context` | MERGE_INTO_FOUNDATION | OHLCV/session-completeness gating belongs before core skills run |
| `multi-asset-conventions` | `market-context` | MERGE_INTO_FOUNDATION | Pip/contract/session conventions consumed by all core skills |
| `strategy-specification` | `strategy-development` | KEEP_TOP_LEVEL (logical rename only) | Already matches the research/hypothesis/spec workflow in the mission's §26 |
| `performance-analysis` | `strategy-validation` | MERGE_INTO_STRATEGY_TOOLING | Strategy-neutral evaluation framework |
| `backtest-engineering` | `strategy-validation` | MERGE_INTO_STRATEGY_TOOLING | Same |
| `robustness-validation` | `strategy-validation` | MERGE_INTO_STRATEGY_TOOLING | Same |
| `trend-range-classification` | **`ST_ASIAN_SWEEP_5R_V1`** (strategy-specific) | MOVE_TO_STRATEGY_SPECIFIC | `ER_ONLY_V2` lives in `strategy_engine/session/classifier.py`; `strategies/registry.yaml` maps `strategy_engine` to `ST_ASIAN_SWEEP_5R_V1`, **not** `SESSION_TRADE_V1` |
| `sweep-detection-range-v2` | **`ST_ASIAN_SWEEP_5R_V1`** (strategy-specific) | MOVE_TO_STRATEGY_SPECIFIC | `entry_2_sweep` in the same `strategy_engine/session/setups.py`; same owner |
| (none existed) | `strategy-management` | NEW (documentation only) | `strategy_manager/` + `assistant/runtime.py` + `scripts/trade_assistant.py` already implement this; zero agent-skill representation existed before this pass |

**Correction of the mission brief's assumed mapping:** the brief assumed
`trend-range-classification` and `sweep-detection-range-v2` belonged to
`SESSION_TRADE_V1`. Reading `strategy_engine/session/*.py` and
`strategies/registry.yaml` directly shows both are owned by `ST_ASIAN_SWEEP_5R_V1`
instead — `SESSION_TRADE_V1` has its own separate classifier/sweep implementation in
`Session Trade Codex`. Per `ARCHITECTURE_CONFLICT_AUDIT.md`, both pairs coexist
intentionally for distinct signed strategies; this pass did not merge, alter, or
prefer one over the other — only corrected the ownership record.

## MERGED (logical grouping only, no files physically combined)

- `trade-management-analysis` + `risk-position-sizing` + 5 `trade_management/*`
  sub-skills -> `trade-management`
- `session-box-drawing` + `market-data` + `market-data-quality` +
  `multi-asset-conventions` -> `market-context`
- `performance-analysis` + `backtest-engineering` + `robustness-validation` ->
  `strategy-validation`

## MOVED TO STRATEGY OWNERSHIP

- `trend-range-classification` -> `ST_ASIAN_SWEEP_5R_V1` (`ER_ONLY_V2`)
- `sweep-detection-range-v2` -> `ST_ASIAN_SWEEP_5R_V1` (`SESSION_FLOW_V2_SIMPLE`)

Both kept in place physically (reference-based ownership, per mission §33/§52) — only
an ownership note was added to each `SKILL.md`, in both `.claude/skills/` and
`.agents/skills/` copies. No algorithm, threshold, or instruction text inside either
skill was changed.

## UNCHANGED IMPLEMENTATIONS

All deterministic Python packages (`market_structure/`, `supply_demand/`,
`liquidity/`, `trade_management/`, `strategy_manager/`, `assistant/`,
`strategy_engine/`, `mt5/`) — zero code changes this pass. `AG_ORDER_BLOCK_V1`,
`ER_ONLY_V2`, `SESSION_FLOW_V2_SIMPLE`, `strategies/registry.yaml`,
`strategies/session_trade/contract.yaml` all frozen/untouched.

## DEPRECATED NAMES

None. No skill was renamed or removed; `strategy-specification` keeps its name (its
logical family is `strategy-development`, recorded in the registry, not enforced by
renaming). No compatibility shim was needed because nothing was renamed.

## UNRESOLVED

1. `entry-confirmation` has no deterministic backing module — remains `PARTIAL`,
   scoped for a future `ENTRY_CONFIRMATION_V1` pass (not built here, per mission §15/§68).
2. `risk-position-sizing`'s skill text is framed for backtest/research sizing, not live
   account risk. It is logically grouped under `trade-management` per the mission's
   explicit instruction, but its own wording was not rewritten this pass — a future
   pass may want to either reframe it or keep it purely as the research/validation-side
   sizing reference while `trade_management/risk.py` stays authoritative for live state.
3. Session Trade Codex's two pre-existing test failures
   (governance config-hash drift, golden-fixture classifier drift) are unrelated to
   this pass and were not touched, per mission §51/§77.

## Counts

```
OLD_TOP_LEVEL_SKILLS = 16
NEW_LOGICAL_SKILLS   = 9
MERGED               = 12   (folded into market-context, trade-management, strategy-validation)
STRATEGY_SPECIFIC    = 2    (trend-range-classification, sweep-detection-range-v2)
DEPRECATED           = 0
UNRESOLVED           = 3
NEW_SKILL_FILES_ADDED = 1   (strategy-management -- documentation only)
```
