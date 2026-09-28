"""AG canonical, strategy-neutral proposal envelope (Workstream 0 / M1A).

See models.py for the versioned schema. This package contains NO detection logic and NO
execution imports anywhere -- see tests/test_proposal_envelope_execution_boundary.py for
the static AST guard proving that, plus tests/test_proposal_envelope_models.py for a
behavioral companion. Adapters under proposal_envelope.adapters map each existing
strategy-specific output losslessly into the common envelope; they never invent a field
and never redetect anything the source module has not already computed.
"""
