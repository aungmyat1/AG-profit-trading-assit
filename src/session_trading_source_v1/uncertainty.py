"""Source-rule uncertainty contract. NEW_SOURCE_IMPLEMENTATION.

These are source-contract FACTS recorded from ES-S1R's evidence, not tunable
parameters -- nothing in this module may be edited to "fix" the strategy; a fact
here changes only when new primary-source evidence is found and re-adjudicated in
a future mission, never in response to Oct-2022 (or any other) outcomes.
"""
from __future__ import annotations

NEW_ENTRY_CUTOFF = "SOURCE_AMBIGUOUS"
MAX_ENTRIES_PER_SESSION = "SOURCE_MISSING"
MAX_ENTRIES_PER_DAY = "SOURCE_MISSING"
TIGHT_RANGE_FILTER_THRESHOLD = "SOURCE_MISSING"
END_OF_SESSION_POSITION_POLICY = "SOURCE_AMBIGUOUS"
BE_COST_ADJUSTMENT = "SOURCE_UNADDRESSED"

# Candidate cutoff clock values found in source evidence, NEITHER verified --
# used only to bound where entry-cutoff uncertainty begins (see occurrence.py).
# Recorded here, not as accepted values, purely as the observed disputed range.
_DISPUTED_ENTRY_CUTOFF_EARLIEST_HOUR = 16  # earliest candidate seen in source evidence
_MANAGEMENT_END_HOUR = 22  # STRONGLY_SUPPORTED, carried forward from ES-S1R P7/P11
_NEW_ENTRY_START_HOUR = 7  # VERIFIED

# Candidate tight-range threshold VALUES found in source evidence (both explicitly
# excluded in ES-S1R as OUTCOME_DERIVED_INTERPRETATION -- neither is accepted as
# the real threshold). Used only as a disputed-zone bound: a range at or above the
# HIGHER candidate would not be filtered under either value ever seen in source
# material, so only ranges below it carry the uncertainty flag. This is the same
# disputed-bounds technique as the entry-cutoff handling above, not a chosen default.
_DISPUTED_TIGHT_RANGE_HIGHEST_CANDIDATE_PIPS = 15.0
