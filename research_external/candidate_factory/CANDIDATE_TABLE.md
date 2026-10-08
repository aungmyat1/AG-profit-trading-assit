# AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 — Candidate table

PREREG_ID: `AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1`
PREREG_SHA256: `342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b`

| ID | Source | Session | SB Class | G1 | G2 | G3 | G4 | G5 | AG_REPRODUCED | Friction | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| INT_C001 | PR #33 `SESSION_TRADE_V2` | LONDON_NEWYORK + ASIAN_LONDON (EURUSD) | SB0 | PASS | PASS | PASS (EURUSD) / HOLD_DATA (GBP/JPY/XAU) | PASS | EXACT | TRUE | FAIL (gross & net negative) | **REJECTED** |
| INT_C002 | PR #34 `ST_MTF_CONTROL_SHIFT_V1` | LONDON_NEWYORK + ASIAN_LONDON (EURUSD) | SB0 | PASS | PASS | PASS (EURUSD) / HOLD_DATA (GBP/JPY/XAU) | PASS (incl. warm-up invariance) | EXACT | TRUE | NOT_EVALUATED (0 trades) | **HOLD_SAMPLE_REQUIRED** |
| OSS_FX_C001 | Zarattini & Aziz (2023) ORB, rule-extracted | LONDON_NEWYORK (EURUSD) | SB4 | PASS (AG-operationalized) | PASS | PASS (EURUSD) | PASS | MATERIAL_DEVIATION | TRUE | FAIL (gross PF<1.3; net negative) | **REJECTED** |
| OSS_CRYPTO_C001 | Donchian/Turtle System Two, rule-extracted | N/A (BTC/ETH) | SB5 | PASS | FAIL_AS_SOURCED | FAIL (no data) | PASS_BY_SOURCE_DESIGN | NOT_EVALUATED | FALSE | NOT_EVALUATED | **HOLD_DATA** |
| OSS_CRYPTO_C002 | freqtrade `DoubleEMACrossoverWithTrend` | N/A (BTC/ETH) | SB3 | HOLD_SPEC | FAIL_AS_SOURCED_PRESUMED | FAIL (no data) | NOT_EVALUATED | NOT_EVALUATED | FALSE | NOT_EVALUATED | **HOLD_DATA** |

N_CANDIDATES = 5. N_TRIALS = 5 (INT_C001×2 cycles, INT_C002×2 cycles, OSS_FX_C001×1).
DEV_REPLAY_COUNT = 5 (of MAX_DEV_REPLAYS=6). PROMOTE_TO_FREEZE_CAMPAIGN = 0.

No candidate reached `WATCH`, `OPPORTUNITY`, or `TICKET_READY`. No candidate's
`LOGIC_VERIFIED` or `EDGE_VERIFIED` changed from its default `FALSE`.

## Addendum: INT_C002 diagnostic follow-up (AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1)

A separate, later mission re-ran INT_C002 under its own new, frozen prereg
(`PREREG_MTF_LONGER_SAMPLE_R1.json`) with genuinely longer D1/H4 warm-up history (no
bounded tail-window truncation). Verdict is unchanged (`HOLD_SAMPLE_REQUIRED`, 0
trades both cycles); the longer history ruled out "insufficient D1/H4 warm-up" as the
cause and located a sharper bottleneck one stage later (`H1_CONTROL_SHIFT`). See
`candidates/INT_C002_LONGER_SAMPLE_R1.json` and
`docs/status/AG_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1_STATUS.md`. This row above
(INT_C002) is left exactly as originally reported; this addendum does not edit it.
