"""AG_EXTERNAL_CANDIDATE_VALIDATION_LAYER_V1.

Infrastructure for admitting, versioning, reproducing, and validating a FROZEN
strategy candidate produced by an external research/optimization process (e.g.
Gemini). This package performs no optimization, invents no candidate, and grants
no execution/Demo/Live authority -- see docs/status/AG_EXTERNAL_CANDIDATE_VALIDATION_
LAYER_V1_STATUS.md for the authority boundary this package exists to enforce:

    EXTERNAL RESEARCH (hypothesis/parameter search/candidate selection)
        -> REPOSITORY (admission, reproduction, R5 evidence, R6 evaluation)
        -> EXECUTION (separate, already-existing, unrelated authority)

Every module here is pure/deterministic: no network calls, no broker access, no
filesystem mutation of existing evidence, no wall-clock-dependent behavior beyond an
explicitly supplied `generated_at`.
"""
