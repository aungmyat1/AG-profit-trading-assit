"""The canonical broker interface. Its single implementation is
:class:`demo_execution.mt5_canonical_adapter.MT5CanonicalAdapter` (B', C14); this Protocol does not
implement, wrap, or call MT5 itself.

Boundary contract (hardened 2026-10-11): every operation takes the execution-authority
object *and* the single-use authorization that
:class:`demo_execution.guarded_adapter.GuardedCanonicalAdapter` issued for exactly that
step. An implementation must re-validate both inside itself
(:mod:`demo_execution.authority`) immediately before it touches the broker -- the
caller's own gate results are never sufficient on their own -- and must report every
outcome back through the guard so the lifecycle evidence trail
(:mod:`demo_execution.lifecycle`) stays complete. An unknown outcome is HALTed and
reconciled; it is never resubmitted.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from demo_execution.authority import ExecutionAuthority


class CanonicalBrokerAdapter(Protocol):
    """Single interface seam for the C11 canonical execution import."""

    def check_order(self, *, authority: ExecutionAuthority, authorization: Mapping[str, Any],
                    ticket: Mapping[str, Any], account_mode: str) -> Mapping[str, Any]:
        """Delegate to the existing canonical order_check path; implementation lives in C11.

        `authorization` is the guard's ORDER_CHECK authorization (single-use, unexpired, bound to
        this ticket and to the live DEMO account read the guard took immediately before issuing
        it). `account_mode` must be the guard-verified mode, never a caller-supplied guess.
        """
        ...

    def send_order(self, *, authority: ExecutionAuthority, authorization: Mapping[str, Any],
                   ticket: Mapping[str, Any], checked_order: Mapping[str, Any],
                   account_mode: str) -> Mapping[str, Any]:
        """Delegate to the existing canonical order_send path; implementation lives in C11.

        `checked_order` must be the same structure the guard sealed into the CHECKED evidence row;
        `authorization` is the guard's ORDER_SEND authorization, issued only after the durable
        send claim was written.
        """
        ...

    def reconcile(self, *, authority: ExecutionAuthority, ticket_id: str,
                  send_result: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return only a reconciled terminal result; unknown results must halt."""
        ...
