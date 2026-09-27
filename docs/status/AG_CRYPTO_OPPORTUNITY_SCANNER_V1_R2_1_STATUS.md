# AG Crypto Opportunity Scanner V1 R2.1 Status

Date: 2026-09-27

Classification: `CRYPTO_OPPORTUNITY_SCANNER_V1_R2_1_READY_FOR_REAUDIT`

Commit status: not created, per the user's instruction to hold commit creation.

## Lineage and worktree provenance

Vulnerable base SHA: `e675a0126ab652a7be22cb46df0c7dad5370c16e`
Vulnerable base tree: `3fe96520e5d96e936a9e4ae43c9d38cf77f384cb`
R2.1 commit SHA: `NOT_CREATED`
Branch: `fix/crypto-scanner-v1-r2-1-market-identity`

At task entry, `CURRENT_HEAD` was the vulnerable base SHA, `CURRENT_HEAD_TREE` was `3fe96520e5d96e936a9e4ae43c9d38cf77f384cb`, and the dirty-worktree tree was `e8351440efa7f0b0ea82da76001c4307f61ab0e0`. `WORKTREE_STATUS` was seven modified tracked files, one untracked status path, and no staged changes. The complete entry `git diff`, `git diff --cached`, and status were captured at `C:\Users\aungp\AppData\Local\Temp\crypto-scanner-r2-1-preexisting.patch`, `C:\Users\aungp\AppData\Local\Temp\crypto-scanner-r2-1-preexisting-cached.patch`, and `C:\Users\aungp\AppData\Local\Temp\crypto-scanner-r2-1-preexisting-status.txt`. Those seven tracked edits were remediation-aligned but authorship cannot be established, so classify their entry provenance as `UNKNOWN` (pre-existing at entry). The untracked status file contained 3,868 zero bytes; it was preserved at `C:\Users\aungp\AppData\Local\Temp\crypto-scanner-r2-1-preexisting-status-artifact.bin` before replacement with this evidence. No unrelated paths were found in the entry diff. No R2.1 commit has been created.

The clean exploit reproduction ran from a separate clean checkout at the vulnerable base SHA/tree above. It requested BTCUSDT and received 720 valid candles with `result.symbol=ETHUSDT`. The feed accepted all 720 candles, the scanner returned `OPPORTUNITY_UPDATED`, formed a REAL/BYBIT candidate, and persisted one candidate.

## Remediation

`src/execution_runtime/bybit_linear_perp_feed.py` validates Bybit's response `category` and exact uppercase `symbol` before candle parsing. Missing, null, empty, malformed, whitespace/case-mutated, and wrong symbols fail closed. Kline response metadata returns category and symbol; instrument-info response metadata also returns category and a symbol list. Both identity fields are required and must match the linear BTCUSDT request. Instrument metadata now selects an exact BTCUSDT entry and rejects absent matches; the former first-entry fallback is removed.

The feed returns a list-compatible candle batch carrying the validated symbol and timeframe. The scanner requires that verified batch and checks both values against BTCUSDT/M5 before constructing REAL provenance, evaluating the strategy, or persisting. The batch cannot be constructed or relabeled through its ordinary public constructor/attributes.

Bybit's documented public response contract identifies category and symbol for kline and instrument-info responses. Category is required by this adapter and missing category fails closed. Candle interval is not returned as response identity metadata; the request interval is applied to the kline rows, so no unsupported response timeframe field is inferred.

## Verification

Environment: Windows, Python 3.14.0, pytest 8.3.5. All Bybit HTTP tests use deterministic offline fixtures; no live Bybit request was made.

- `python -m pytest -q tests/test_crypto_opportunity_scanner.py` — 31 passed, 1 Starlette/httpx deprecation warning.
- `python -m pytest -q tests/test_bybit_linear_perp_feed.py` — 40 passed.
- Affected functional and authority selection across feed, scanner, Opportunity contracts/engine/store/events/import boundaries, API, proposal formation/eligibility, and execution-containment tests — 310 passed, 1 deprecation warning.
- `tests/test_edge_ai_architecture_boundaries.py` — 4 passed, 1 failed. The failure is the historical `test_production_runtime_and_authority_files_match_frozen_base` broad-tree comparison against `1a8e7c5d922ba48423dca1b7858f8895afe0d66f`; the R2 status already records that this guard fails from the scanner base through R2. No guard or waiver was changed.
- The broad non-live suite (`python -m pytest -q -m "not slow and not live_mt5"`) was interrupted at roughly 40% after several failures appeared. Pytest did not emit a completed summary; the failure set is therefore `UNKNOWN` and the full suite is not claimed as passing. Slow historical walks and live MT5 tests were excluded. No network, private venue, or broker operation was invoked by this remediation.
- Compilation/import checks and final diff checks are pending completion of the current validation pass.

## R2 provenance and persistence controls

Offline scanner tests cover caller-created REAL windows, direct helper escalation, fixture and replay mode preservation, missing/unverified feed identity, scanner identity mismatch, and REAL candidate persistence boundaries. Wrong/missing/null/empty/malformed/case-mutated response identities and category mismatches are rejected before strategy evaluation; rejection tests assert no candidate is persisted. Correct-symbol fake HTTP responses pass through the actual feed validator before the test-only scanner composition can form a REAL candidate.

No registry, proposal, owner-decision, strategy, risk, MT5, order, scheduler, or frontend authority was changed. No private Bybit API, Bybit order, MT5 order-check/send, position, CanonicalProposal, or OwnerDecision action was invoked.

## Changed paths

- `src/execution_runtime/bybit_linear_perp_feed.py`
- `src/crypto_opportunity_scanner/scanner.py`
- `tests/test_bybit_linear_perp_feed.py`
- `tests/test_crypto_opportunity_scanner.py`
- `PROJECT_STATUS.md`
- `README.md`
- `docs/README.md`
- `docs/status/AG_CRYPTO_OPPORTUNITY_SCANNER_V1_R2_1_STATUS.md`

Next gate: `AG_CRYPTO_OPPORTUNITY_SCANNER_V1_R2_1_INDEPENDENT_REAUDIT` after the user authorizes creation of the local commit.
