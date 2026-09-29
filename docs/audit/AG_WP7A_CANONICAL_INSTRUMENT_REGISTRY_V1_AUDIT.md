# WP-7A CANONICAL INSTRUMENT REGISTRY V1 — INDEPENDENT AUDIT

**Mission:** `WP7A_CANONICAL_INSTRUMENT_REGISTRY_V1_INDEPENDENT_AUDIT`
**Date:** 2026-09-29 · **Auditor branch:** `arena/01a0ebe9-ag-profit-trading-assit`
**Method:** isolated detached worktree; candidate never modified, merged or cherry-picked.
**Independent probes:** 129 auditor-written tests, removed after use; worktree verified pristine.

```
CLASSIFICATION = CANONICAL_INSTRUMENT_REGISTRY_V1_AUDIT_PASS
```

**Primary question — answered YES.** WP-7A establishes a deterministic, exact-match,
versioned canonical identity contract for `FX.EURUSD` on VT Markets Demo, and it does so
**without touching the frozen TradeTicket** (byte-identical) and **without weakening any
execution boundary** (still zero broker reachability).

---

## Identity and lineage

```
AUDITED_SHA   = 9b185e7986e49b960d5b0af686834943723ca0e5   (matches expected)
TREE_HASH     = 5ce8980e2fefc26b1f83921e1c39205d1b974f57   (matches expected)
LINEAGE_VALID = YES
```

`9b185e79` is a **single non-merge commit whose direct parent is the frozen TradeTicket
`1564769a`**. Not merged into `origin/main`. The whole change is **additive: 1066
insertions, 0 deletions**, across 10 files — 3 production modules, 1 registry, 1 fixture,
1 test file, 1 evidence artifact, 3 docs.

## `FROZEN_TRADETICKET_IDENTITY = BYTE_IDENTICAL`

The strongest possible result: the **entire `src/trade_ticket/` tree object is unchanged**,
so nothing inside it could have been touched.

```
src/trade_ticket  tree cd4053727a1acb9b338d11d525087518ecb3a978  (1564769a == 9b185e79)
  ticket.py       919334a81ee13220705af76b53322176659b9b8f  IDENTICAL
  qualification.py 07e36466075bcd4efecd34ea608b5c7e130e3b1f IDENTICAL
  sizing.py       febaee7dc49e37c4571b8bd3aaccdd03f7707614  IDENTICAL
```

Also `UNCHANGED`: `strategies/registry.yaml`, `config/trading.demo.yaml`, `src/opportunity`,
`src/proposal_envelope`, `src/mt5`, `src/fx_opportunity`, `src/strategy_engine`,
`src/post_asian_pilot`. Still `ABSENT`: `src/execution`, `src/authorization`,
`src/ticket_delivery`, `src/owner_decision`, `src/strategy_manager`.

The identity fields are carried by an **external envelope**, not by new ticket fields —
the correct call, since adding them to the ticket would be a TradeTicket V2 decision.

---

## `REGISTRY_VERSIONING = IMMUTABLE_PINNED_CONTENT_FINGERPRINT`

Each published version is a separate file whose parsed-content fingerprint is pinned in
`REGISTRY_VERSIONS`, re-verified on **every** load.

| Probe | Result |
|---|---|
| Committed file matches its pin | `322468278a…05d1b2` ✓ (independently recomputed) |
| In-place tamper under the same version (8 variants: `venue_symbol`, `server`, `enabled`, `base_asset`, `product_type`, `expected_metadata`, added instrument, venue `environment` → `LIVE`) | **`RegistryIntegrityError` on all 8** |
| Integrity error swallowed by `resolve_identity`? | **No — it propagates**, never silently resolves |
| Comment / CRLF-only change | accepted (fingerprint is over parsed content, so formatting is not identity — correct) |
| File on disk but not pinned (the test fixture) | **rejected**; presence never implies publication |
| `registry_version` recorded on every identity | yes |

```
UNKNOWN_REGISTRY_VERSION (fail-closed): instruments-v1.0.1, instruments-v2.0.0,
  instruments-test-v1, "", "v1", "instruments-v1.0.0 " (trailing space) -> all fail closed
```

## `EXACT_MATCH_POLICY = EQUALITY_ONLY` · `FUZZY_MATCHING = NONE`

AST scan of `src/instrument_registry/`: **no** `lower/upper/casefold`, `startswith/endswith`,
`strip/replace`, `removeprefix/removesuffix`, no `re`, no `difflib`, no nearest-match, no AI.
(The single `replace` is `dataclasses.replace` — record copying, not string manipulation.)

**Drift cases — all `BROKER_SYMBOL_DRIFT`, all with `identity = None`:**

```
EURUSD+   EURUSD-VIP   EURUSD.a   eurusd   EURUSD.raw   EUR/USD
EURUSDm   _EURUSD      " EURUSD"  "EURUSD "  EURUSD.   EURUSD_i
XEURUSDX  EURUSDEURUSD      (containment is not a match)
```

Two sharper cases also block: exposed list lacking the exact symbol **cannot be rescued by
correct caller-supplied metadata**, and an exposed-OK / metadata-variant combination is
still drift. `drift_evidence_symbols` is **report-only** — it records `EURUSD-VIP` for human
review and provably never remaps.

**This is not hypothetical.** The broker evidence artifact shows this server really exposes
both `EURUSD` and `EURUSD-VIP` among 1242 symbols. With both exposed, resolution selects
`EURUSD` exactly and ignores the sibling.

```
SERVER_TESTS: VTMarkets-Live, VTMarkets-Demo2, vtmarkets-demo, "VTMarkets-Demo ",
  "", None, "Demo"  ->  SERVER_MISMATCH (7/7)
  metadata.server or metadata.venue_id disagreeing -> SERVER_MISMATCH with mismatched_fields
```

Unknown canonical ID (`FX.GBPUSD`, `fx.eurusd`, `EURUSD`, `""`, `CRYPTO.BTCUSD`) →
`UNKNOWN_CANONICAL_INSTRUMENT`. Unknown venue → `VENUE_NOT_CONFIGURED`. Disabled instrument
→ `INSTRUMENT_DISABLED` with no identity and no fingerprint; `enabled` requires literal
boolean `true`.

---

## `IDENTITY_MODEL` / `METADATA_MODEL` — cleanly separated

```
CanonicalInstrumentIdentity (registry-owned, versioned)  -- what the instrument IS
  canonical_instrument_id, asset_class, base_asset, quote_asset, product_type,
  venue_id, server, venue_symbol, enabled, registry_version,
  settlement_currency, contract_multiplier, instrument_subtype

BrokerMetadataSnapshot (observed, read-only)             -- what the broker REPORTS
  venue_id, server, symbol, currency_base, currency_profit, digits, point, tick_size,
  tick_value, contract_size, volume_min, volume_max, volume_step,
  trade_mode, execution_mode, filling_mode, source, observed_at
```

Identity carries **no** broker trading metadata (verified by set intersection). Mutating
`digits`, `point`, `trade_mode`, `volume_max`, `filling_mode` or `tick_value` **never**
changes `identity_fingerprint`. An identity change requires a new version file.

**Field classification — exhaustive and disjoint** (verified: every snapshot field is
classified; no overlap between classes):

| Class | Fields | Rule |
|---|---|---|
| `IDENTITY_CRITICAL` | `symbol`, `server`, `currency_base`, `currency_profit` | must equal registry identity |
| `TRADING_CRITICAL_PINNED` | `digits`, `point`, `tick_size`, `contract_size`, `volume_min`, `volume_max`, `volume_step` | present, finite, equal to `expected_metadata` |
| `TRADING_CRITICAL` unpinned | `tick_value` | required, finite, **> 0**; not pinned because it is account-currency dependent — correct |
| `INFORMATIONAL` | `trade_mode`, `execution_mode`, `filling_mode` | recorded + fingerprinted, never gating in V1 |

## `IDENTITY_FINGERPRINT` / `METADATA_FINGERPRINT` = `DETERMINISTIC_AND_COMPLETE`

- Every identity field is covered — mutating any one changes the hash, and all 13 mutations produce **distinct** hashes.
- Every metadata field is covered **except** `source` and `observed_at`, which are deliberately excluded so re-observing identical metadata hashes identically. Verified both ways.
- Stable in a **fresh interpreter** (subprocess): identical values.
- `identity_fingerprint != metadata_fingerprint`.

**The evidence artifact is independently reproducible**, which is the provenance result that
matters most here — I recomputed both claimed fingerprints from the artifact's own recorded
`symbol_info` and they match exactly:

```
identity_fingerprint  6a781d6092240571bb6a4636870fd8df5aaefc8438fb8f6543f069da275903c8  MATCH
metadata_fingerprint  1455483dbb19566a070dff8e259e33c2bd2d2551679f95950725e89957d248d6  MATCH
resolution status     RESOLVED                                                          MATCH
```

Collection method is recorded as read-only (`initialize`/`account_info.server`/`symbol_info`/
`symbols_get`; no `symbol_select`, no order or position API) and the login/account number is
deliberately **not** recorded.

## `METADATA_TESTS`

```
BROKER_METADATA_MISMATCH  (9/9, each naming the offending field, identity=None):
  digits, point, tick_size, contract_size, volume_min, volume_max, volume_step,
  currency_base, currency_profit
BROKER_METADATA_UNAVAILABLE (16/16):
  any of the 8 required numerics or 2 currencies = None; NaN; +Inf; -Inf;
  metadata=None; exposed_symbols=None; digits=True (bool is not a number)
tick_value <= 0 rejected; any positive finite tick_value accepted (account-currency dependent)
```

`PER_INSTRUMENT_ISOLATION` — one instrument's failure never blocks another:

```
{'FX.EURUSD': RESOLVED, 'FX.GBPUSD': BROKER_SYMBOL_DRIFT,
 'FX.USDJPY': RESOLVED,  'FX.AUDUSD': INSTRUMENT_DISABLED}
```

---

## `MARKETSTATE_GATE = FAIL_CLOSED_CHAIN_WIDE`

Positive control (essential, so the gate is not vacuously blocking):

```
GATE_POSITIVE_CONTROL: ('AUTHORITATIVE', 'MAY_EVALUATE', 'MAY_PROCEED', 'MAY_PROCEED')
```

Every failure collapses the whole chain to
`BLOCKED / NOT_EVALUATED / BLOCKED / BLOCKED` with `identity_fingerprint = None`:

| Trigger | Reason code |
|---|---|
| MarketState symbol ≠ platform symbol | `MARKET_STATE_INSTRUMENT_MISMATCH` |
| REAL data, empty or missing `server_clock` | `MARKET_STATE_SERVER_UNVERIFIED` |
| any clock record's server ≠ identity server (incl. one bad record among good ones, and a record with no `server` key) | `MARKET_STATE_SERVER_MISMATCH` |
| MarketState absent | `MARKET_STATE_MISSING` |
| identity unresolved (drift / server / unknown version / unknown ID / metadata mismatch / metadata absent) | the resolution status |

`REPLAY` mode correctly does not require a server clock. **Readability is separated from
authority**: `market_data_readable=True` while `marketstate_authority=BLOCKED` — data stays
inspectable without becoming trustworthy.

## `TICKET_INSTRUMENT_ENVELOPE = AG_TICKET_INSTRUMENT_ENVELOPE_V1, INTEGRITY_VERIFIED`

- **Binding verified:** `envelope_fingerprint` covers **every** field — mutating any one changes it, including `ticket_id` and `ticket_semantic_fingerprint`. Two tickets differing only in `ticket_id`, or only in `semantic_fingerprint`, yield three distinct envelope fingerprints.
- **Fail-closed on mismatch:** `TICKET_INSTRUMENT_MISMATCH`, `TICKET_VENUE_SYMBOL_MISMATCH` (incl. `EURUSD+` and `EURUSD-VIP`), `TICKET_SERVER_MISMATCH`, `TICKET_ENVIRONMENT_MISMATCH` (`LIVE`, `REAL`), `TICKET_VERIFICATION_FAILED` when the frozen `verify_ticket_dict` fails, and the resolution status when identity is unresolved. No envelope is emitted in any of these cases.
- Environment is read from the **registry venue**, not from the ticket — the ticket cannot assert its own environment.

## `TRADE_MODE_0_CLASSIFICATION = INFORMATIONAL_ONLY_CORRECTLY_RECORDED`

`trade_mode = 0` (`SYMBOL_TRADE_MODE_DISABLED`) was observed on this account. It is recorded
in the metadata fingerprint (`trade_mode=0` and `=4` hash differently) but does **not** gate
V1 identity — resolution is `RESOLVED` either way. That is right for an *identity* contract,
and the candidate explicitly flags that it **blocks any future Demo-execution step until
explained**. No overclaim.

## `EXECUTION_CONTAINMENT = INTACT`

```
BROKER_ORDER_CHECK_REACHABILITY       = NOT_REACHABLE
BROKER_ORDER_SEND_REACHABILITY        = NOT_REACHABLE
POSITIONS_GET_REACHABILITY            = NOT_REACHABLE
OTHER_EXECUTION_MUTATION_REACHABILITY = NOT_REACHABLE
```

- **Static (AST):** no executable reference anywhere in `src/instrument_registry/` to `order_send`, `order_check`, `positions_get`, `positions_total`, `order_calc_margin`, `order_calc_profit`, `symbol_select`, `initialize`, `login`, `shutdown`, `history_orders_get`, `history_deals_get`, `account_info`.
- **Runtime:** with all MT5 entry points replaced by recording stubs, six resolution paths (success, drift, server mismatch, metadata absent, metadata mismatch, unknown version) plus `gate_market_state` and `envelope_for_ticket` produced **`calls == []`**.
- **Purity:** the only file access is a single **read** of `instruments-v1.0.0.yaml`. No writes.
- `snapshot_from_symbol_info` only *reads attributes* of a caller-supplied object — the 14 names read are all metadata; no order/position names. Missing attributes stay `None`, never defaulted.

---

## Findings

```
BLOCKING_FINDINGS = NONE
```

### `NONBLOCKING_FINDINGS` (4)

1. **`gates.py` inherits the MT5 *import* surface from the frozen ticket.** `gates.py` imports `trade_ticket.ticket`, which transitively imports `MetaTrader5`. I verified this is **pre-existing and unchanged**: a fresh interpreter importing `trade_ticket.ticket` alone at the frozen commit yields the same `['MetaTrader5','mt5']`. `identity.py` imported alone is **pure (`[]`)**. The resolved module is the repo's local stub, which *raises* on any broker operation. Not introduced by WP-7A and not a reachability path — but the clean purity of `identity.py` is worth preserving in `gates.py` too (e.g. import `verify_ticket_dict` lazily) so the identity layer never depends on the MT5 import surface.
2. **No `verify_envelope()` helper.** Envelope tampering is *detectable* (the fingerprint covers every field) but each consumer must recompute it themselves. A small verifier mirroring `verify_ticket_dict` would make misuse harder. Same tamper-evident-not-tamper-proof caveat recorded in the R1 ticket audit applies: full re-forgery with a recomputed fingerprint is not detectable without an external anchor.
3. **`envelope_for_ticket` calls `load_registry(...)` with the default `REGISTRY_DIR`**, a relative path — so it depends on the process working directory, unlike `resolve_identity`, which accepts `registry_dir`. Worth threading `registry_dir` through before the runner wiring, or resolving `REGISTRY_DIR` against the package root.
4. **Registry content fingerprint is over parsed YAML**, so comments and line endings are not covered. This is the right choice (formatting is not identity), but it does mean the *documented* immutability warning in the file header is itself unpinned. Cosmetic.

### Not failures (correctly scoped, per mission)

- **Live runner not wired** — future integration work. The candidate states plainly: *"The live runner and scanner are not rewired in V1; wiring them is the next step."* No false claim, so not a V1 failure.
- Crypto identities intentionally absent, with the reasoning recorded (BTCUSD CFD / BTCUSDT spot / linear perp / inverse perp are distinct products needing distinct canonical IDs). Correct restraint.
- Only `FX.EURUSD` is in production scope, as specified.

---

## Tests

```
FOCUSED_TESTS    = 44 passed   (candidate tests/test_instrument_registry_v1.py)
INDEPENDENT_TESTS = 129 passed (auditor-written, all 23 mission items)
REGRESSION_TESTS = 816 passed, 4 skipped, 1 failed
```

The single failure is
`tests/test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`
(`ModuleNotFoundError: No module named 'api.app'`) — the **known pre-existing environment
failure**, reproduced at the frozen parent and in both prior audits. **Not a WP-7A
regression.** The suite grew 772 → 816 (+44), exactly the new tests, with no previously
passing test broken.

Two initial red results in my own probes were **mis-scoped probes, not candidate defects**
(`dataclasses.replace` matched a string-method blocklist; the MT5 import assertion ignored
the pre-existing baseline). Both were diagnosed, corrected, re-run, and are reported above
rather than hidden.

---

## Verdict

```
CLASSIFICATION = CANONICAL_INSTRUMENT_REGISTRY_V1_AUDIT_PASS

NEXT_STEP = WIRE_IDENTITY_GATE_INTO_LIVE_OPPORTUNITY_RUNNER_READ_ONLY
```

Wiring was **not** started during this audit. Before it begins, I recommend addressing
nonblocking finding 3 (working-directory dependence in `envelope_for_ticket`), since the
runner will execute from a different cwd than the test suite.

**Constraints honoured.** Candidate not modified, not merged, not cherry-picked; audit
worktree verified clean and removed; live runner not wired; execution not investigated
beyond containment checks; no broker contact; no order or position API exercised.
This document authorizes nothing.
