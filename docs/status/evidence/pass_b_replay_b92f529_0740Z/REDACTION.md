# Redaction record — PASS B `REPLAY_PINNED_0740Z` evidence

| Field | Value |
|---|---|
| Date | 2026-10-06 |
| Approval | Owner-approved |
| File changed | `run_result.json` (only file; every other evidence file is byte-identical) |
| Field changed | `journal` — the host scratchpad prefix of the path was replaced by `<HOST_SCRATCHPAD>`; the remainder (`/PASS_B_REPLAY_b92f529\journal`) is unchanged |
| Reason | The original path contained the host's local Windows username |
| Original `run_result.json` sha256 | `c636330df14f0c9572e3bf3fe003f30d1729949ba3faca062475caecb51311b7` (as listed in `SHA256SUMS.original`) |
| Redacted `run_result.json` sha256 | `23c417ead8a6b59368ebaa96d9a9309e83b179ce9cdf2bf48d391db549273e25` (as listed in `SHA256SUMS`) |
| Source of redacted files | host branch `host/pass-b-evidence-b92f529-r` @ `167bb27` |
| Original retrievable at | commit `398a169`: `git show 398a169:docs/status/evidence/pass_b_replay_b92f529_0740Z/run_result.json` |

`SHA256SUMS` covers the redacted set (12/12 verify). `SHA256SUMS.original` is the unmodified checksum
file from the sealed run and verifies against the files at `398a169`. No test result, state,
count or price in the evidence was changed.
