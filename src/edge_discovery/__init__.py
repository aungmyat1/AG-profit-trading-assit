"""AG Edge Discovery Candidate Factory V0 (AG_EDGE_DISCOVERY_ACCELERATION_R1).

Research-only pipeline layer:

    CANDIDATE -> CONTRACTABILITY -> DEV FAST REPLAY -> FRICTION SCREEN
              -> PROMOTE / REJECT -> FREEZE SURVIVOR -> existing verification authority

Hard boundaries:
  - No execution surface: nothing here imports a broker-mutation path, and
    EXECUTION_AUTHORIZED is a constant False.
  - FAST_SCREEN_PASS is a research-prioritization outcome. It is NEVER EDGE_VERIFIED
    and can never become EDGE_VERIFIED inside this package.
  - Fail closed: missing data, missing fields, role violations, and cross-instrument
    substitution all produce stable reason codes, never silent fallbacks.
"""
EXECUTION_AUTHORIZED = False
PROPOSAL_AUTHORITY = "BLOCKED"
