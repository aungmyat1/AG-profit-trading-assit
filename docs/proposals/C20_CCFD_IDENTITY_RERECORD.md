# C20 proposal — re-record the CCFD 1.0.0 logic identity

Mission AGP-C20-VERIFICATION-LEDGER-R2 (T2). Proposal only: nothing here changes `strategies/registry.yaml`,
READY, demo/live flags or the runtime. Owner decision OD1014-FAST D1: the CCFD runtime stays **1.0.0**; this is
the re-record path for that version.

## Why
`ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.0.0` is `STALE_IDENTITY` since 2026-10-11: merging main changed identity-set
files (`src/v1_tickets/logic_gate.py`, `src/v1_tickets/manual_ticket.py`,
`config/v1_tickets/crypto_cfd_ticket_policy.yaml`); no strategy rule file changed.

## Evidence (re-replay, VT recorded 60 days, 2026-08-11..2026-10-09)
Summary: `artifacts/verification_ledger/c20_rerun_summary.json` (`t2_ccfd_1_0_0_recorded_60d`).

| Symbol | Branch | Recorded (b507e116…) | Re-replay | Identical |
|---|---|---|---|---|
| BTCUSD | SHORT | verified, L1–L6 PASS, 2 emissions | verified, L1–L6 PASS, 2 emissions | yes |
| BTCUSD | LONG | not verified (0 emissions, L2–L6 INSUFFICIENT) | same | yes |
| ETHUSD | LONG | verified, L1–L6 PASS, 3 emissions | same | yes |
| ETHUSD | SHORT | verified, L1–L6 PASS, 2 emissions | same | yes |

- 0 mismatches per symbol; signal event-log verdict PASS with 0 event-log mismatches on both symbols.
- 1320 tickets in both runs with identical decision and reason codes per ticket.
- Differences are schema additions only (added `event_id` on signal-log entries; added provenance keys in the
  report). No mismatch category changed.
- Contract hash unchanged (`492efaf5…`). Engine identity changed `119c6a4d…` → `0a3886eb…` (the identity-set
  edits above); recomputed logic identity **`7a0946e41b2e1e79ea5ee8c47df1eb3e99fe94181f29cd36f30eb6ce797dc2a2`**.

## Proposed registry diff (not applied)
In `ST_CRYPTO_CFD_SWEEP_RETEST_V1.candidate_versions."1.0.0"`:

```yaml
logic_status: LOGIC_VERIFIED                       # was STALE_IDENTITY
logic_verified_identity: 7a0946e41b2e1e79ea5ee8c47df1eb3e99fe94181f29cd36f30eb6ce797dc2a2
# logic_verified_symbols[*].logic_identity -> the same digest
# evidence -> the committed re-replay output (to be committed with the decision), evidence_sha256 -> its hash
# keep logic_status_recorded / stale_identity_* as history (re-recorded <date>, owner decision <id>)
```

Scope stays exactly as recorded: **BTCUSD SHORT, ETHUSD LONG, ETHUSD SHORT**. **BTCUSD LONG stays uncovered**
(no LONG entry on the VT days); it is not added.

## Owner decision required
Approve or reject re-recording identity `7a0946e4…` for the three covered scopes. Logic only: no economic/edge
claim, no READY, demo or live authority.
