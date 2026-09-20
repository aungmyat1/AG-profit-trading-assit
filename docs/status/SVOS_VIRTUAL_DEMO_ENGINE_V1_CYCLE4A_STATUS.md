# SVOS Virtual Demo Engine V1 — Cycle 4A position and account core

Date: 2026-09-20. Classification: **VD_ACCOUNT_CORE_READY**.

## Baseline and scope

HEAD before implementation: `57fccf8c2368a62ca7e3e0f00afdc2a7a500d82e` (Cycle 3C).
The unrelated untracked `src/proposal_envelope/identity_audit.py` was preserved and
not staged. MI/TD-8E/SSC semantics and prior exchange/bridge code remain unchanged.

## Position and account model

`VirtualPosition` preserves strategy identity/version, symbol, side, dataset/decision/
proposal/order/fill lineage, research reference price, executable entry price,
stop/target geometry, normalized quantity basis, state, transitions, and normalized
mechanical price P&L. States are `OPEN`, `PARTIAL` (reserved for a future canonical
partial event), `CLOSED`, and `UNRESOLVED`. A valid fill creates exactly one OPEN
position. An adverse/favorable exit closes it once. `AMBIGUOUS_SEQUENCE` leaves it open
and records no fabricated close. Partial/BE/runner transitions are not claimed as
fully implemented because exchange records do not carry canonical partial quantities
or BE modification events; the representation preserves the future state.

`VirtualAccount` is an idempotent reducer with an engineering starting balance,
open/closed registries, configurable max-open-position count, and immutable hash-linked
snapshot records. Quantity is always `ENGINEERING_NORMALIZED_1`; broker volume authority
is false. Mechanical price delta is recorded in normalized units only. Economic status
is `NOT_MODELED`; spread, commission, slippage, latency, broker volume, margin, and
currency conversion are not inferred.

## Proofs and safety

Tests cover no-fill/no-position, one-fill/one-position, duplicate and conflicting fills,
single terminal close and duplicate exit, ambiguity preservation, mismatched or missing
lineage, exit-before-fill, deterministic snapshots, and repeated account runs. Cycle 3B
exit records carry an explicit stop/target mechanical price when unambiguous; ambiguous
exits carry no price and cannot close the position. The module has no MT5 or live fallback.

## Verification

- `python -m pytest -q tests/test_svos_virtual_account_cycle4a.py tests/test_svos_ssc_bridge_cycle3c.py tests/test_svos_virtual_exchange_cycle3b.py` → **19 passed**.
- Full requested regression across Cycle 4A, 3C, 3B, 2, SVOS, SSC, TD-8E, and MI tests → **113 passed**.

`engineering_ready = true`; `integration_ready = true`; `economic_qualification_ready = false`.
No sizing, balance/equity economics, margin, currency conversion, spread calibration,
commission, slippage, latency calibration, sealed data, Demo/Live order, optimization,
or execution-authority change occurred.
