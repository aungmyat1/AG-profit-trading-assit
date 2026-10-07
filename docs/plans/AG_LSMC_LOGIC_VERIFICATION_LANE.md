# ST_LARGE_SMC_V1 Logic-Verification Lane — R3 (preparation only)

Two distinct identities, not combined:

```
ST_LARGE_SMC_V1@1.0.7  — RESEARCH_IDENTITY
  config: strategies/ST_LARGE_SMC_V1.yaml
  engine: src/large_smc_research/engine.py (RESEARCH_ONLY; no proposal/demo/live/execution/
          risk-sizing authority)
  C10 (stop-loss policy): SIGNED and implemented (c10_stop_policy.py, 2026-09-07) — see
          docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md
          and docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md
  Lifecycle: OFFLINE_RESEARCH -> FORWARD_RESEARCH (owner-promoted 2026-09-07,
          strategies/STRATEGY_LEDGER.md AG_LARGE_SMC_V1_FORWARD_RESEARCH_PROMOTION_V1)
  Next transition (FORWARD_RESEARCH -> OPERATIONAL_SHADOW): evaluated, not executed —
          blocked on an unresolved shadow-entry-evidence gate (registry note)

ST_LARGE_SMC_V1@1.1.0  — WATCH_IDENTITY
  config: strategies/ST_LARGE_SMC_V1_1_1_0.yaml
  engine: src/large_smc_watch/ (watch/alerts only, SHADOW_ALERTS_ONLY)
  instruments: EURUSD GBPUSD USDJPY XAUUSD BTCUSDT ETHUSDT (perpetual-style crypto names —
          see T4/D_CRYPTO_VENUE for the CFD-vs-perp distinction this creates)
  proposal_generation_authorized=false, alerts ARCHIVE_ONLY

RUNTIME_IDENTITY = NEITHER is wired to a running strategy-manager caller — registry
  itself states "nothing in this repo currently calls a strategy-manager runtime"
  (strategies/registry.yaml header comment).
```

```
C10_D1=RESOLVED — stop-loss policy signed v1.0.7 (c10_stop_policy.py)
C10_D2=NOT_VERIFIED this mission — AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2
  exists; its relationship to "D2" numbering not re-derived here (would require reading the
  full packet body; out of this mission's budget — do not infer content from filename alone)
C10_D3=NOT_VERIFIED this mission — same caveat, V3 packet exists
  (docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md)
EXPIRY_AUTHORITY=RESOLVED_BY_REUSE as of v1.0.6 (historical_replay/fill_simulator.py,
  per registry note); C12 contract resolution doc exists:
  docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md (not re-read in full)
OUTCOME_RESOLVER=PARTIAL — docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md exists;
  content not re-verified this mission
LOGIC_STATUS=NOT_VERIFIED for both 1.0.7 and 1.1.0 — no LOGIC_VERIFIED claim or blind
  verification report found for either identity (unlike PR #45's Asian Sweep r3 report,
  no equivalent r3-style report exists for ST_LARGE_SMC_V1 in the paths checked)
```

## Required sequence (already stated by the mission; recorded, not altered)

```
signed rule authority
→ C10 + expiry closure           (C10: RESOLVED; expiry: RESOLVED_BY_REUSE per registry note)
→ outcome resolver                (PARTIAL — status doc exists, content not re-verified)
→ runtime defect closure          (see known audit classes below — NOT closed)
→ freeze identity                 (NOT_VERIFIED / not found)
→ blind logic verification        (NOT_VERIFIED / not found — no equivalent of PR #45's R4A/R4B)
→ LOGIC_VERIFIED                  (NOT SET for either identity)
→ economic qualification separately (NOT_EVALUATED)
```

## Known runtime prerequisite defect classes (not fixed here)

- **Dedup**: `docs/status/AG_PROPOSAL_DEDUP_R1_STATUS.md` exists — status re status not
  re-verified this mission.
- **Identity drift**: `docs/status/LARGE_SMC_FROZEN_CONTRACT_DRIFT_ADJUDICATION_STATUS.md`
  exists — content not re-verified this mission.
- **Late alerts**: `docs/status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md`
  exists — content not re-verified this mission.

None of these three docs were opened in full this mission (token budget); their mere
existence is recorded as evidence that the defect classes were previously addressed in
some form, not that they are currently closed. Treat as `NOT_VERIFIED` until re-read.

## Bottom line

`ST_LARGE_SMC_V1` has NO analog yet to PR #45's R3/R4A blind-verification apparatus.
Building that apparatus (not just closing C10/C14-style contract gaps) is the real
remaining gap before `LOGIC_VERIFIED` can be claimed for either 1.0.7 or 1.1.0.
