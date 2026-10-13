# AGP-C25 OSS differential verification (2026-10-14)

Class: EVIDENCE + PROPOSALS. No engine, contract, registry, READY or flag change. Owner scope: the 60 committed
recorded days only (amend); extended replays (step 4) dropped. Oracle results are REFERENCE evidence, never
authority (AGENTS.md OSS-FIRST).

Command: `TQDM_DISABLE=1 python scripts/c25_oss_differential.py --out artifacts/oss_differential/c25_report.json`
(seed 20261014; byte-reproducible, sha256 `2d52d68e269aea77cf87312e305b054cca4b06e0e6ed8bb311e2827fd88161e2`). Harness history and first-run divergences:
[C25_HARNESS_CHANGE_LOG](C25_HARNESS_CHANGE_LOG.md).
Oracle pins: `research_external/requirements-oracle.txt`. Environment: Linux web sandbox, no network, no MT5.

## Results

| Check | ASW v1.1.3 | CCFD 1.0.0 |
|---|---|---|
| Outcome oracle (backtesting.py, identical entry/SL/TP1/horizon/bar path) | 54/55 AGREE (98.2%), 1 SPEC_DIFFERENCE | 6/7 AGREE (85.7%), 1 SPEC_DIFFERENCE |
| Range cross-check (pandas-ta donchian) | session box 55/55 | previous-UTC-day reference 7/7 |
| Sweep oracle (smartmoneyconcepts) | n/a | sweep level 7/7 (100%), MSS broken swing 7/7 (100%) |
| L3 fuzz, owner definition (truncate at signal close / future perturb / signal-bar perturb) | 274 cases, **172 FAIL** (all signal-bar level changes; truncation 0, future 0) | 7 cases, 0 FAIL |
| L3 supplementary (latest bar after the signal bar perturbed) | 269 IDENTICAL, 5 N/A | 3 IDENTICAL, 4 N/A |

## ASW: the 219 excluded tickets

The 219 excluded tickets are **unique signals, not repeated scan records**:

- The harness emits one ticket per symbol x session x fixture day, so 274 tickets give 274 unique keys.
- 217 fail `TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2` and 2 fail `TP1_NOT_BEYOND_ENTRY`.
- The engine blocks all of them (TICKET_BLOCKED; `src/v1_tickets/target_geometry.py`).
- The oracle still ran on them as supplementary: 215 AGREE, 4 SPEC_DIFFERENCE, 0 defects.

**Finding:** ASW v1.1.3 emits geometry-invalid tickets at 80% overall (219/274) on the 60d data:

| Scope | Signals | Geometry-invalid | Rate |
|---|---|---|---|
| EURUSD x ASIAN_LONDON | 39 | 32 | 82.1% |
| EURUSD x LONDON_NEWYORK | 33 | 26 | 78.8% |
| GBPUSD x ASIAN_LONDON | 42 | 28 | 66.7% |
| GBPUSD x LONDON_NEWYORK | 37 | 30 | 81.1% |
| USDJPY x ASIAN_LONDON | 34 | 32 | 94.1% |
| USDJPY x LONDON_NEWYORK | 28 | 20 | 71.4% |
| XAUUSD x ASIAN_LONDON | 26 | 23 | 88.5% |
| XAUUSD x LONDON_NEWYORK | 35 | 28 | 80.0% |

CCFD signals are the deduped `ENTRY_VALID` tickets of the recorded 60d dataset. One ticket is excluded:
BTCUSD LONG 2026-09-13 17:05, `NO_TRADE_TARGET_GEOMETRY`.

## Outcome divergences (all classified; no ENGINE_DEFECT, no ORACLE_DEFECT)

| Case | Class | Cause |
|---|---|---|
| ASW USDJPY LONDON_NEWYORK 2026-08-26 LONG | SPEC_DIFFERENCE | bar gapped through TP1: repo resolver books TP1 at the level (3.28R, `src/v1_tickets/outcome.py:53`), backtesting.py fills at the bar open (3.68R) |
| CCFD BTCUSD SHORT 2026-10-09 18:40 | SPEC_DIFFERENCE | dataset ends before the 24h horizon: repo resolver returns DATA_INSUFFICIENT (`src/v1_tickets/outcome.py:56`), backtesting.py finalizes at the last bar |

Both are documented resolver conventions (conservative level fill; never resolve past available data).

## DATA_INSUFFICIENT_60D (final for this phase)

ASW v1.1.3 USDJPY x ASIAN_LONDON/LONDON_NEWYORK; ASW v1.1.3 XAUUSD x ASIAN_LONDON/LONDON_NEWYORK; CCFD 1.0.0
BTCUSD LONG. No verification claim is made for these scopes.

## Defects and proposals

Defects: none (no ENGINE_DEFECT, no ORACLE_DEFECT).

Proposals (owner decisions; no engine or contract change is made here):

- **P1. L3 signal-bar perturbation.** Under the owner definition, 172 ASW cases FAIL because shrinking the
  signal candle moves the levels the contract derives from that candle (stop, entry, targets). Direction and
  signal time never change, and truncation and future perturbation never change a signal. The owner rules
  whether this counts as repaint or as a fuzz-definition SPEC_DIFFERENCE.
- **P2. Geometry-invalid rate.** About 80% of ASW v1.1.3 signals are blocked by
  `FAIL_CLOSED_IF_TP1_BEYOND_TP2` (TP1 at the opposite session boundary lies beyond the 5R TP2). Review this
  in the next candidate version's target model, not in the frozen v1.1.3.

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Outcome/geometry oracle | backtesting.py 0.6.5 (AGPL-3.0) | WRAPPED | independent bracket fill engine; isolated research script, never imported by `src/` |
| Range/ATR cross-check | pandas-ta 0.4.71b0 (MIT) | REUSED | `donchian` gives an independent high/low of the same bars |
| Sweep/swing oracle | smartmoneyconcepts 0.0.27 (MIT) | REUSED | `previous_high_low("1D")`, `swing_highs_lows(5)` as independent sweep/MSS reference |
| Engine-side resolver and replay harness | repo `v1_tickets.outcome`, `scripts/asw_v112_60d_replay.py` | REUSED | existing authority, unchanged |
| L3 fuzz driver | none fit (engine-specific causality) | NEW (research script) | perturbation over repo engine entry points only |
| Dependency isolation | — | test | `tests/test_c25_oss_differential.py`: backtesting/pandas-ta never in runtime requirements or `src/` imports |

## Tests

`python -m pytest tests/test_c25_oss_differential.py -q` checks the committed report invariants and the pure
divergence classifier; it needs no oracle package.
