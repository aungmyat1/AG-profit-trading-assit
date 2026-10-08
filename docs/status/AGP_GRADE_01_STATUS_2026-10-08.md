---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-GRADE-01 — M1 replay outcome grader

Status: implemented on branch `codex/agp-grade-01`, based on TICKET_STORE_V1 PR #64 head
`f6f7744a40cd1c8acd6e12fe442fcb4a5046e0e9`. PR targets `main` and depends on #64 merging.
This is read-only market-history analysis; it does not use MT5 APIs or create orders.

## Contract

- Reads evaluations from TICKET_STORE_V1 and M1 CSV OHLC bars with timezone-aware timestamps.
- Entry is filled at the first post-signal bar touching or crossing the recorded entry. Entry
  expiry applies only before fill. Unfilled by expiry grades `EXPIRED`; after fill, M1 bars
  continue through the first SL/TP1/TP2 event.
- Same-bar SL plus target is recorded `AMBIGUOUS`, with the conservative `grade=SL` and
  `net_R` calculated from SL. Net R subtracts `spread_at_signal / abs(entry - SL)`.
- `BLOCKED` and `NO_TRADE` with valid direction/levels use `COUNTERFACTUAL_M1_V1`; other
  valid tickets use `FIRST_TOUCH_M1_V1`. Both append `source=REPLAY` OUTCOME records.
- Incomplete history or invalid levels fail closed and do not append an outcome. Replay is
  immutable and idempotent; changed results for an existing ticket/cohort are refused.
- `SPREAD_TIMING_GAP` is set when the absolute spread-measurement/signal-close gap exceeds
  one known trigger bar (15 minutes for ST_ASIAN_SWEEP_5R_V1, 5 for
  ST_LIQUIDITY_SWEEP_RETEST_V1).
- Reports include state counts, block reasons, net expectancy/win rate, MFE/MAE quantiles,
  counterfactual expectancy per block reason, `DIRECTIONAL_ONLY` for n < 100, and parity
  between LIVE/REPLAY evaluation input-bar hashes for matching evaluation identity.

## Verification and sample

- `uv run --with pytest --with PyYAML python -m pytest tests/test_ticket_store_grader.py -q`
  — 10 passed.
- Related grader/manual/store selection — 29 passed, 2 deselected. The two deselected
  legacy checks import the pandas-backed host/strategy pipeline, which is not installed in
  this offline test environment.
- `tests/fixtures/ticket_outcome_m1/sample_report.json` is generated from the pinned offline
  M1 fixtures. Fixture files and evaluation construction are checked by the focused test.
- No live MT5 data or terminal was used.
- The PR is stacked on #64; it must be rebased/retargeted after the store PR merges if GitHub
  does not preserve the dependency automatically.
