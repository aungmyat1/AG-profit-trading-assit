# AG Panel R5C Independent Re-audit Status

Classification: `PANEL_R5C_INDEPENDENT_REAUDIT_FAIL`

Audited from immutable candidate
`ff6f3ca2dfb5378318bd949fc19a33ba2249808b` in a fresh worktree. No
implementation remediation was applied.

## Lineage and scope

- `R5B_R1_FROZEN_SHA`: `87e2da798f827caf95e8c6e58916b394641c98fb`
- `R5C_SHA`: `ff6f3ca2dfb5378318bd949fc19a33ba2249808b`
- Lineage valid; R5B-R1 is the direct parent.
- Observed files are exactly the expected reconciliation module, two test
  files, R5C status document, and `PROJECT_STATUS.md`.
- `src/execution/durable_idempotency.py` is unchanged from the frozen R5B-R1
  candidate; no R5A/R1 authorization production code changed.

## Verified behavior

R5B-R1 already contains `SUBMISSION_UNKNOWN -> BROKER_ACCEPTED`; R5C did not
change the transition table. The earlier textual summary was incomplete, but
the frozen implementation contract is internally consistent.

Reconciliation uses injected read-only position/deal lookups, exact equality
against the `AGT:<command_id>` tag, and only legal local transitions. Missing,
ambiguous, unavailable, and conflicting evidence normally fail closed; no
absence path resubmits or rewinds a durable record. No broker-write imports,
HTTP clients, MT5 submission, retry facility, or automatic execution path were
added. R5A/R1 authorization remains intact.

## Blocking finding

The implementation constructs broker identities with:

```python
str(getattr(record, "ticket", None))
```

Therefore an observation with the correct exact tag but no `ticket` becomes the
synthetic identity string `"None"`, is classified `MATCHED`, and can advance a
pending record to `BROKER_ACCEPTED` while persisting `broker_order_id="None"`.

An exact tag without a broker record identity is not deterministic broker
evidence. It must remain unresolved (`NOT_FOUND`, `EVIDENCE_INSUFFICIENT`, or
equivalent) rather than establish a broker match. This is an R5C production
defect independently reproduced by an auditor-owned probe.

## Tests and guarantees

- R5C focused suite: `18 passed`.
- Combined R5B/R5B-R1/R5C suite: `52 passed`.
- R5A/R1 authorization regression: `58 passed`.
- Auditor probe: failed as expected for the current defect because the code
  returned `MATCHED` with `broker_order_id='None'`.
- Known proposal-deduplication failure remains pre-existing, outside R5C scope,
  and unrelated to reconciliation identity.

Persistence and concurrency claims remain limited to inherited atomic
`os.replace`, ordinary restart persistence, and same-process transition
serialization. No fsync, power-loss, cross-process, cross-machine, or broker
exactly-once guarantee is claimed.

## Final status

- `R5C_FROZEN_SHA`: not approved
- `SAFE_TO_FREEZE_R5C`: `NO`
- `SAFE_TO_START_R5D`: `NO`
- Next action: smallest bounded R5C remediation is to reject matched broker
  observations whose required broker identity (`ticket`) is missing or invalid,
  then perform a fresh independent audit.

## Audit artifact

- Branch: `audit/panel-r5c`
- `R5C_AUDIT_ARTIFACT_SHA`: recorded by the commit containing this document
- Pushed: `NO`
