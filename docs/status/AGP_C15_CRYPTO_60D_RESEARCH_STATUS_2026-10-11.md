# C15 crypto 60-day research verification

**State:** research evidence awaiting independent review. No registry admission, READY, demo/live authorization, or broker calls.

Dataset: VT Markets demo `recorded_60d`, manifest SHA-256 `b2a5b8ec8ade615a82527dc72d223fb140322fd614aa220550918955628b86a7`. The capture records `VTMarkets-Demo` and `MT5_VT_MARKETS_DEMO`; OD1011-COMMISSION binds effective commission to 0 for that server under the authoritative account policy. Raw capture commission was absent; it is retained as `captured_commission_R: null` and is not described as an effective commission gap.

Candidate: `ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0`. Canonical frozen contract hash: `ac116e0aadcca33238d0ce2d2b327368f0faa3a6bfb6f8cfdd2cf5222ca6ecf7`. The replay identity and separate runtime identity record independently recompute this hash and match the runtime engine component. Candidate runtime binding remains `NOT_ADMITTED_RESEARCH_ONLY`.

| Symbol × direction × window | L1 | L2 | L3 | L4 | L5 | L6 | Entry-valid scans | Emissions | Withdrawn | Scope |
|---|---|---|---|---|---|---|---:|---:|---:|---|
| BTCUSD × LONG × WEEKDAY | PASS | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | 0 | 0 | 0 | NOT_VERIFIED |
| BTCUSD × SHORT × WEEKDAY | PASS | PASS | PASS | PASS | PASS | PASS | 77 | 2 | 0 | PASS |
| BTCUSD × LONG × WEEKEND | PASS | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | 0 | 0 | 0 | NOT_VERIFIED |
| BTCUSD × SHORT × WEEKEND | PASS | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | 0 | 0 | 0 | NOT_VERIFIED |
| ETHUSD × LONG × WEEKDAY | PASS | PASS | PASS | PASS | PASS | PASS | 354 | 3 | 0 | PASS |
| ETHUSD × SHORT × WEEKDAY | PASS | PASS | PASS | PASS | PASS | PASS | 72 | 1 | 0 | NOT_VERIFIED |
| ETHUSD × LONG × WEEKEND | PASS | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | 0 | 0 | 0 | NOT_VERIFIED |
| ETHUSD × SHORT × WEEKEND | PASS | PASS | PASS | PASS | PASS | PASS | 175 | 1 | 0 | NOT_VERIFIED |

BTCUSD WEEKEND remains `NOT_VERIFIED`: zero emissions do not exercise entry gates. The two verified scopes have 2 and 3 emissions respectively; this is thin logic coverage and does not imply edge. All 60 days and 17,280 scans per symbol completed with zero aggregate mismatches.

The frozen contract hash reported here is computed canonically from the current candidate YAML with the self-reference field blank. It does not match the `9a1f6759…` value requested in the PR handoff; independent review must resolve that identity discrepancy before any verification authority is considered.
