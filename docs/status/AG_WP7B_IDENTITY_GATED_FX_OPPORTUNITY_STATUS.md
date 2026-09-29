# WP-7B — canonical identity gate wired into the live FX Opportunity runner — status

Date: 2026-09-29. Classification: **IDENTITY_GATED_LIVE_OPPORTUNITY_READY_FOR_AUDIT**.

| Item | Value |
|---|---|
| Base | `471b1c026a04edc8ea34f61b0e6b2fce91c67000` (WP-7A R1, audited `PASS_WITH_NONBLOCKING_FINDING`) |
| Branch | `feat/wp7b-identity-gated-fx-opportunity` (worktree `D:/ddev/AG-wp7b-identity-gate`) |
| Code commit | `5fc8d1fbc6499b62286c2a0b2967982983e1e9a8` (the live run's recorded `application_lineage`) |
| Entrypoint | `scripts/run_fx_opportunity_once.py`. The `os.chdir(_REPO)` startup and the MT5 mutation-API blocking counters are unchanged. |

## What changed

- **New module:** `src/instrument_registry/fx_gated_scan.py`, composition only. The sequence is:
  1. Look up the platform symbol's canonical ID in the registry, exactly.
  2. Run `resolve_identity` with the observed server, the exposed symbol names from `symbols_get`, and the `BrokerMetadataSnapshot` from `symbol_info`.
  3. Only after identity RESOLVES, read the server-time provenance and the spread.
  4. Build the strategy-neutral MarketState with the platform's own `observe_market_state`, through `MemoFetch`.
  5. Run `gate_market_state`.
  6. Only when the gate is AUTHORITATIVE, run the unchanged `scanner.scan_symbol` on the same cached bars.
  7. The scanner's MarketState fingerprint must equal the gated one; otherwise the result is `MARKETSTATE_FINGERPRINT_DIVERGENCE`.
- **Symbols without a production mapping:** in `instruments-v1.0.0` these are GBPUSD and USDJPY. They report `CANONICAL_IDENTITY_NOT_CONFIGURED`, with no `symbol_info` read, no market-data read and no fallback to the raw-symbol path.
- **Script change:** the script's former `check_broker_spec` (digits/point) step is superseded by the registry's stricter metadata check.
- **Not changed:**
  - ST_ASIAN_SWEEP_5R_V1 and the runner/scanner;
  - `OpportunityCandidate` and ProposalEligibility;
  - sizing and `src/trade_ticket` (tree `cd405372`);
  - the registry file and pin;
  - `gates.py` and `identity.py`;
  - the GBPUSD/USDJPY production mappings.
- **Semantics check:** a test proves the gated scan summary equals the ungated scanner summary for identical inputs.
- **`trade_mode = 0`:** INFORMATIONAL for this read-only path. It neither blocks evaluation nor grants anything.

## Live read-only run (2026-09-29T15:11:10Z)

Evidence: `artifacts/validation/CANONICAL_INSTRUMENT_REGISTRY_V1/WP7B_LIVE_IDENTITY_GATED_RUN_2026-09-29T1511Z.json`. It was launched from a foreign cwd, with the candidate store outside the repo.

| | EURUSD | GBPUSD | USDJPY |
|---|---|---|---|
| Canonical identity | `FX.EURUSD` RESOLVED (`instruments-v1.0.0`, `VT_MARKETS_MT5`, `VTMarkets-Demo`, `EURUSD`) | CANONICAL_IDENTITY_NOT_CONFIGURED | CANONICAL_IDENTITY_NOT_CONFIGURED |
| Identity / metadata fingerprints | `6a781d60…` / `1455483d…` (same as the WP-7A evidence) | — | — |
| MarketState authority | AUTHORITATIVE (reference complete, 20 bars; 12 post-session bars; spread 0.1 pip) | BLOCKED | BLOCKED |
| Opportunity | MAY_EVALUATE → `NO_OPPORTUNITY` (decision EXPIRED, `NO_SETUP_BY_WINDOW_END`) | NOT_EVALUATED | NOT_EVALUATED |
| Proposal / TradeTicket | NO_PROPOSAL_AUTHORITY / NOT_CREATED | BLOCKED / BLOCKED | BLOCKED / BLOCKED |

- **Account:** broker `VT_MARKETS`, server `VTMarkets-Demo`, environment `DEMO`.
- **Mutation-API counters:** all 0 (order_send, order_check, positions_get and the rest).
- **EURUSD provenance:** MarketState fingerprint `92a7b099…`, lineage fingerprint `6e6f3bbf…`, evaluation fingerprint `fe908b35…`.
- **Time authority:** server-time period `SERVER_CONSENSUS` (UTC+3, week-bounded), with evidence symbols EURUSD and GBPUSD. This is the platform's existing shared server-time authority reading GBPUSD bars as clock evidence only; GBPUSD itself is not evaluated.
- **Output contents:** no login or account number.

## Tests (fixtures; no broker contact)

`tests/test_fx_identity_gated_scan.py` → 25 passed. It covers:

- the resolved path to MAY_EVALUATE, and equality with the ungated scanner;
- EURUSD+ and EURUSD-VIP drift (including VIP metadata while EURUSD is exposed);
- wrong server, metadata mismatch, metadata unavailable, unknown registry version and venue not configured. Each blocks before any data read or strategy run;
- GBPUSD and USDJPY not configured;
- the MarketState server mismatch;
- a time-authority failure;
- the fingerprint-divergence guard;
- `trade_mode = 0`;
- provenance;
- foreign-cwd startup;
- the entrypoint routing (no raw `scan_symbol` call);
- static, transitive and runtime containment.

The affected regression is 476 passed: `test_instrument_registry_v1`, `test_trade_ticket_vertical_slice`, `test_opportunity_*`, `test_proposal_*` and `test_fx_opportunity_*`.
