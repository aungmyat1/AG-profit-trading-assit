---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP C14 DEMO execution boundary hardening (2026-10-11)

Refusal-side hardening of the future automatic DEMO execution boundary authorized in
principle by C14 (`docs/governance/AGP_C14_AUTO_DEMO_OWNER_DECISION_2026-10-11.md`).
Four owner requirements are now enforced by code that fails closed, plus a test suite
that runs offline with no broker and no MT5 terminal.

No order was checked, sent, modified or cancelled. No account was read. Nothing on the
host changed. `ORDER_API_CALLS = 0`, `BROKER_MUTATION_COUNT = 0`, `broker_mutation: NONE`.
The committed S1 scope still reads `enabled: false`, D6 READY is still OFF, and every
strategy binding still reads `demo_authorized=false`. This is unit-tested offline
evidence, not live verification: no part of it was exercised against a broker.

## What the four requirements now mean in code

| # | Owner requirement | Where it is enforced | Test |
|---|---|---|---|
| 1 | Every adapter call refuses unless an execution-authority object is passed and re-validated inside the adapter | `src/demo_execution/guarded_adapter.py` (`GuardedCanonicalAdapter`), validators in `src/demo_execution/authority.py`, Protocol in `src/demo_execution/broker_adapter.py` | `tests/test_demo_execution_authority_boundary.py` |
| 2 | Duplicate-ticket ledger check before `order_check`, not only before send | `authorize_order_check` inspects `ExecutionLedger` before the live account read and before any authorization is issued | `test_a_duplicate_ticket_is_refused_before_order_check_not_only_before_send` |
| 3 | Reserved S1 magic must not equal any magic in use on the host | `src/demo_execution/host_magics.py` + `config/demo_execution_host_magics.yaml`, checked inside `load_scope_policy` (`src/demo_execution/scope.py`) | `tests/test_demo_execution_host_magics.py` |
| 4 | Every state transition appends an evidence record; unknown outcome halts and reconciles, never resubmits | `src/demo_execution/lifecycle.py` (append-only `DEMO_LIFECYCLE_EVIDENCE`), guard transitions, `ExecutionLedger.record_unknown` | `test_every_transition_appends_one_evidence_record_with_ids_and_utc_timestamps`, `test_an_unknown_send_outcome_halts_and_is_never_resubmitted` |

## Requirement 1 — the authority object is re-validated inside the adapter

`CanonicalBrokerAdapter` is a Protocol whose every operation takes `authority`, and whose
two broker-facing operations (`order_check`, `order_send`) additionally take the
single-use `authorization` the guard issued. There is no callable implementation in this
repository and no broker API call site anywhere in `src/demo_execution/`; the last test in
`tests/test_demo_execution_authority_boundary.py` re-asserts that statically by walking the
AST of every module in the package for forbidden call names and for any `MetaTrader5`
import. `tests/test_manual_ticket_report_and_boundary.py` keeps the repo-wide
`.order_send(` / `.order_check(` ban green.

Every guarded call re-runs, in this order, and refuses on the first missing fact:

1. **Authority shape** — a dataclass, not a mapping or a string; ticket id, strategy,
   version, symbol, session, branch, direction, logic identity and magic present and of
   the right type; all three evidence refs present with SHA-256 ids and UTC timestamps
   (`EXECUTION_AUTHORITY_MISSING`, `EXECUTION_AUTHORITY_INVALID`).
2. **Issued-at** — the authority must not predate or postdate its own use
   (`AUTHORITY_NOT_YET_VALID`, `AUTHORITY_EXPIRED`, `AUTHORITY_TIMESTAMP_INVALID`).
3. **Committed scope, re-loaded from disk on every call** — schema `AGP_C14_DEMO_SCOPE_V1`,
   `enabled`, strategy@version registered and `LOGIC_VERIFIED`, symbol/session/branch/
   direction/magic, broker server, account login suffix, host magic registry
   (`EXECUTION_DISABLED`, `EXECUTION_SCOPE_INVALID`, `AUTHORITY_SCOPE_MISMATCH`,
   `HOST_MAGIC_REGISTRY_UNAVAILABLE`, `STRATEGY_MAGIC_COLLIDES_WITH_HOST`).
4. **Ticket binding** — the ticket presented must be the ticket the authority names, field
   by field, and inside its window (`AUTHORITY_TICKET_MISMATCH`, `TICKET_EXPIRED`).
5. **Lifecycle trail** — one authority id is single use; an existing trail means the ticket
   was already authorized, halted or reconciled and is never re-authorized
   (`AUTHORITY_REUSED`, `LIFECYCLE_ORDER_INVALID`, `HALT_UNKNOWN_RESULT`,
   `LIFECYCLE_ALREADY_RECONCILED`, `LIFECYCLE_EVIDENCE_CONFLICT`).
6. **Duplicate-ticket ledger** — `ExecutionLedger.inspect` before the account is read
   (`DUPLICATE_TICKET_ID`, `HALT_UNCERTAIN_SEND`). A refused ticket never reaches the live
   account read or the gate evaluation.
7. **Live DEMO account identity, read inside the call** — see below.
8. **READY / risk / freshness evidence ids** — recomputed by the guard from the facts it was
   actually handed and compared with the ids the authority claims, then bound to the
   `AUTHORIZED` row for every later phase (`READY_EVIDENCE_ID_MISMATCH`,
   `RISK_EVIDENCE_ID_MISMATCH`, `FRESHNESS_EVIDENCE_ID_MISMATCH`, `RISK_EVIDENCE_STALE`,
   `FRESHNESS_EVIDENCE_TIMESTAMP_IN_FUTURE`). A caller's `ADMITTED_PRE_SEND` is never taken
   on trust: the guard runs `evaluate_pre_send_gates` itself.
9. **Standing authorization, re-read from the authorization file** — emergency stop,
   revocation, scope, path and decision id (`EMERGENCY_STOP_ENGAGED`, `AUTHORIZATION_REVOKED`,
   `AUTHORIZATION_SCOPE_MISMATCH`, `AUTHORIZATION_PATH_MISMATCH`,
   `AUTHORIZATION_DECISION_ID_MISMATCH`).
10. **Per-order owner confirmation** — required while the committed scope requires it, and
    `per_order_confirm_required` defaults to required when the key is absent or malformed
    (`OWNER_CONFIRM_REQUIRED`, `OWNER_CONFIRM_MISSING`, `OWNER_CONFIRM_ID_MISMATCH`,
    `OWNER_CONFIRM_BINDING_MISMATCH`, `OWNER_CONFIRM_REUSED`, `OWNER_CONFIRM_NOT_CONSUMED`).
    Binding, window, duplication and reuse are judged by the sanctioned validator
    `demo_execution.confirmation.check_and_consume_owner_confirmation`, called read-only; the
    guard restates none of those rules. What the guard adds is the authority's own claim — the
    confirmation id the authority names must be the confirmation the ledger holds for this
    ticket — and the send-time rule that it was consumed exactly once, verified from the
    `DEMO_OWNER_ORDER_CONFIRM_USED` rows with their store seal intact.

    Order matters here: the confirmation claim is validated **before** the pre-send gates run,
    because those gates are what consume the confirmation. A call that is going to be refused
    never spends the owner's single-use confirmation, and reports
    `gates: NOT_EVALUATED_OWNER_CONFIRMATION_REFUSED` instead of a gate result. The guard hands
    its own `TicketStore` to `evaluate_pre_send_gates`, so the confirmation is consumed by its
    sanctioned writer and the gates' duplicate-ledger check reads the same append-only store the
    guard writes evidence to.

### The DEMO account is read live, immediately before `order_check`

`authorize_order_check` calls the injected `live_account_reader` itself and stamps the read
with its own `now_utc`; the result is never cached, never accepted from the caller, and is
written into the `AUTHORIZED` evidence row. A second live read happens at
`record_order_checked` and a third at `authorize_order_send`. Classification is strict:
`trade_mode` is normalized from the MT5 integer (`0` DEMO, `1` CONTEST, `2` REAL) or string,
and only DEMO passes; an unclassifiable or absent mode is `ACCOUNT_MODE_UNAVAILABLE`, a
non-DEMO mode is `ACCOUNT_NOT_DEMO`. Login suffix and server must equal the pinned scope
values, a read older than 30 s is `ACCOUNT_READ_STALE`, a read stamped in the future is
`ACCOUNT_IDENTITY_TIMESTAMP_INVALID`, and a reader that raises fails closed to
`ACCOUNT_IDENTITY_UNAVAILABLE`. Only a four-character `login_suffix` is ever accepted or
recorded; a full account login is refused and never appears in evidence.

## Requirement 2 — duplicate ticket before `order_check`

`authorize_order_check` inspects the claim ledger before the live account read. A ticket
that already carries a `DEMO_EXECUTION_SENDING` claim is refused with the ledger's own
reason (`HALT_UNCERTAIN_SEND`) and no `AUTHORIZED` evidence row is written. A reconciled
ticket is refused with `DUPLICATE_TICKET_ID` plus `LIFECYCLE_ALREADY_RECONCILED` and
`LIFECYCLE_ORDER_INVALID`, and the guard reports `resubmission: NEVER`.

## Requirement 3 — reserved magic versus the magics in use on the host

`config/demo_execution_host_magics.yaml` (schema `AGP_C14_HOST_MAGIC_REGISTRY_V1`) records
the magics in use on the VT Markets DEMO host with per-magic provenance:

| Magic | In use by |
|---|---|
| 0 | unattributed manual / local MT5 API orders (reason `EXPERT`, source `127.0.0.1`) |
| 102233 | `ContinuationBreakout_EA` (the only EA loaded on the host at inventory time) |
| 18152023 | `asian_session_ea` |
| 550055 | `SMC_Sniper_EA` |
| 20260713 | `SMC_LSS_v1_EA` |
| 1120250714 | `MT5_EA_1BullBear_ICT_SMC` |

The reserved S1 magic is not a literal in the check: `load_scope_policy` resolves it from
the registered `ST_ASIAN_SWEEP_5R_V1@1.1.2` contract (`777001`) and refuses to load the
scope at all if it collides with any registry entry, if the registry is missing, unreadable,
malformed, duplicated, unstamped, unattributed, or omits magic `0`. `777001` collides with
none of the six. `tests/test_demo_execution_host_magics.py` pins the six-magic list
literally and asserts the reserved magic differs from each of them, so a future contract
change that collides fails closed instead of sharing a magic with another order source.
`.ex5` binaries on the host were inventoried, not decompiled; their magics are recorded as
`UNKNOWN_BINARY` in the C11 inventory and are not claimed here.

## Requirement 4 — evidence for every transition, halt on unknown

`src/demo_execution/lifecycle.py` appends one `DEMO_LIFECYCLE_EVIDENCE` record per
transition over the existing append-only `TicketStore`, in the fixed order

```text
AUTHORIZED -> CHECKED -> SENT -> BROKER_ACK -> POSITION_TRACKED -> CLOSED -> RECONCILED
```

with `HALT` reachable from any pre-terminal state. Each record carries the ticket id, the
prior state, the authority id, the guard-issued authorization id for the broker-facing
steps, the broker order / deal / position ids where applicable, the recomputed READY, risk
and freshness evidence ids, and UTC timestamps (`transitioned_at_utc` equals the store's
`recorded_at_utc`). The store's own seal (`outcome_id` over ticket, kind, source, timestamp
and payload hash) makes a tampered row a `LIFECYCLE_EVIDENCE_CONFLICT` rather than a silent
pass. Repeats, skips, backwards timestamps, and transitions missing their required
identifier are refused, not recorded. The lifecycle kind is deliberately not prefixed
`DEMO_EXECUTION_`, so `ExecutionLedger.inspect` still sees only its own claim rows.

The durable send claim is written **before** the `SENT` evidence row: a crash in between
leaves a `SENDING` row, and every later inspection of that ticket halts instead of
resubmitting.

An unknown outcome — a send result with no broker order identifier, an ack window that
closed with no reported result, a transport failure — halts: a `HALT` row is appended with
the reason and the state it halted from, the claim is marked uncertain, and the decision
reports `action_required: RECONCILE` and `resubmission: NEVER`. After that the ticket can
only be reconciled; `authorize_order_check` and `authorize_order_send` both refuse, the
claim stays uncertain permanently, and an `UNKNOWN` terminal result is refused
(`RECONCILIATION_EVIDENCE_INVALID`) so the halt is never resolved by guessing. Post-trade
evidence (`POSITION_TRACKED`, `CLOSED`) is still recorded after the standing authorization
is revoked or the emergency stop is engaged: revoking authority must never strand an open
position's evidence trail.

## Files

New: `src/demo_execution/authority.py`, `src/demo_execution/guarded_adapter.py`,
`src/demo_execution/lifecycle.py`, `src/demo_execution/host_magics.py`,
`config/demo_execution_host_magics.yaml`, `tests/_demo_execution_boundary_fixtures.py`,
`tests/test_demo_execution_authority_boundary.py`,
`tests/test_demo_execution_host_magics.py`.

Changed: `src/demo_execution/scope.py` (account login suffix, broker server type guard,
host magic registry resolution and collision refusal), `config/demo_execution_s1.yaml`
(`account_login_suffix: "985"`, `scope.host_magic_registry_path`),
`src/demo_execution/broker_adapter.py` (Protocol now requires `authority`, and
`authorization` for check and send), `src/demo_execution/__init__.py` (exports).

Not changed: strategy contracts, the strategy registry, risk ceilings, READY/D6 authority,
`demo_authorized` flags, `AGENTS.md`, `docs/agents/INVARIANTS.md`,
`src/demo_execution/confirmation.py`, `src/demo_execution/admission.py`, and
`tests/test_demo_execution_gates.py`.

Rebased onto `main` at `e97fe410` (PR #155, single-use owner confirmation). Three conflicts
were resolved by keeping both sides: `config/demo_execution_s1.yaml`
(`per_order_confirm_required: true` and `account_login_suffix: "985"`),
`src/demo_execution/__init__.py` (both export sets), and `src/demo_execution/scope.py`, where
the three new required `ScopePolicy` fields are declared before #155's defaulted
`per_order_confirm_required: bool = True` so the dataclass stays constructible.

## Verification

Date: 2026-10-11. Environment: sandboxed Linux 6.1.158+ x86_64, CPython 3.11.2,
repository dependencies at their `requirements.txt` pins (pandas 2.3.3, numpy 2.2.6), no
MT5 terminal and no network. The root `MetaTrader5.py` stub raises on every attribute
access, so any accidental broker call in these paths would fail the suite. All broker
interaction in the tests is a counted in-process double (`LiveAccountRead`) and all
timestamps are injected.

```text
$ .venv/bin/python -m pytest tests/test_demo_execution_authority_boundary.py \
    tests/test_demo_execution_host_magics.py tests/test_demo_execution_gates.py \
    tests/test_manual_ticket_report_and_boundary.py -q
155 passed in 15.68s

$ .venv/bin/python -m pytest -q
2283 passed, 5 skipped, 5 warnings in 167.92s (0:02:47)

$ .venv/bin/ruff check src/demo_execution/ tests/_demo_execution_boundary_fixtures.py \
    tests/test_demo_execution_authority_boundary.py tests/test_demo_execution_host_magics.py
All checks passed!
```

Status: **UNIT_TESTED OFFLINE**. Not live-verified, not host-verified, not
broker-verified. Bringing this boundary into contact with a terminal remains a separately
reviewed C11 host-execution import step; until then the committed scope stays
`enabled: false` and no code path in this repository can reach a broker.
