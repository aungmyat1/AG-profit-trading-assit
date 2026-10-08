# Agent Invariants

Version: v1

## Execution firewall
- `DEMO`/`LIVE` authorization remains false by default; require explicit owner authorization and every separate strategy, configuration, runtime, and per-order user-confirmation gate already defined in `AGENTS.md` and governance. Platform readiness alone never grants trading authority.
- In read-only missions: `ORDER_API_CALLS = 0` and `BROKER_MUTATION_COUNT = 0`. Never call `order_send`, `order_check`, position/pending-order mutation, an execution gateway, or `assistant.commands.execute_command()`.

## Fail-closed policy
- Missing, unsigned, malformed, or conflicting actionability policy never authorizes `WATCH_READY`; use the existing fail-closed state and never invent a numeric threshold.

## No invented market facts
- Canonical ticket context, POI, and structure fields are source pass-through only; absent facts are `NOT_AVAILABLE`. Never synthesize a POI or market-context label.

## No silent sessions
- Every required `instrument × session` receives exactly one typed terminal decision. Missing or unavailable data must be an explicit `BLOCKED`/`INSUFFICIENT_DATA` outcome, never `NO_TRADE`.

## Status honesty
- `LOGIC_VERIFIED` does not imply `EDGE_VERIFIED`; ticket generation does not imply broker execution. Report only what the evidence establishes.

## Branch discipline
- Start from a fresh worktree at current `origin/main`; keep one writer per branch/worktree.
- Open a draft PR before pushing changes; never edit `D:/wp3-main-integ`; do not merge without the owner's authority.

## Standard report footer
- End each mission report with: `PR=<url-or-NONE> | FINAL_HEAD=<sha> | LINES_ADDED/REMOVED=<added>/<removed> | CONFLICTS_FOUND=<summary-or-NONE> | POLICY_CHANGES=<count>`.
