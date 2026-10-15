---
class: STATUS_EVIDENCE
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# C14 Dispatch HALT Persistence Remediation (2026-10-15)

## Scope

PR #235's dispatch returned `HALTED` after an unknown send or failed acknowledgement
without checking that the guard had persisted lifecycle state `HALT`. A refused halt
can leave the ticket in `SENT`; reporting it as halted hides an unreconciled outcome.
The dispatcher also called broker methods named `order_check` and `order_send`, which
violated the repository's single physical-call-site boundary.

The dispatcher now uses semantic adapter methods. `MT5CanonicalAdapter` exposes these
as aliases of its checked methods, so raw MT5 order calls remain in the canonical
adapter. Dispatch reports `HALTED` only when the guard decision says `state == HALT`;
otherwise it reports `HALT_FAILED` with the guard's reason. Regression cases cover
unknown-send and acknowledgement-fallback persistence failures.

## Verification

- Date: 2026-10-15.
- Environment: Windows PowerShell, Python 3.14.0, fake terminal only.
- Command: `python -m pytest -q tests/test_demo_execution_dispatch.py tests/test_manual_ticket_report_and_boundary.py tests/test_demo_execution_authority_boundary.py`
- Result: **121 passed**; the post-lint rerun completed in 384.41 seconds.
- Lint: `python -m ruff check src/demo_execution/dispatch.py tests/test_demo_execution_dispatch.py` — passed.
- `git diff --check`: passed.
- GitHub CI was pending at initial evidence capture; required checks later passed on code commit `492c5013362755ab74f9553f4a99936028d8f9b2`.
- Host / MT5 verification: not run. No broker operation was attempted.

This remediation changes no scope, READY authority, standing authorization, execution
flag, order shape, or live-account capability. S1 remains disabled and the host path
remains unapproved. The independently owner-approved `PILOT_FULL_TP1` shape remains
analytics-excluded, with margin mode `UNKNOWN_UNTIL_HOST_VERIFIED`; that shape approval
does not enable a scope or authorize an order.
