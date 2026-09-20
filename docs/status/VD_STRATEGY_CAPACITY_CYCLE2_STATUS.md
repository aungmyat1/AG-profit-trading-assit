# Strategy Capacity VD — Cycle 2 status

Date: 2026-09-20. Classification: `VD_CYCLE2_PARTIAL`.
Mode: `STRATEGY_CAPACITY_VALIDATION`. Strategy:
`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1.

## C2A — canonical authority

Capacity mode rejects a caller decision map or function. It loads the fixed SSC
contract, validates the approved H1 metadata manifest against its dataset file,
and calls `session_sweep_continuation.canonical_consumer.run_canonical_shadow_cycle`
with TD-8E closed candles. That consumer invokes the unchanged SSC replay. The
runner admits only setups whose M15 entry closes at the current virtual T.
Canonical unavailability produces a `CanonicalUnavailable` ledger event and no
order. A canonical decision records strategy ID/version, contract hash, replay
event ID, evaluation time, bound series identities, and decision hash.

This is an engineering integration proof with fixture data and a patched
canonical entrypoint. A real admitted development replay has not yet been run.
The loaded H1 store's content is separately identified by TD-8E; the manifest
validation binds the approved file bytes and dataset ID, but this runner does
not independently reparse that file to compare every loaded candle.

## C2B — later-event lifecycle

`VirtualExchange.advance()` consumes one closed M1 observation per call using
its existing first-eligible-open and SL/TP ambiguity rules. The runner retains
orders across iterations, prevents same-event fills, applies later fills and
terminal outcomes to the account and ledger, and marks pending/open positions
explicitly at end of data. Maximum concurrent virtual positions remains the
existing engineering account limit of one; it is not a frozen capacity risk
profile. Existing VirtualExchange does not define BE or partial-position
transitions, so neither was invented here. OHLC ambiguity remains unresolved.

## C2C — checkpoint

The JSON-serializable checkpoint records clock, replay cursor, feed sequence,
pending orders, account snapshot, open/closed position IDs, strategy identity,
processed decisions, and ledger root. Restoration recreates the state by
deterministically replaying the immutable admitted prefix and comparing every
checkpoint field. This is suitable for engineering restart parity. It is not
yet a sealed-campaign persistence format: replaying protected data would require
separate access governance.

## Safety and remaining gates

No campaign was run, no protected/holdout/OOS data was accessed, and no MT5
order or margin path was used. Strategy semantics, registration, execution
authorization, and parameters were unchanged. The next bounded engineering gate is
the frozen `VD_CAPACITY_RISK_V1` contract in `src/svos/capacity_risk_contract.py`,
which records the repo-authority virtual-capacity limits and fails closed on any
broker or economic value that is not explicitly authorized by the project. The
capacity contract intentionally defers leverage, margin, commission, slippage,
latency, and executable-spread authority as `DEFERRED_EXECUTION_PARITY`. Simulator
readiness still needs the friction/metric/qualification contracts and manifest,
plus engineering parity proofs on permitted development evidence. BE and partial
behavior require an explicit virtual lifecycle contract before inclusion.
