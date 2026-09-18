"""Friction authority for the VirtualBroker (P10).

A FrictionProfile carries the per-component cost state with the mission's vocabulary:

    BROKER_EVIDENCED -- measured from admitted broker evidence
    BROKER_SPECIFIED -- from the broker's own published specification
    MODELED          -- from an admitted model / documented config default
    UNAVAILABLE      -- no data at all

Invariant: UNAVAILABLE is never silently converted to zero. `total_cost_R` raises
FrictionUnavailableError if any consumed component is UNAVAILABLE, so a virtual fill
can never be costed as if friction were free.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class FrictionComponentState(str, Enum):
    BROKER_EVIDENCED = "BROKER_EVIDENCED"
    BROKER_SPECIFIED = "BROKER_SPECIFIED"
    MODELED = "MODELED"
    UNAVAILABLE = "UNAVAILABLE"


class FrictionUnavailableError(Exception):
    """Raised when a cost component is UNAVAILABLE but a cost total is demanded."""


@dataclass(frozen=True)
class FrictionComponent:
    state: FrictionComponentState
    value_R: Optional[float] = None  # cost expressed in R per round trip
    unit: str = "R"

    def admitted(self) -> bool:
        return self.state is not FrictionComponentState.UNAVAILABLE and self.value_R is not None


@dataclass(frozen=True)
class FrictionProfile:
    spread: FrictionComponent
    commission: FrictionComponent
    slippage: FrictionComponent
    funding: Optional[FrictionComponent] = None

    def components(self) -> tuple:
        comps = (self.spread, self.commission, self.slippage)
        return comps + ((self.funding,) if self.funding is not None else ())

    def admitted(self) -> bool:
        return all(c.admitted() for c in self.components())

    def total_cost_R(self) -> float:
        """Sum of all admitted component costs in R. Raises on any UNAVAILABLE (never
        returns zero as a stand-in)."""
        if not self.admitted():
            unavailable = [k for k, c in self._named().items() if not c.admitted()]
            raise FrictionUnavailableError(
                f"friction components not admitted: {', '.join(unavailable)} -- "
                "UNAVAILABLE never converts to zero"
            )
        return sum(c.value_R for c in self.components() if c.value_R is not None)

    def _named(self) -> dict:
        d = {"spread": self.spread, "commission": self.commission, "slippage": self.slippage}
        if self.funding is not None:
            d["funding"] = self.funding
        return d


def zero_modeled_profile() -> FrictionProfile:
    """Convenience profile with all components MODELED at 0.0 R. Explicitly MODELED, not
    UNAVAILABLE -- so it may be consumed as an admitted (albeit optimistic) assumption."""
    zero = FrictionComponent(state=FrictionComponentState.MODELED, value_R=0.0)
    return FrictionProfile(spread=zero, commission=zero, slippage=zero)
