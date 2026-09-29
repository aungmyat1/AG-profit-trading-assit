# WP-7B — IDENTITY-GATED LIVE OPPORTUNITY: INDEPENDENT INTEGRATION AUDIT

**Mission:** `WP7B_INDEPENDENT_INTEGRATION_AUDIT`
**Date:** 2026-09-29 · **Auditor branch:** `arena/01a0ebe9-ag-profit-trading-assit`
**Method:** isolated detached worktree; candidate never modified, merged or cherry-picked.
No broker contact — committed live evidence plus deterministic fixtures only.
**Independent probes:** 36 auditor-written tests, removed after use; worktree verified pristine.

```
CLASSIFICATION = WP7B_IDENTITY_GATED_LIVE_OPPORTUNITY_AUDIT_PASS_WITH_NONBLOCKING_FINDINGS
```

**Primary question — answered YES.** WP-7B places the audited canonical identity gate in
front of live Opportunity evaluation by **pure composition**: every platform package,
the frozen TradeTicket, the registry and the WP-7A modules are byte-identical, and
execution capability is unchanged at zero.

---

## A1 — Identity and lineage

```
AUDITED_SHA   = 4b450ff36d9dc0940b0940613426d6e85e7c4450   (matches expected)
TREE_HASH     = 7203c98c7e167fd816b1ad2f6e35fb17b70aaacf   (matches expected)
LINEAGE_VALID = YES
```

The expected base `471b1c02` is an ancestor, reached through a **two-commit series**
(the direct parent is `5fc8d1fb`, not `471b1c02` — worth stating precisely, but not a
finding):

```
471b1c02 (WP-7A R1, audited)
  └─ 5fc8d1fb  feat: WP-7B identity gate   (code: module + entrypoint + tests)
      └─ 4b450ff3  docs(evidence): live run + status   ← audited HEAD
```

Frozen ticket `1564769a` and WP-7A `9b185e79` are both ancestors. `origin/main` is
unchanged at `accf0637` and **the candidate is not merged into it**.

## A2 — `DIFF_CONTAINMENT = PASS`

`471b1c02..4b450ff3` — 7 files, **+883 / −22**:

| File | Kind |
|---|---|
| `src/instrument_registry/fx_gated_scan.py` | **new integration surface** (+227) |
| `scripts/run_fx_opportunity_once.py` | entrypoint wiring (+60/−22) |
| `tests/test_fx_identity_gated_scan.py` | tests (+239) |
| `artifacts/.../WP7B_LIVE_IDENTITY_GATED_RUN_2026-09-29T1511Z.json` | live evidence |
| `PROJECT_STATUS.md`, `docs/README.md`, `docs/status/AG_WP7B_…_STATUS.md` | docs |

**Every other production path is byte-identical** (verified by git tree/blob hash, not by
reading diffs):

```
UNCHANGED: src/fx_opportunity  src/opportunity  src/proposal_envelope  src/strategy_engine
           src/post_asian_pilot  src/mt5  strategies/registry.yaml
           config/instruments/fx_opportunity_instruments.yaml
ABSENT   : src/execution  src/authorization  src/ticket_delivery  src/owner_decision
           src/strategy_manager
```

So the scanner, `ST_ASIAN_SWEEP_5R_V1`, `OpportunityCandidate`, `ProposalEligibility`,
sizing and TradeTicket are **not semantically edited at all** — the gate is composed in
front of them. The only `−22` lines are in the entrypoint, where the old inline
pre-checks were replaced by the gate call.

## A3 — EURUSD happy path

```
EURUSD_IDENTITY              = RESOLVED
EURUSD_METADATA              = VALID
EURUSD_MARKETSTATE_AUTHORITY = AUTHORITATIVE
EURUSD_OPPORTUNITY_RESULT    = NO_OPPORTUNITY (live) / OPPORTUNITY (fixture)
```

From the committed live run (`WP7B_LIVE_IDENTITY_GATED_RUN_2026-09-29T1511Z.json`,
`mode=LIVE`, `market_data_mode=REAL`, `account_environment=DEMO`,
`application_lineage=5fc8d1fb…` = the code commit):

| Field | Value |
|---|---|
| canonical ID | `FX.EURUSD` |
| venue / server | `VT_MARKETS_MT5` / `VTMarkets-Demo` (observed `VTMarkets-Demo`) |
| venue symbol | `EURUSD` (observed `EURUSD`) |
| resolution | `RESOLVED`, `mismatched_fields: []` |
| identity fingerprint | `6a781d60…275903c8` |
| metadata fingerprint | `1455483d…57d248d6` |

Both fingerprints are **identical to the values I independently recomputed during the
WP-7A audit**, which ties this live run to the audited registry lineage.

**The reported `NO_OPPORTUNITY` / `EXPIRED` / `NO_SETUP_BY_WINDOW_END` is coherent** — I
checked it against the artifact's own data rather than accepting the label:

- execution window ends `2026-09-29T15:00:00Z`, evaluated at `15:11:10Z` → the window **had** closed, so `EXPIRED` is correct;
- `reference_high_taken = false` and `reference_low_taken = false` → genuinely no setup formed, not a suppressed one;
- `reference_complete = true`, `reference_bar_count == reference_bars_expected == 20` → the absence of a signal is not an absence of data;
- `direction = null`, `entry = null`, `eligibility_status = BLOCKED / [EXPIRED]`;
- `provenance.market_state_fingerprint == market_state.fingerprint`.

I did not require a signal. As a **positive control** that the gate can actually emit one,
my deterministic fixture run reaches `AUTHORITATIVE → MAY_EVALUATE → OPPORTUNITY`.

## A4 — `IDENTITY_FIRST_ZERO_READ_GUARD = ENFORCED` (critical gate)

Independently instrumented candle feed, server-clock provider and spread provider. For
every bad identity: **zero candle reads, zero spread reads, zero server-time reads, no
strategy evaluation.**

| Probe | Status | candles | clock | spread | downstream |
|---|---|---|---|---|---|
| `EURUSD+` | `IDENTITY_BLOCKED` | 0 | 0 | 0 | BLOCKED / NOT_EVALUATED / BLOCKED / BLOCKED |
| `EURUSD-VIP` | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| `eurusd` | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| wrong server | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| unknown registry version | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| metadata unavailable | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| metadata mismatch | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |
| venue not configured | `IDENTITY_BLOCKED` | 0 | 0 | 0 | ″ |

The design reason is structural, not incidental: `server_clock_provider` and
`spread_provider` are **lazy callables invoked only after `resolve_identity()` succeeds**,
and in the entrypoint `MetaTrader5.symbol_info()` is itself guarded —
`symbol_info(...) if canonical_id_for(symbol, venue_id) else None`. AST-verified: exactly
one `scanner.scan_symbol` call site in the module, preceded by the
`if not gate.authoritative` guard (line 216 guards line 219).

## A5 — `GBPUSD_STATUS` / `USDJPY_STATUS` = `CANONICAL_IDENTITY_NOT_CONFIGURED`

Confirmed in both the live run and my probes, with `canonical_instrument_id: null`,
`broker_metadata: null`, `market_data_readable: false`, and **no broker read of any kind**
— not even `symbol_info`. Downstream: `BLOCKED / NOT_EVALUATED / BLOCKED / BLOCKED`.

**No raw-symbol fallback exists:** one guarded scanner entry point, and the entrypoint's
single `symbol_info` call is conditioned on the canonical lookup. `canonical_id_for` is an
exact `base+quote` match against the registry — `GBPUSD`, `USDJPY`, `AUDUSD`, `XAUUSD` all
return `None`. As specified, this is correct V1 behaviour and **not** a WP-7B defect.

## A6 — `SAME_DATA_REUSE = SINGLE_READ` · `MARKETSTATE_FINGERPRINT_PARITY = ENFORCED`

Claude's claim holds, and it is enforced in code rather than merely asserted:

- `MemoFetch` read-through cache → each broker window fetched **exactly once** (2 windows, 2 unique fetches, no duplicates) even though MarketState is built twice; clock and spread providers each invoked exactly once. It also returns a copy, so a caller cannot poison the cache.
- The gated MarketState fingerprint **equals** the scanner's.
- **Identical outcome with and without the gate:** running the unchanged scanner directly on the same fixture yields the same `status`, the same `reason_codes`, the same MarketState fingerprint and a byte-equal `summary()`. The gate changes nothing on the pass path.
- **Divergence is fatal, not ignored.** I monkeypatched the scanner to return a different MarketState fingerprint: the result becomes `MARKETSTATE_FINGERPRINT_DIVERGENCE` with `scan = None` and `opportunity = NOT_EVALUATED`.

No mismatch found; no duplicate broker fetch caused by the gate.

## A7 — `METADATA_AUTHORITY_MODEL = SINGLE_METADATA_AUTHORITY`

The old `check_broker_spec` (digits/point only) is **gone from the Opportunity path** —
absent from both the entrypoint and the gated module. It survives only as a pure helper in
`src/fx_opportunity/instruments.py` and one unrelated caller,
`scripts/capture_vt_spread_evidence.py` (an evidence-capture script, not the live
Opportunity path). It is therefore **not independently authoritative** over Opportunity,
and there is no competing parallel metadata authority.

Coverage is a strict superset of the old safety surface:

```
old: digits, point
new: digits, point, tick_size, contract_size, volume_min, volume_max, volume_step,
     tick_value, currency_base, currency_profit, symbol, server
     + finiteness / non-bool / presence validation
```

Verified behaviourally: both old-style failures (`digits` wrong, `point` wrong) still
block, now with zero data read.

## A8 — `GBPUSD_CLOCK_ONLY_DISTINCTION = DOCUMENTED_AND_CORRECT`

An important nuance, confirmed in the live artifact. The EURUSD server clock record is:

```json
{"scope": "SERVER_SHARED", "source": "SERVER_CONSENSUS", "server": "VTMarkets-Demo",
 "evidence_symbols": ["EURUSD", "GBPUSD"], "utc_offset_hours": 3, ...}
```

GBPUSD bars **were** read as shared-server clock evidence for the EURUSD evaluation — yet
in the very same run GBPUSD has `canonical_instrument_id: null`,
`status = CANONICAL_IDENTITY_NOT_CONFIGURED`, `opportunity = NOT_EVALUATED`,
`marketstate_authority = BLOCKED`, no `scan` key and `broker_metadata: null`.

**Clock-only reads are not a GBPUSD Opportunity evaluation.** The distinction is clean:
time-authority evidence is a property of the *server*, whereas Opportunity evaluation is a
property of a *canonically identified instrument*. GBPUSD contributes to the former and is
excluded from the latter.

## A9 — `TRADE_MODE_0_CLASSIFICATION = INFORMATIONAL_FOR_READ_ONLY / EXECUTION_GATE_RELEVANT_LATER`

`trade_mode = 0` (`SYMBOL_TRADE_MODE_DISABLED`) is present in the live metadata and is
**recorded** (it is inside the hashed metadata fingerprint — `trade_mode=0` and `=4` hash
differently) but does **not** block read-only MarketState/Opportunity analysis: identity
`RESOLVED`, Opportunity evaluated. It grants nothing: `execution_authority = NONE`,
`trade_ticket = NOT_CREATED`. Execution was not investigated further, per scope.

## A10 — `PROVENANCE = COMPLETE`

Every required element is present in the result:

```
canonical_instrument_id  FX.EURUSD              registry_version  instruments-v1.0.0
venue_id  VT_MARKETS_MT5                        server  VTMarkets-Demo
venue_symbol  EURUSD    (+ observed_server / observed_symbol / mismatched_fields)
identity fingerprint     6a781d60…             metadata fingerprint  1455483d…
time authority           server_clock[] with broker, scope SERVER_SHARED,
                         source SERVER_CONSENSUS, utc_offset_hours, effective_from/until
market-data fingerprints market_state / reference / post_session / instrument
application lineage      5fc8d1fb… (git commit)  + pilot_config_fingerprint, pilot_id
```

**No credential data.** I scanned the full live artifact and the runtime summary for
`login`, `password`, `investor`, `account_number`, `credential`, `token`, `terminal_path`,
`api_key` — none present. Only `account_environment: DEMO` is recorded. The snapshot's
`source` field is deliberately stripped from the emitted metadata.

## A11 — `FOREIGN_CWD_STARTUP = SAFE`

The entrypoint anchors repo root from `__file__` at line 37 (`os.chdir(_REPO)`), which
precedes every platform import (first at line 57) — AST-verified. With the MetaTrader5
package importable, I launched `scripts/run_fx_opportunity_once.py --help` from an
unrelated cwd: **exit 0**, arguments parsed. Registry selection is not cwd-dependent:
resolving from a tmp dir and from `/` yields the same `FX.EURUSD`, the same registry
version and the same identity fingerprint. The live evidence itself records the run as
*"launched from a foreign cwd; candidate store outside the repo"*.

## A12 — Execution containment

```
BROKER_ORDER_CHECK_REACHABILITY       = NOT_REACHABLE   (calls = 0)
BROKER_ORDER_SEND_REACHABILITY        = NOT_REACHABLE   (calls = 0)
POSITIONS_GET_REACHABILITY            = NOT_REACHABLE   (calls = 0)
OTHER_EXECUTION_MUTATION_REACHABILITY = NOT_REACHABLE   (calls = 0)
```

- **Static (AST):** no executable reference in `fx_gated_scan.py` to `order_send`, `order_check`, `positions_get`, `positions_total`, `orders_get`, `orders_total`, `order_calc_margin`, `order_calc_profit`, `initialize`, `login`, `shutdown`.
- **Runtime:** all mutation APIs replaced with recording stubs, then seven paths exercised (resolved, drift, wrong server, metadata absent, metadata mismatch, GBPUSD, USDJPY) → **`calls == []`**.
- **The live run's own counters agree**, which is the strongest available evidence: `order_check 0, order_send 0, orders_get 0, orders_total 0, positions_get 0, positions_total 0, trade_buy/sell/close/modify/cancel 0`, with `proposal_authority = NONE` and `trade_ticket = NOT_CREATED`.
- **PREPARED/TradeTicket unreachable from the real strategy:** `resolve_strategy_binding("ST_ASIAN_SWEEP_5R_V1").proposal_authority is False`, and the registry is untouched, so the gated result is `NO_PROPOSAL_AUTHORITY / NOT_CREATED` even on the fully authoritative path.
- All five execution packages remain absent.

## A13 — Frozen contracts

```
FROZEN_TRADETICKET_IDENTITY = BYTE_IDENTICAL  (src/trade_ticket tree cd405372… == 1564769a)
FROZEN_REGISTRY_IDENTITY    = BYTE_IDENTICAL  (instruments-v1.0.0.yaml unchanged)
WP7A_CODE_IDENTITY          = BYTE_IDENTICAL  (identity.py and gates.py unchanged)
```

## A14 — Tests

```
FOCUSED_TESTS (WP-7B)   = 24 passed, 1 failed  (environment — see below)
WP-7A registry tests    = 46 passed
TradeTicket tests       = 112 passed
Opportunity/Proposal/FX = 449 passed, 2 failed (the same two)
INDEPENDENT_TESTS       = 36 passed (auditor-written, A3–A13)
REGRESSION_TESTS (full) = 842 passed, 4 skipped, 2 failed
```

Both failures classified, nothing hidden:

| Failure | Class | Evidence |
|---|---|---|
| `test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection` (`No module named 'api.app'`) | **pre-existing baseline** | reproduced at every prior audited commit |
| `test_fx_identity_gated_scan.py::test_live_runner_starts_safely_from_a_foreign_cwd` (`No module named 'MetaTrader5'`) | **environment** | see below |

**No candidate regression.** The suite grew 818 → 842 (+24), exactly the new focused tests.

### Diagnosis of the second failure (it is *not* a cwd defect)

The test's name implies a cwd problem; the actual cause is not. I ran the runner from the
**repository root** with no `PYTHONPATH` and it fails **identically**:

```
from repo root   : ModuleNotFoundError: No module named 'MetaTrader5'
from foreign cwd : ModuleNotFoundError: No module named 'MetaTrader5'
with MT5 importable, foreign cwd : exit 0, --help parsed
```

cwd is therefore **not** the differentiator. The cause is that the script inserts only
`_REPO/src` on `sys.path`, while the repo's fallback `MetaTrader5.py` stub sits at the
repo **root** — so on any host without the real MetaTrader5 package installed the import
fails regardless of cwd. On the Windows MT5 host that produced the live evidence
(explicitly "launched from a foreign cwd") it passes. The property the test claims to
check does hold — my A11 probe verifies it directly.

---

## Findings

```
BLOCKING_FINDINGS = NONE

NONBLOCKING_FINDINGS = 3
```

1. **Environment-dependent test.** `test_live_runner_starts_safely_from_a_foreign_cwd` fails on any host without the MetaTrader5 package, for a reason unrelated to the cwd property it names. It makes an unreliable CI gate. Suggest `pytest.importorskip("MetaTrader5")`, or adding `_REPO` to `sys.path` in the entrypoint so the committed stub is reachable — which would also make the runner's fail-closed behaviour uniform across hosts.
2. **`check_broker_spec` still called by `scripts/capture_vt_spread_evidence.py`.** Off the Opportunity path and non-authoritative, so not a competing authority today; worth migrating to the canonical metadata check so only one comparison survives long-term.
3. **Evidence artifact filename/key drift.** The status doc refers to the artifact as `AG_WP7B_LIVE_IDENTITY_GATED_RUN_…`, but the committed file is `WP7B_LIVE_IDENTITY_GATED_RUN_…` (no `AG_` prefix). Cosmetic, but it briefly obstructs automated evidence lookup.

Carried forward unchanged from earlier audits: no `verify_envelope()` helper; registry
content fingerprint covers parsed YAML rather than raw bytes; the platform-wide
cwd-relative config-path pattern (`fx_opportunity.instruments` et al.) remains a separate
future mission.

---

## Verdict

```
CLASSIFICATION = WP7B_IDENTITY_GATED_LIVE_OPPORTUNITY_AUDIT_PASS_WITH_NONBLOCKING_FINDINGS

NEXT_STEP = CANONICAL_INSTRUMENT_REGISTRY_V1_1_ADD_GBPUSD_WITH_READ_ONLY_VT_EVIDENCE
```

The expansion was **not** started during this audit. When it is, the strongest evidence
from this run is that the V1 registry scope is genuinely load-bearing: GBPUSD is already
being read as server-clock evidence while remaining completely unevaluated as an
instrument — so adding it must go through the same read-only evidence capture and pinned
new registry version (`instruments-v1.1.0`, never an in-place edit), not through a
convenience alias.

**Constraints honoured.** Candidate not modified, not merged, not cherry-picked; registry
not expanded; no broker contact (committed evidence and deterministic fixtures only);
execution not investigated beyond containment; audit worktree verified clean and removed.
This document authorizes nothing.
