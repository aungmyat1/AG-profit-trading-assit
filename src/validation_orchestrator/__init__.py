"""AVO-WP1 -- read-only, strategy-neutral validation status orchestrator.

See docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md (section 22, AVO-WP1) and
docs/validation/AG_ACCELERATED_VALIDATION_PLAN_V1.md (section 26, AVP-WP1) for the
governing specification. This package implements ONLY the state model and read-only
status derivation described there -- no scheduler, no persistent ledger, no agent
dispatch, no prompt renderer, no execution path of any kind.
"""
