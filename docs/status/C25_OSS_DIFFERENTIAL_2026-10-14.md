# AGP-C25 OSS differential verification (2026-10-14)

Class: EVIDENCE + PROPOSALS. No engine, contract, registry, READY or flag change. Owner scope: the 60 committed
recorded days only (amend); extended replays (step 4) dropped. Oracle results are REFERENCE evidence, never
authority (AGENTS.md OSS-FIRST).

Command: `TQDM_DISABLE=1 python scripts/c25_oss_differential.py --out artifacts/oss_differential/c25_report.json`
(seed 20261014; byte-reproducible, sha256 `8af20fc62d7ce50d69ce977398eec4acb4623404d087ce31ba607360bb26f6ed`).
Oracle pins: `research_external/requirements-oracle.txt`. Environment: Linux web sandbox, no network, no MT5.

## Results

| Check | ASW v1.1.3 | CCFD 1.0.0 |
|---|---|---|
| Outcome oracle (backtesting.py, identical entry/SL/TP1/horizon/bar path) | 54/55 AGREE (98.2%), 1 SPEC_DIFFERENCE | 6/7 AGREE (85.7%), 1 SPEC_DIFFERENCE |
| Range cross-check (pandas-ta donchian) | session box 55/55 | previous-UTC-day reference 7/7 |
| Sweep oracle (smartmoneyconcepts) | n/a | sweep level 7/7 (100%), MSS broken swing 7/7 (100%) |
| L3 causality fuzz (truncate / future perturb / last-bar perturb) | 274 cases, 0 FAIL | 7 cases, 0 FAIL, 0 NOT_EVALUABLE |

ASW: 219 further emitted tickets fail the engine's own L2 target-order gate (TICKET_BLOCKED, e.g. TP1 on the
wrong side of entry); they are listed as `engine_gated_geometry` and excluded from outcome comparison.
CCFD signals are the deduped `ENTRY_VALID` tickets of the recorded 60d dataset.

## Divergences (all classified; no ENGINE_DEFECT, no ORACLE_DEFECT)

| Case | Class | Cause |
|---|---|---|
| ASW USDJPY LONDON_NEWYORK 2026-08-26 LONG | SPEC_DIFFERENCE | bar gapped through TP1: repo resolver books TP1 at the level (3.28R, `src/v1_tickets/outcome.py:53`), backtesting.py fills at the bar open (3.68R) |
| CCFD BTCUSD SHORT 2026-10-09 18:40 | SPEC_DIFFERENCE | dataset ends before the 24h horizon: repo resolver returns DATA_INSUFFICIENT (`src/v1_tickets/outcome.py:56`), backtesting.py finalizes at the last bar |

Both are documented resolver conventions (conservative level fill; never resolve past available data).

## DATA_INSUFFICIENT_60D (final for this phase)

ASW v1.1.3 USDJPY x ASIAN_LONDON/LONDON_NEWYORK; ASW v1.1.3 XAUUSD x ASIAN_LONDON/LONDON_NEWYORK; CCFD 1.0.0
BTCUSD LONG. No verification claim is made for these scopes.

## Defects and proposals

Defects: none. Proposals: none (no divergence requires an engine or contract change).

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Outcome/geometry oracle | backtesting.py 0.6.5 (AGPL-3.0) | WRAPPED | independent bracket fill engine; isolated research script, never imported by `src/` |
| Range/ATR cross-check | pandas-ta 0.4.71b0 (MIT) | REUSED | `donchian` gives an independent high/low of the same bars |
| Sweep/swing oracle | smartmoneyconcepts 0.0.27 (MIT) | REUSED | `previous_high_low("1D")`, `swing_highs_lows(5)` as independent sweep/MSS reference |
| Engine-side resolver and replay harness | repo `v1_tickets.outcome`, `scripts/asw_v112_60d_replay.py` | REUSED | existing authority, unchanged |
| L3 fuzz driver | none fit (engine-specific causality) | NEW (research script) | perturbation over repo engine entry points only |

## Tests

`python -m pytest tests/test_c25_oss_differential.py -q` checks the committed report invariants and the pure
divergence classifier; it needs no oracle package.
