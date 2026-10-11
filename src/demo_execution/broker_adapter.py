"""C11 import point only; intentionally no concrete broker adapter exists here.

The host's already-reviewed canonical execute_command boundary must supply these
operations when C11 is imported. This Protocol does not implement, wrap, or call MT5.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol


class CanonicalBrokerAdapter(Protocol):
    """Single interface seam for the C11 canonical execution import."""

    def order_check(self, *, ticket: Mapping[str, Any], account_mode: str) -> Mapping[str, Any]:
        """Delegate to the existing canonical order_check path; implementation lives in C11."""
        ...

    def order_send(self, *, ticket: Mapping[str, Any], checked_order: Mapping[str, Any],
                   account_mode: str) -> Mapping[str, Any]:
        """Delegate to the existing canonical order_send path; implementation lives in C11."""
        ...

    def reconcile(self, *, ticket_id: str, send_result: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return only a reconciled terminal result; unknown results must halt."""
        ...
