# AG Panel R5C-R1 Broker Identity Remediation Status

`R5C_R1_BASE_SHA`: `ff6f3ca2dfb5378318bd949fc19a33ba2249808b`

This candidate remediates the independently reproduced R5C defect where exact
AGT-tag evidence with a missing ticket became `broker_order_id="None"` and
advanced to `BROKER_ACCEPTED`.

The fix is confined to `src/execution/reconciliation.py`: `_normalize_broker_ticket`
accepts only positive integer MT5 ticket identities and returns `None` for missing,
blank, sentinel, zero, negative, boolean, or non-integer values. Matching filters
invalid identities before classification. Invalid evidence therefore cannot produce
`MATCHED`, persist a broker ID, advance lifecycle state, or trigger retry/submission.
Valid exact-tag tickets remain matchable; mixed invalid-plus-valid evidence uses only
the valid identity; conflicting valid identities remain fail-closed.

Validation tests cover the original exploit, invalid values, valid values, wrong tags,
multi-surface evidence, and restart recovery from `SUBMISSION_UNKNOWN`.

Verification:

- R5C-R1 + R5C focused/no-submit tests: 23 passed.
- R5B/R5B-R1/R5C/R5C-R1 tests: 57 passed.
- R5A-R1 authorization regression: 58 passed.
- Adjacent execution-boundary tests: 7 passed.
- No order-check, order-send, broker, Demo, Live, lifecycle-table, scheduler, or
  authorization changes.

Status: implementation candidate; ready for independent re-audit. Do not freeze or
start R5D from this branch.
