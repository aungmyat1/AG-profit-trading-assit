# Research eligibility quarantine manifests

This directory is populated only by
`scripts/run_crypto_cfd_research_eligibility.py` after it verifies the immutable PR #32
BTCUSD/ETHUSD source hashes. Each canonical per-symbol JSON record is a reproducible
quarantine artifact, not an economic result:

- raw quality remains `BLOCKED_UNKNOWN_GAPS`;
- every UTC date has an explicit reference-day decision/reason set;
- conservative observation-day eligibility carries its previous-reference dependency;
- incomplete dates remain visible and quarantined;
- existing paths may only be reproduced byte-for-byte, never replaced.

No source files are available in this checkout, so no data-specific eligibility manifest
is committed. The runner does not create R2 partitions or execute C001.
