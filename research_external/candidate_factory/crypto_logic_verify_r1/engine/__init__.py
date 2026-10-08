"""CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1 -- NEW implementation written from the frozen spec
(research_external/candidate_factory/crypto_logic_verify_r1/spec/CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC.md).

This is AG's own code, derived from a rule EXTRACTED from an external README (per the
EXTERNAL CODE RULE: never pip install/import/execute external repositories -- rule
extraction and independent reimplementation only). No source code from
CoenTan/Donchian-Breakout-Strategy-with-Turtle-Trading-System-2 is imported or vendored.

RESEARCH_ONLY: no proposal/demo/live/execution authority. Not registered in
strategies/registry.yaml. Freshness/remaining-R ticket actionability is explicitly NOT
implemented here (see spec's "Explicit non-scope" section) -- this module stops at the
deterministic-opportunity layer.
"""
from .turtle_breakout_d1 import (
    Bar,
    Decision,
    Ticket,
    TickResolution,
    evaluate,
    resolve_ticket,
)

__all__ = ["Bar", "Decision", "Ticket", "TickResolution", "evaluate", "resolve_ticket"]
