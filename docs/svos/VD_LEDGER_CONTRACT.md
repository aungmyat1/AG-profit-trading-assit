# VD V1 immutable ledger contract

The ledger is append-only, schema-versioned, and content addressed. Canonical serialization uses UTF-8 JSON with sorted keys, normalized UTC ISO-8601 timestamps, decimal strings for prices/quantities/money, explicit nulls, and no NaN/Infinity. `id = SHA256(namespace | schema_version | canonical immutable payload)`. The record envelope carries `record_id`, `record_type`, `campaign_id`, `event_ordinal`, `created_at_virtual`, `prior_record_hash`, `payload_hash`, and source parent IDs. Wall-clock telemetry is outside the semantic hash. Duplicate ID with different payload fails closed. Corrections append a superseding record and retain the original.

| Record | Minimum immutable fields and parents |
|---|---|
| `StrategyDecision` | Dataset/version/hash, TD-8E event/provenance ID, MI snapshot ID/hash, SSC ID/version/config hash, `run_replay` input fingerprint, decision time/state/reason, canonical result hash. |
| `TradeProposal` | Decision ID, proposed side/entry/stop/targets/risk as emitted or adapted without semantic edits, proposal time, adapter version, acceptance state. |
| `VirtualOrder` | Proposal ID, account/execution profile hashes, side/type/quantity, submission and eligibility time, state transitions and rejection reason. |
| `VirtualFill` | Order ID, observation ID/quality, timestamp, executable quote, quantity, spread/slippage/fee components, ambiguity label and model versions. |
| `VirtualPosition` | Parent fill IDs, position transitions, quantity/cost basis/stops, account snapshot IDs. |
| `VirtualOutcome` | Position ID, terminal fills or unresolved reason, gross/net cash and R when computable, quality flags, terminal account snapshot. |

Lineage is mandatory: `dataset → event → MI → SSC decision → proposal → order → fill → position → outcome`. A `NO_TRADE` decision ends at the decision record; a rejected order ends at its rejection record; an open position at end of data gets an unresolved outcome. All records retain dataset and campaign identities through ancestry. The ledger root is a hash chain over ordered record hashes and is verified on restart/export. The source manifest and exact MI/TD-8E/SSC release hashes are embedded in the campaign manifest, never inferred from current HEAD after a run.
