# AGP-C23 registry apply — OD1014-FAST D8 / D9 (2026-10-14)

Environment: Linux web sandbox, off-host; unit-tested only, not host-verified. No READY, demo, live, runtime
binding, contract or engine change.

- **D8** `ST_CRYPTO_CFD_SWEEP_RETEST_V1` 1.0.0: `logic_verified_identity` re-recorded `b8188dfb…` → `7a0946e4…`
  (`logic_status` STALE_IDENTITY → LOGIC_VERIFIED). Evidence: the C20 T2 re-replay of the same VT recorded 60d
  dataset, copied to `artifacts/logic_verification/ST_CRYPTO_CFD_SWEEP_RETEST_V1_1_0_0/c20_rerecord_2026-10-14/`
  (0 verdict mismatches). Previous identity and evidence kept as `previous_*` history. Scope unchanged: BTCUSD
  SHORT, ETHUSD LONG/SHORT; BTCUSD LONG uncovered.
- **D9** `ST_ASIAN_SWEEP_5R_V1` 1.1.3: candidate registration (`CANDIDATE_PENDING_OWNER_CONFIRM`, identity
  `7e232429…`), LOGIC_VERIFIED for EURUSD/GBPUSD × ASIAN_LONDON/LONDON_NEWYORK (RANGE_SWEEP); USDJPY/XAUUSD not
  verified. The v1.1.2 entries, the EURUSD × ASIAN_LONDON v1.1.2 suspension and S1 are unchanged.
- **Identity-set proof:** `strategies/registry.yaml` is in no file set of `v1_tickets.authority` (adapters,
  candidate contracts, candidate engine files). Digests computed on `origin/main` and on this branch are equal
  (S1 v1.1.2 `d7a8ebe5…`, ASW 1.1.3 `7e232429…`, CCFD 1.0.0 `7a0946e4…`); `tests/test_c23_identity_sets.py`.
- **Stamps:** `reporting.asw_lane._stamp` now follows the registry (`resolve_ticket_scope`, version-aware via
  `scope_status.REPORT_LANE_VERSIONS`); EURUSD × ASIAN_LONDON on the report lane stamps LOGIC_VERIFIED from the
  v1.1.3 record and stays REPORT_ONLY / non-actionable. CCFD per-ticket stamps stay UNVERIFIED
  (`WINDOW_NOT_IN_SCOPE`): the registry records no weekday/weekend window, so per-window evidence (which supports
  BTCUSD WEEKDAY SHORT and ETHUSD WEEKDAY LONG only) cannot be mapped to a record. Owner decision, not inferred.
- **Ledger** (`scripts/verification_ledger.py`, version-aware): LOGIC_VERIFIED 2 (S1 GBPUSD × ASIAN_LONDON
  v1.1.2; EURUSD × ASIAN_LONDON v1.1.3), UNVERIFIED 16. Other ASW scopes resolve against the v1.1.2 records
  because the report lane runs v1.1.2 for them.
- **C21 byte pin:** `tests/fixtures/c21/frozen_sha256.json` re-pins `strategies/registry.yaml` from `80317057…` to `8955c1b5…` (the D8/D9 edit, owner-decided); every other C21 frozen pin is unchanged.
