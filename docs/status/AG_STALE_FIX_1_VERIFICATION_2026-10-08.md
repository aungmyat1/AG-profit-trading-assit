---
class: status
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# STALE-FIX-1 verification — stale-gate trigger-close fix landed and regression-green (2026-10-08)

Mission mapping: the coordinator designation **STALE-FIX-1 / PR B** resolves to the
repository mission **AGP-TTU-02** ("keep trigger close through stale-data gate"), published
upstream as PR #61 and merged into `main`. This record is an **independent re-verification**
performed in a fresh Linux cloud container on this session's checkout. It changes no code,
no configuration, no strategy admission, and no broker execution authority. It is
documentation-only.

## 1. Source commit, patch artifact, affected files

| Fact | Value |
|---|---|
| Upstream PR | #61 `fix(v1_tickets): keep trigger close through stale-data gate (AGP-TTU-02)` |
| Dedicated fix branch | `fix/stale-gate-trigger-close` |
| Fix head SHA | `34af0bfbab75d2d7bdbea3bb54297b1f54d6c792` |
| Merged to `main` at | `2026-10-07T19:47:03Z` via merge commit `96f4aa6a8470f86b876294bfa27b89989467842d` |
| Patch artifact | The PR #61 diff itself (4 files, +263/−0). No standalone `.patch`/`.diff` file for STALE-FIX-1 exists in the repository, the workspace, or any stash (searched: tree, `docs/plans/`, `/tmp`, git stash, git fsck — the only `.patch` files are three unrelated historical documents under `docs/plans/`) |

Affected files of the fix:

| File | Delta | Role |
|---|---|---|
| `src/v1_tickets/guards.py` | +4 | RC1: keep the already-computed `signal_close_utc` on a stale-withheld READY |
| `src/v1_tickets/actionability.py` | +9 | RC2: a stale engine `NO_TRADE` is restored with its engine reason only once `now >= trade_window_end`; an open window stays `INFO_ONLY_STALE / STALE_DATA` |
| `tests/test_stale_gate_trigger_close.py` | +231 (new) | 18 regression tests (cases A–G + frozen replay) |
| `PROJECT_STATUS.md` | +19 | rolling status entry |

## 2. Applied-to-branch state

The patch **is applied**: the dedicated branch was merged into `main`, and the fix content
is present in this checkout and on current `origin/main`.

Evidence:

- `git merge-base --is-ancestor 34af0bfb 59900b2c` → true (fix head is an ancestor of this
  session's base, merge of PR #88).
- `git merge-base --is-ancestor 34af0bfb origin/main` → true (ancestor of current
  `origin/main` `0bea6681...`, merge of PR #89).
- `git diff 59900b2c origin/main -- src/v1_tickets/guards.py src/v1_tickets/actionability.py tests/test_stale_gate_trigger_close.py` → **empty** (byte-identical).

No unpushed or uncommitted rescue artifact exists anywhere reachable from this session.

## 3. Real timestamps preserved, no invented timestamps

- `signal_close_utc` is computed from the **real signal bar** in `src/v1_tickets/fx.py:167`
  (`signal_close = signal_open + M15` from an actual M15 candle), not synthesized. RC1 now
  keeps that real close on stale-withheld READY tickets; before the fix, the gate withheld
  the ticket before attaching it, so downstream classification had no trigger close.
- Nothing is fabricated for tickets that legitimately have no trigger: the gate adds no
  `signal_close_utc` to engine `NO_TRADE` tickets, and `actionability._trigger_bar_close()`
  falls back only through real fields (`signal_close_utc` → `signal_timestamp` + one trigger
  TF → legacy `data_close`); with none available it still fails closed as
  `INSUFFICIENT_DATA / TRIGGER_TIMEFRAME_UNKNOWN`.
- Runtime probe in this container (pure, no broker/network): a stale-gated READY at
  17:56Z kept `signal_close_utc = 2026-10-07T07:15:00+00:00` exactly; a stale-gated
  NO_TRADE emitted **no** `signal_close_utc` key.
- Frozen replay of the recorded 2026-10-07T17:56Z eight-evaluation run (reconstructed from
  the archived journal): `EXPIRED=6, NO_TRADE=2`, zero `TRIGGER_TIMEFRAME_UNKNOWN`; unfixed
  behavior reproduced the recorded `TTU=7` (locked in by
  `test_frozen_replay_2026_10_07`).

## 4. Tests (this environment: Linux cloud container, Python 3.11.2, pytest 9.1.1)

Six existing regression suites guarding the stale-gate / actionability path:

```
python -m pytest -q tests/test_stale_gate_trigger_close.py \
  tests/test_actionability_and_canonical_ticket.py tests/test_mt5_provider_integration.py \
  tests/test_mt5_candles_readonly.py tests/test_d6_actionability_suppressed.py \
  tests/test_d6_ready_authority.py
```

| Suite | Result |
|---|---|
| `test_stale_gate_trigger_close.py` | 18 passed |
| `test_actionability_and_canonical_ticket.py` | 19 passed |
| `test_mt5_provider_integration.py` | 29 passed |
| `test_mt5_candles_readonly.py` | 19 passed |
| `test_d6_actionability_suppressed.py` | 8 passed |
| `test_d6_ready_authority.py` | 13 passed |
| **Total** | **106 passed, 0 failed** |

Additional: full suite `python -m pytest -q tests/` → **1496 passed, 3 skipped, 0 failed**
(101–111 s). Environment note: the first full run reported 4 failures in
`test_crypto_opportunity_scanner.py` / `test_research_market_dataset.py`; all four were
missing optional packages (`fastapi`, `pyarrow`, and companions) in the fresh venv, not
code defects — after `pip install fastapi pyarrow uvicorn pydantic httpx` the same tests
pass. No test file was modified.

## 5. Authority boundary

- Zero changes to strategy YAML, the registry, thresholds, sessions, or sizing rules.
- Zero changes to `execution/`, `mt5/`, broker/MT5 call sites, or any demo/live flag.
- No strategy admission: `ST_ASIAN_SWEEP_5R_V1` authority (`demo_authorized: false`,
  D6 `SHADOW_INFO_ONLY` READY gate) untouched; this PR references it only as evidence of
  what the already-merged fix does.
- This is a documentation-only PR independent of, and non-blocking for, the scoped
  ST_ASIAN_SWEEP_5R_V1 v1.1.2+ admission review (PR #62 lineage): it records that the
  stale-gate fix that admission depends on is landed and regression-green.
- `BROKER_MUTATIONS=0`, `STRATEGY_ADMISSIONS=0`, `TELEGRAM_AUTHORITY_CHANGED=FALSE`.

## 6. Not claimed

- No live open-window evaluator run was performed here (the upstream PR records the same
  boundary; the next runtime milestone remains AGP-LIVE-01).
- This verification does not refresh host evidence; the Windows-host runs recorded in the
  original mission remain the live-environment evidence of record.
