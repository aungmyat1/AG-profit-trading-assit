---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# TICKET_STORE_V1 — append-only ticket evaluation store (2026-10-08)

Storage only. No strategy, decision, actionability, delivery or authority logic changed.
A store write failure is reported on the evaluation result (`ticket_store_error`) and never
changes the decision.

## Audit of existing stores

| Store | Path | Shape | Role after V1 |
|---|---|---|---|
| Scan records | `journal/ticket_delivery/manual/scan_records/<day>.jsonl` | append-only, one per strategy×symbol×session run | unchanged; migrated as LEGACY |
| Manual tickets | `journal/ticket_delivery/manual/tickets/<day>.jsonl` | append-only, content_hash-deduped | unchanged; migrated as LEGACY |
| FX ticket archive | `journal/ticket_delivery/archive/fx_ticket_archive/**/<day>.json` | one JSON per strategy/symbol/cycle/day | unchanged; migrated as LEGACY |
| Canonical archive | `<archive_root>/ticket_delivery/daily_evaluator/<day>_<sym>_<session>.jsonl` | append-only AG_CANONICAL_TICKET_V1 | unchanged; V1 writes alongside it |
| Delivery store | `delivery_records.json` (`ticket_delivery/delivery_store.py`) | current-state, overwritten per transition | unchanged; not a ticket record |
| Delivery attempt journal | `ticket_delivery/attempt_journal.py` | append-only audit | unchanged |
| Owner decisions | `journal/ticket_delivery/manual/owner_decisions.jsonl` | append-only, one per ticket | unchanged; linked via `owner_decision_ref` |
| VIRTUAL_FORWARD outcomes | `journal/ticket_delivery/manual/outcomes/<day>.jsonl` | append-only | unchanged; migrated to OUTCOME (LEGACY) |
| JsonKeyValueStore | `src/runtime_state/store.py` | keyed JSON, full rewrite (atomic replace) | not a ticket store; unchanged |

None of these holds one record per evaluation for every terminal state with levels, spec and
code identity, and input-bar hashes. Several overwrite in place.

## Schema

`<store>/evaluations/<YYYY-MM-DD>.jsonl` (day = `evaluated_at_utc`), one
`TICKET_STORE_V1_EVALUATION` per strategy×symbol×session evaluation, for every terminal state:

`schema, evaluation_id, ticket_id, strategy (id@version), spec_sha256, code_sha, source
(LIVE|REPLAY|LEGACY), symbol, session, evaluated_at_utc, signal_close_utc, state,
block_reasons[], warnings[], direction, entry, sl, tp1, tp2, spread_at_signal,
spread_measured_at_utc, input_bar_hashes, delivery_status, owner_decision_ref, provenance,
record_sha256`

`<store>/outcomes/<YYYY-MM-DD>.jsonl`: `TICKET_STORE_V1_OUTCOME` records, keyed by `ticket_id`:
`schema, outcome_id, ticket_id, source, outcome_kind, recorded_at_utc, result, payload,
provenance, record_sha256`.

Rules:
- **Fields:** every field is always present; a fact that wasn't measured is `null`.
- **Identity:** `evaluation_id = sha256(strategy, symbol, session, evaluated_at_utc, source)`.
  Re-writing the identical record is a no-op, which makes restarts and retries idempotent.
  A different record under the same identity raises `TicketStoreConflict`.
- **Corruption:** a truncated or unparseable line raises `TicketStoreCorrupt` and is never repaired.
- **Immutability:** tickets are never mutated. Outcomes and owner decisions are separate records.
- **`spread_at_signal`:** the live spread as measured at evaluation time;
  `spread_measured_at_utc` says when it was taken.
- **`spec_sha256`:** hash of the registered contract whose `version` equals the ticket's
  version; `null` when no contract matches.
- **`code_sha`:** `v1_tickets.code_identity`, or `null` when unknown.
- **Source:** defaults to `REPLAY`. Only `scripts/host/live_eval_smoke.py`'s real MT5 run passes `LIVE`.
- **Index:** `<store>/index.sqlite` is rebuildable and never authoritative.
  `python scripts/ticket_store_reindex.py --store <store> [--check-only]` exits 1 unless the
  JSONL count equals the index count and the ids are identical.

## Wiring

`v1_tickets.daily_evaluator._finalize` (the canonical-ticket path) writes one EVALUATION
after the canonical archive append, to `<archive_root>/ticket_store`. On the host run that
is `journal/ticket_store`.

## Migration (`scripts/ticket_store_migrate.py --journal <j> --store <s>`)

Read-only on the journal. The views of one evaluation are grouped by (strategy@version,
symbol, session, evaluated_at) into ONE `LEGACY` record. Field precedence is
canonical > manual > scan > fx. Fields no view carries stay null. `spec_sha256` and
`input_bar_hashes` are always null for LEGACY. Symbols are not normalized. Each source line
is listed in `provenance.legacy_sources`.

| Journal | Read | EVALUATION written | Re-run written | Outcomes | Index check |
|---|---|---|---|---|---|
| Committed evidence `docs/status/evidence/pass_b_replay_b92f529_0740Z/journal` | manual 8, scan 12, fx 8 | **12** (8 ST_ASIAN_SWEEP_5R_V1 merged from 3 views each; 4 SESSION_TRADE_V1 scan-only) | 0 | 0 | PASS 12 = 12 |
| Windows host `journal/` | NOT_EVALUATED (not in this checkout) | — | — | — | — |

## Tests (2026-10-08, Linux, Python 3)

- `python -m pytest tests/test_ticket_store_v1.py -q`: **13 passed**
- `python -m pytest tests -q`: **1157 passed, 2 skipped**

## Next

On the Windows host:

```
python scripts/ticket_store_migrate.py --journal journal --store journal/ticket_store
python scripts/ticket_store_reindex.py --store journal/ticket_store --check-only
```
