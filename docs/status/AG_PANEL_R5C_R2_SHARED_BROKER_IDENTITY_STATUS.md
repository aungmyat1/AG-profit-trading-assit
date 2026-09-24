# AG Panel R5C-R2 Shared Broker Identity Status

Date: 2026-09-24

## Classification

`PANEL_R5C_R1_REAUDIT_FAIL` -> remediated as candidate `PANEL_R5C_R2`.

## Lineage

- `R5B_R1_FROZEN_SHA`: `87e2da798f827caf95e8c6e58916b394641c98fb` (`origin/main`)
- `R5C_SHA`: `ff6f3ca2dfb5378318bd949fc19a33ba2249808b`
- `R5C_R1_SHA`: `1c5bbf5` (`fix/panel-r5c-broker-identity`)
- R5C-R2: this branch (`claude/hopeful-ptolemy-1tiv9c`), direct child of R5C-R1.

## R5C-R1 re-audit

R5C-R1 correctly fixes the R5C re-audit finding: a missing, sentinel, zero, negative,
boolean, or non-integer `ticket` no longer becomes a `"None"` broker identity.

A fresh auditor probe, using real MT5 field semantics, reproduced a new blocking defect.
MT5 gives a position and its opening deal **different** `ticket` values. The deal ticket
is a deal id. The position ticket (== `position.identifier`) is the ticket of the
opening order. R5C/R5C-R1 key both surfaces on `ticket`, so:

| Probe | Evidence | R5C-R1 result | Expected |
|---|---|---|---|
| A | open position (ticket 5001) + its opening deal (ticket 9001, position_id 5001) | `AMBIGUOUS`, record stays `SUBMISSION_PENDING` | `MATCHED` -> `BROKER_ACCEPTED` |
| B | matched while open (5002), then only the opening deal (9002, position_id 5002) after close | `CONFLICT`, record stuck at `BROKER_ACCEPTED` | `MATCHED` -> `RECONCILED` |

Both outcomes fail closed. No unsafe state is reached, and no resubmission happens.
But the ordinary filled-order case can never reconcile, so the boundary cannot do its
job. Unit fakes missed this because they gave a position and a deal the same `ticket`.

## Remediation (confined to `src/execution/reconciliation.py`)

Broker identity is now MT5's shared position identity on both surfaces:
`position.identifier` and `deal.position_id`. There is no fallback to `ticket`, so
missing shared identity is not evidence and stays `NOT_FOUND`. The R5C-R1 validation
(`_normalize_broker_ticket`) is reused unchanged. Exact AGT tag equality, the
`entry == 0` opening-deal filter, `AMBIGUOUS` for distinct identities, `CONFLICT` for a
persisted mismatch, and the unmutated-record rule for `NOT_FOUND` are all unchanged.

Test fakes now carry the MT5 identity fields (`identifier`, `position_id`), defaulting to
`ticket` so each earlier test keeps its original single-identity meaning. No assertion's
intent changed.

## Verification (2026-09-24, Linux container, MT5 portability stub, no live terminal)

- `pytest tests/test_execution_reconciliation*.py tests/test_execution_durable_idempotency*.py -q`
  -> **62 passed** (includes 5 new R5C-R2 tests in `tests/test_execution_reconciliation_r2.py`).
- `pytest tests/test_api_owner_decision_auth.py tests/test_api_authorize_demo_auth.py tests/test_execution*.py -q`
  -> 200 passed, 1 failed. The failure is
  `test_execution_mt5_gateway.py::test_order_check_failure_blocks_order_send`, which
  **fails identically on `origin/main`** without this change. It is pre-existing, outside
  this module, and not repaired here.
- The known pre-existing proposal-dedup failure
  (`test_proposal_envelope_adapters.py::test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`)
  still reproduces on `origin/main`. It is unrelated to reconciliation.

## Safety statement

No order_check, order_send, broker write, HTTP route, scheduler, lifecycle-table,
authorization, strategy, Demo, or Live change. Reconciliation is still unwired from any
runtime path. It is **not live-verified**: the identity semantics follow the MT5 API
contract and have not been observed against a live terminal.

## Status

- `SAFE_TO_FREEZE_R5C`: `NO`. This needs a fresh independent audit of R5C-R2.
- `SAFE_TO_START_R5D`: `NO`
- Recommended live check before freeze: on the demo terminal, confirm
  `positions_get()[i].identifier == history_deals_get(...)[j].position_id` for one
  AGT-tagged fill.
