# Architecture Conflict Audit — 2026-08-27

Scope: this repo (`AG profit trading`) plus its registered-by-reference strategy
`SESSION_TRADE_V1` (implemented in `D:\ddev\Session Trade Codex`). Searched for duplicated
strategy authority across session windows, classifiers, sweep rules, direction/entry/SL/TP
rules, quotas, and execution/demo-live gates.

| Rule | File(s) | Owner | Status | Conflict? | Action |
|---|---|---|---|---|---|
| Asian session window (canonical) | `config/canonical_sessions.yaml` (this repo) | Canonical config | `00:00–06:00`, 24 candles, `CANONICAL` | No | None — single source of truth for canonical windows, already correctly centralized |
| Asian session window (`ST_ASIAN_SWEEP_5R_V1`) | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` | Strategy | matches canonical `asian` exactly | No | None |
| Asian session window (`SESSION_TRADE_V1`) | source repo `config/strategy.yaml` | Strategy | `00:00–07:00`, 28 candles — deliberately non-canonical, documented `LEGACY_SESSION_WINDOW` | **Documented, not a bug** | None — already recorded in that repo's own `canonical_sessions.yaml legacy_session_windows`; do not force-migrate (would invalidate golden fixtures) |
| Trend/Range classifier: `ER_ONLY_V2` | `strategy_engine/session/classifier.py` (this repo) | `ST_ASIAN_SWEEP_5R_V1` | threshold 0.40, path-length-based, no direction output | No | Owned by its strategy, correctly scoped |
| Trend/Range classifier: `classify_session()` | source repo `session_strategy/engine.py` | `SESSION_TRADE_V1` | threshold 0.35 + close-location 0.65, directional | **Two different classifiers exist, by design** | None to merge — each is signed for a different strategy. Risk: a future contributor could assume they're interchangeable. Mitigated by `SESSION_TRADE_V1_SPEC.md` §"Trend/Range classifier" stating this explicitly. |
| Hypothesized midpoint open/close-side classifier | (nowhere — checked and not found) | — | **Not implemented anywhere** | N/A | Correctly not adopted — no signed source found in either repo (see spec doc). If the owner wants this rule, it needs to be signed into a specific strategy's config first. |
| Sweep qualification: generic liquidity | `liquidity/status.py` (this repo) | Liquidity capability | `UNSWEPT/SWEPT/RECLAIMED/CONSUMED`, symbol/timeframe-general | No | Already documented as independent of any strategy's own sweep rule (`liquidity-analysis` skill's own text) |
| Sweep qualification: `ST_ASIAN_SWEEP_5R_V1` | `strategy_engine/session/setups.py` (`entry_2_sweep`) | Strategy | strict penetration against its own reference box | No | Correctly strategy-owned |
| Sweep qualification: `SESSION_TRADE_V1` | source repo `session_strategy/engine.py::detect_sweep()` | Strategy | buffer/quality/dual-side rules, own thresholds | No | Correctly strategy-owned, distinct from the above two by design |
| Direction/entry/SL/TP formulas | strategy-specific files per strategy above | Strategy | — | No | Never found duplicated into a capability layer or skill |
| Session-pair naming convention (`ASIAN_LONDON`/`LONDON_NEWYORK`) | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` (this repo) AND source repo's `scripts/execute_session_signal.py` | Two different strategies | Same *naming pattern*, different window values, different strategies | **Naming collision risk, not a rule conflict** | Both are legitimately named this way; `SESSION_TRADE_V1_SPEC.md`/`contract.yaml` now state explicitly these are not the same pair definitions. No rename done — would be cosmetic churn across two repos for a documentation-only ambiguity. |
| Trade quota | `config/strategy.yaml` (`maximum_trades_per_symbol_session: 1`), per magic number per cycle | `SESSION_TRADE_V1` | Per-strategy, per-cycle | No | Confirmed **not** applied globally to the whole assistant — `execution/` in this repo has its own independent (currently paused) risk config, untouched |
| Execution authority: `ST_ASIAN_SWEEP_5R_V1` | `config/trading.yaml` (this repo) | Repo-wide | `mode: ANALYSIS`, `allow_order_send: false` | No | Consistent, project-wide paused |
| Execution authority: `SESSION_TRADE_V1` `ASIAN_LONDON` | source repo `config/strategy.yaml` | Strategy | `mode: trading_enabled`, demo only, live hard-blocked | No | Independent of this repo's own paused state — correctly scoped per-repo, per-strategy |
| Execution authority: `SESSION_TRADE_V1` `LONDON_NEWYORK` | source repo `scripts/execute_session_signal.py` | Strategy | `UNSIGNED`, hard-refused | No | Working as intended |
| Live-execution gate | both repos independently | Both | Hard `false`, unconditional, in both `config/trading.yaml` (this repo) and `config/strategy.yaml` (source repo) | No | Two independent hard blocks, not one shared flag — correct, no single point of failure |
| Agent skills (`.claude/skills/*`) | this repo | Capability instructions | Scanned for hardcoded strategy decisions (e.g. "sweep => short") | **False positive only** | `market-structure-analysis/SKILL.md`'s one match is its own guardrail *prohibiting* that phrasing, not a violation. All trading-related skills read explicitly defer to `strategy_engine.evaluate()` / advisory-only language already. No change needed. |

## Summary

```
STRATEGY_RULE_CONFLICTS  = 0
DUPLICATE_AUTHORITIES    = 0
```

No case found where two components claim to own the *same* decision with *different* answers.
The apparent overlaps (two classifiers, two sweep rules, shared pair-naming convention) are all
correctly scoped to distinct, independently-signed strategies once traced to their actual
source — the risk was documentation clarity, not runtime conflict, and is addressed by this
audit plus `SESSION_TRADE_V1_SPEC.md` stating the distinctions explicitly.
