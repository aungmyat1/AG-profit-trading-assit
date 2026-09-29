# WP-7A Canonical Instrument Registry V1 — status

Date: 2026-09-29. Classification: **CANONICAL_INSTRUMENT_REGISTRY_V1_READY_FOR_AUDIT**.

## Lineage

| Item | Value |
|---|---|
| Base | `1564769ac3bd43a3b5aceaa37aa85cc662906e95` (frozen, audited AG_TRADE_TICKET_V1; tree `54fa8e69`) — unmodified ancestor |
| Branch | `feat/wp7a-canonical-instrument-registry-v1` (worktree `D:/ddev/AG-wp7a-instrument-registry`) |
| origin/main | `accf063` (= `4bbba31` + PR #12, MT5 MCP launcher under `web/scripts`, docs, README); contains neither the platform lineage nor the TradeTicket |
| platform/fx-opportunity-v2 | `ebc7152` (after `76348c7`: spread-collector evidence and `fx_friction_capture` only) |
| INTEGRATION_STRATEGY | `DEPEND_ON_AUDITED_LINEAGE`: WP-7A commits sit on top of `1564769`, and no TradeTicket diff is replayed. Neither main's nor the platform's newer commits touch WP-7A surfaces, so a later merge is non-overlapping. |

## What exists

- **Registry file:** `config/instruments/registry/instruments-v1.0.0.yaml` (schema `AG_CANONICAL_INSTRUMENT_REGISTRY_V1`).
  - It contains only `FX.EURUSD` → `VT_MARKETS_MT5` / `VTMarkets-Demo` / `EURUSD`, enabled, `SPOT_FX`, base EUR, quote USD.
  - Optional future fields are `settlement_currency`, `contract_multiplier` and `instrument_subtype`.
  - The file's content fingerprint is pinned in `REGISTRY_VERSIONS`. Editing a published version in place raises `RegistryIntegrityError`, and an unpinned version is `UNKNOWN_REGISTRY_VERSION`.
- **`src/instrument_registry/identity.py`:** the two models, resolution, and the metadata field classes.
  - `CanonicalInstrumentIdentity` and `BrokerMetadataSnapshot` are separate models with separate fingerprints. The metadata fingerprint excludes `observed_at` and `source`.
  - `resolve_identity` handles one instrument, fail-closed. `resolve_many` resolves several independently.
  - Metadata field classes:
    - IDENTITY_CRITICAL: symbol, server, currency_base, currency_profit.
    - TRADING_CRITICAL, pinned: digits, point, tick_size, contract_size, volume_min, volume_max, volume_step.
    - TRADING_CRITICAL, required but not pinned: tick_value, which depends on the account currency.
    - INFORMATIONAL: trade_mode, execution_mode, filling_mode.
- **`src/instrument_registry/gates.py`:** the MarketState identity gate and the TradeTicket instrument envelope.

Failure states:

- `UNKNOWN_CANONICAL_INSTRUMENT`
- `UNKNOWN_REGISTRY_VERSION`
- `VENUE_NOT_CONFIGURED`
- `SERVER_MISMATCH`
- `BROKER_SYMBOL_DRIFT`
- `INSTRUMENT_DISABLED`
- `BROKER_METADATA_MISMATCH` (with the mismatched field names)
- `BROKER_METADATA_UNAVAILABLE`

Exact-match policy: symbols and servers are compared with `==`. There is no prefix or suffix stripping, no case folding, no nearest match, no alias creation and no AI. `drift_evidence_symbols` is report-only and is never used to resolve.

## Live broker evidence (read-only, 2026-09-29)

`artifacts/validation/CANONICAL_INSTRUMENT_REGISTRY_V1/EURUSD_VTMARKETS_DEMO_BROKER_EVIDENCE_2026-09-29.json`. The probe used only `initialize`, `account_info().server`, `symbol_info` and `symbols_get`. There was no `symbol_select`, no order or position API, and the login and account number were not recorded.

- **Account:** server `VTMarkets-Demo`, DEMO account in USD.
- **EURUSD metadata:** digits 5, point 1e-05, tick_size 1e-05, tick_value 1.0, contract_size 100000, volume 0.01/100/0.01, currencies EUR/USD, trade_exemode 2, filling_mode 2. Identity resolves: `RESOLVED`.
- **Exposed names containing EURUSD:** `EURUSD` and `EURUSD-VIP`. `EURUSD-VIP` is a real drift candidate and is never remapped.
- **`trade_mode = 0` (SYMBOL_TRADE_MODE_DISABLED) at observation time.** This is INFORMATIONAL in V1: it does not affect identity or PREPARED tickets, but it **blocks any future Demo-execution step** until it is explained.

## Symbol drift workflow (no auto-remediation)

Example: expected `FX.EURUSD → VT_MARKETS_MT5 → VTMarkets-Demo → EURUSD`, but the broker exposes only `EURUSD+`. The result is `BROKER_SYMBOL_DRIFT`, and it records:

- the expected symbol;
- the observed symbol;
- the registry version;
- the venue and server;
- the metadata snapshot fingerprint.

Evaluation stops for that instrument only. Recovery is human-governed:

1. detect;
2. block;
3. inspect the metadata;
4. publish a new registry version file and pin;
5. run the tests and the audit;
6. resume.

## MarketState gate

`gate_market_state(resolution, market_state)` makes a MarketState AUTHORITATIVE only if all of these hold:

- the identity RESOLVED;
- `market_state.symbol` equals the identity's FX platform symbol (base + quote);
- for REAL data, every server-clock record's `server` equals the registry server.

Otherwise:

- `MARKETSTATE_AUTHORITY = BLOCKED`, although `market_data_readable` may still be true;
- `OPPORTUNITY = NOT_EVALUATED`;
- `PROPOSAL = BLOCKED` and `TRADETICKET = BLOCKED`.

The live runner and scanner are not rewired in V1; wiring them is the next step.

## TradeTicket integration plan

The frozen `AG_TRADE_TICKET_V1` (`1564769`) is not modified. `envelope_for_ticket(ticket, resolution)` produces a hashed `AG_TICKET_INSTRUMENT_ENVELOPE_V1` carrying:

- `ticket_id` and `ticket_semantic_fingerprint`;
- `canonical_instrument_id`, `instrument_registry_version`, `venue_id`, `venue_symbol` and `server`;
- `instrument_identity_fingerprint` and `broker_metadata_fingerprint`.

It fails closed on:

- an identity failure;
- a ticket that fails verification;
- a mismatch between the ticket and the identity in instrument, venue symbol, server or environment.

Folding these fields into the ticket itself would be an `AG_TRADE_TICKET_V2` governance decision with its own audit.

## OSS

No OSS is reused. The inventory found `fx_opportunity.instruments` (platform market facts; reused as a consistency cross-check and left unchanged) and `mt5.symbol_resolver` (suffix resolution already disabled; not imported by `identity.py`). `CUSTOM_BUILD_REASON = AG_SPECIFIC_IDENTITY_AND_GOVERNANCE_CONTRACT`.

## Containment

`identity.py` imports no MT5 and no execution code, as a fresh-interpreter test proves. `gates.py` loads MetaTrader5 transitively only through the frozen `trade_ticket` → `mt5.symbol_resolver` type import; it never calls it, and no execution roots are loaded. Order-check, order-send and other execution mutations are all unreachable.

## Tests (2026-09-29, Windows dev box; no MT5 contact in tests)

- `python -m pytest tests/test_instrument_registry_v1.py -q` → 44 passed.
- `python -m pytest tests/test_trade_ticket_vertical_slice.py tests/test_opportunity_*.py tests/test_proposal_*.py tests/test_fx_opportunity_*.py -q` → 430 passed.

## R1 — registry path determinism (2026-09-29)

**Scope.** Arena audited `9b185e7` as `CANONICAL_INSTRUMENT_REGISTRY_V1_AUDIT_PASS`, with 0 blocking and 4 nonblocking findings. R1 remediates only one of them: registry resolution depended on the process cwd.

**The defect, reproduced on `9b185e7`.** From `scripts/`, `src/` or a temp directory, the published `instruments-v1.0.0` resolved as `UNKNOWN_REGISTRY_VERSION`, so no envelope was produced.

**The fix.** `REGISTRY_DIR` is now `Path(__file__).resolve().parents[2] / "config" / "instruments" / "registry"`. This is the same package-anchored convention as `session_clock._CONFIG_PATH`. There is:

- no copy of the registry;
- no absolute machine path;
- no parent-directory search.

**Unchanged:**

- the pin and content fingerprint;
- `RegistryIntegrityError` and unknown-version handling;
- identity, metadata, the EURUSD mapping, the gate and the envelope schema;
- `src/trade_ticket`.

**Proof.** `tests/_cwd_envelope_probe.py` runs `resolve_identity` and `envelope_for_ticket` after chdir to the repo root, `scripts/`, `src/` and a temp directory. All four give an identical `RESOLVED` result: `instruments-v1.0.0`, identity fingerprint `6a781d60…`, metadata fingerprint `1455483d…`, envelope fingerprint `093beeda…`.

**Residual, out of scope, pre-existing.** Importing `instrument_registry.gates` still requires the repo-root cwd. It imports the frozen `trade_ticket`, which imports the platform `fx_opportunity` package, and that package loads `config/instruments/fx_opportunity_instruments.yaml` and the pilot configs from cwd-relative paths at import time. Fixing this needs a change to audited platform code, so the probe performs its imports at the repo root. `identity.py` has no such dependency.

**Tests.** `tests/test_instrument_registry_v1.py`: 46 passed. Regression: 430 passed.
