# SVOS Virtual Demo Engine V1 — Cycle 4B immutable ledger and replay parity

Date: 2026-09-20. Classification: **VD_LEDGER_PARITY_READY**.

HEAD before: `eea281135d9780d0f41f55cd6f9290f7bb4a1ab7`. The unrelated untracked
`src/proposal_envelope/identity_audit.py` and `tests/test_proposal_identity_layering.py`
were preserved and not staged.

`VirtualLedgerEvent` uses schema `VD_LEDGER_V1`, deterministic event IDs and payload
hashes, explicit sequence, virtual time, causal parents, dataset/source event identity,
strategy/version and proposal/order/fill/position/snapshot references, and
`economic_authority=false`. Record hashes bind the previous hash and sequence. Canonical
JSON excludes runtime metadata. Events are append-only: an equivalent source event is
idempotent, while a conflicting duplicate source event is rejected. Parent IDs must
already exist; verification rejects sequence, payload, parent, or chain mismatches.

Exchange fill/outcome evidence is serialized with reference and executable prices,
observation kind, stop/target metadata, and strategy identity. Replay skips decision
logic and reconstitutes only recorded fill/outcome records into `VirtualAccount`.
Equivalent fixture sequences produce identical event IDs, order, snapshots, and terminal
ledger hash. A simple fill/close reconstructs the closed position and normalized price
P&L. An ambiguous outcome remains an open position after replay. Duplicate evidence does
not create duplicate positions or closes. Partial/BE/runner accounting remains deferred:
Cycle 4A preserves the state representation, but Cycle 3B does not emit canonical
partial quantity or stop-modification events.

The account remains engineering-only: quantity is `ENGINEERING_NORMALIZED_1`, economic
P&L is `NOT_MODELED`, and spread, commission, slippage, latency, broker volume, margin,
and conversion remain unresolved. The ledger persists evidence but grants no economic,
strategy, or execution authority.

Verification: `python -m pytest -q tests/test_svos_virtual_ledger_cycle4b.py tests/test_svos_virtual_account_cycle4a.py` → **9 passed**. Full requested Cycle 4B/4A/3C/3B/2/SVOS/SSC/TD-8E/MI regression → **117 passed**. No MT5/live fallback, protected data, campaign, or order was used.

`engineering_ready = true`; `integration_ready = true`; `ledger_ready = true`;
`economic_qualification_ready = false`.
