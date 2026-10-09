# AG Asian Sweep V1.2 Logic Freeze R2 Status

Date: 2026-10-07  
Strategy: `ST_ASIAN_SWEEP_5R_V1@1.2.0`  
Verdict: **NOT_VERIFIED**

## Freeze order

The owner packet and complete contract were committed before implementation/replay work:

- freeze commit: `6c483fd834e772f9f41179ef939dd4eb4d082286`
- freeze tree: `905e13b018a896de9ee82238cd887620a2335966`
- contract hash: `c96221e69ad10bd016d072688c3cf791caaac9afe4bdb74be289cc50f5b34770`
- canonicalization: UTF-8 YAML bytes with CRLF normalized to LF

No contract rule was changed after replay began. Frozen v1.1.1 SHA-256 remains
`baed22b718e9017f291808063c62d3eda6d00ceb3b8ea89cc071919b8530f9cf`.

## Implemented proofs

A pure production evaluator and separately coded contract-only reference evaluator were
added. Focused tests prove close entry, 25% stop, wick clearance rejection, target order,
75%/25% split with breakeven action, half-open 15-minute expiry, fixed UTC, both spread
gates, deterministic future isolation, batch/stream parity, and synthetic differential
parity. Existing `v1_tickets.logic_gate` evidence shapes are reused by the V1.2 delta.
No external dependency was added to production or test requirements.

Focused result: `66 passed` across V1.2, existing logic-gate, and authority tests.

## Mandatory blocker

The committed “23 recorded sweeps” aggregate is a geometry study, not 23 replay-complete
inputs. Of 23 rows:

- 13 omit the confirmation-candle close;
- all 23 omit the decision timestamp needed to prove close time and expiry;
- authoritative contemporaneous spread is unavailable for the complete set;
- part of the set is `LONDON_NEWYORK`, outside the frozen V1.2 `ASIAN_LONDON` scope.

Only 10 rows permit close-based geometry reconstruction, and none permits the complete
required signal-by-signal comparison. A parallel blind agent/worktree was not available;
the reference is a separate pure code path, but blind authorship is not claimed. Missing
data was not inferred. Therefore `REFERENCE_ENGINE_PARITY` for all 23, blind-reference
independence, and complete golden replay evidence are blocked, which makes
`LOGIC_VERIFIED = FALSE` under the all-mandatory-proofs rule.

## Recorded diagnostic funnel

| Stage | Count | Percent of 23 |
|---|---:|---:|
| Entry close present | 10 | 43.4783% |
| 25% stop formula evaluable/pass | 10 | 43.4783% |
| Wick clear pass | 5 | 21.7391% |
| Target order pass | 10 | 43.4783% |
| Absolute spread pass | 0 proven | 0% |
| Spread-R pass | 0 proven | 0% |
| All logic gates pass | 0 proven | 0% |

Zero means **not proven from the complete recorded evidence**, not necessarily failed in
market behavior. No outcome or profitability result was used to modify the contract.

## Authority and safety

- economic status: `NOT_VERIFIED`
- edge status: `NOT_VERIFIED`
- ticket-ready authority: `FALSE`
- demo/live authorization: `FALSE`
- broker mutation count: `0`
- host/Telegram acceptance: `BLOCKED_RESOURCE`

The exact V1.2 identity is not registered as `LOGIC_VERIFIED` and cannot emit
`TICKET_READY`. `SESSION_TRADE_V1` remains unchanged and adapterless.

## Next executable step

Produce a sealed 23-case **ASIAN_LONDON-only** dataset containing complete reference and
trade candles, UTC timestamps, symbol, admitted spread, and dataset hashes. Run the
unchanged frozen production and reference evaluators over it. Any semantic disagreement
or rule change requires a new strategy version; it must not alter V1.2.0.
