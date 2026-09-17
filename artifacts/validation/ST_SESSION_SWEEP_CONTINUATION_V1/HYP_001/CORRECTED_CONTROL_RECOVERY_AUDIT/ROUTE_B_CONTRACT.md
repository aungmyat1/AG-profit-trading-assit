# Route-B Fresh-Replay Amendment Contract (P7) — NOT executed in this mission

If a future mission is separately preregistered to execute this, it must:

- Use exactly the raw dataset hashes recorded in `RAW_DATA_INVENTORY.md` for GEN_001/GEN_002A/GEN_002 (no substitution, no window change).
- Use exactly the v1.0.1 strategy authorities recorded in `STRATEGY_IDENTITY_MANIFEST.md` (unchanged since preregistration, re-verified this mission).
- Preserve `OPPOSITE_SESSION_BOUNDARY`, unchanged setup/entry/stop rules, unchanged friction, unchanged `AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER` ambiguity policy.
- Introduce no new filters, no new exclusions, no parameter changes, no window changes, no dataset substitution.
- Explicitly resolve the `CONTRACT_AMBIGUOUS` H1-bias-gate-vintage question flagged in `RAW_DATA_INVENTORY.md` before running, not silently assume either way.

## Phase 1 — Occurrence reconstruction (upstream, runner-target-independent per `PAIRED_OCCURRENCE_PROOF.md`)

Regenerate and freeze, **before any CONTROL economic interpretation**:
- Occurrence ID
- `reference_high`/`reference_low`
- Entry (timestamp, price)
- Initial stop
- Source dataset fingerprint
- A reference (path + hash) to the required post-entry candle evidence

Generate `RECONSTRUCTED_OCCURRENCE_POPULATION_HASH` at this point, before touching `runner_target_r` at all.

## Phase 2 — Outcome resolution (only after Phase 1 is frozen)

Run `resolve_campaign_entry(..., runner_target_r=3.0, ...)` for the corrected CONTROL. Per `PAIRED_OCCURRENCE_PROOF.md`, the same frozen Phase-1 population may later be reused for a 1.5R treatment resolution pass **as its own separate, still-not-yet-authorized mission** — this contract does not authorize that treatment run, only documents that no re-detection would be required for it.

This contract is descriptive/preparatory only. **No replay is executed by this mission.**
