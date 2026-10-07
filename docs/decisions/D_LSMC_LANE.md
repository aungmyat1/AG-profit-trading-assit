# Owner Decision Packet: D_LSMC_LANE

This packet references, and does not duplicate, the existing C10/expiry packets:

- `docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2_STATUS.md`
- `docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md`
- `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`
- `docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`

See `docs/plans/AG_LSMC_LOGIC_VERIFICATION_LANE.md` for the full identity table and
sequence (`signed rule authority → C10 + expiry closure → outcome resolver → runtime
defect closure → freeze identity → blind logic verification → LOGIC_VERIFIED →
economic qualification`).

## What the owner needs to decide here

1. Whether `ST_LARGE_SMC_V1@1.0.7` (RESEARCH) and `@1.1.0` (WATCH) should build a
   PR #45-style R3/R4A/R4B blind-verification apparatus as a **joint** lane, or
   **separately per identity** — no such apparatus currently exists for either.
2. Whether the three known runtime defect classes (dedup, identity drift, late alerts —
   each already has a prior status doc, none re-verified closed this mission) must be
   re-confirmed closed before freeze-identity work starts, or can proceed in parallel.
3. Priority relative to the Asian Sweep R4B lane (T3) and crypto venue lane (T4) — see
   `docs/status/AG_READINESS_NEXT_MISSIONS_2026-10-07.md` for a proposed but
   owner-overridable ordering.

No threshold, freeze date, or implementation approach is recommended here.
