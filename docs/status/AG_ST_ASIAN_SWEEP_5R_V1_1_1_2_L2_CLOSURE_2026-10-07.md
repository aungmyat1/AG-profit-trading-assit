# ST_ASIAN_SWEEP_5R_V1@1.1.2 — Logic Gate L2 closure (2026-10-07)

**Candidate only. Asian Sweep READY stays paused until the owner confirms the Phase B table.**
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` (v1.1.1) remains the frozen current authority and is
byte-for-byte unchanged. The runtime still loads it, and its registry `logic_status` stays
`NOT_VERIFIED`, so no `TICKET_READY` can come from this change. `EDGE_VERIFIED = FALSE`;
`economic_status = NOT_EVALUATED`; demo/live authority unchanged (both `false`).

Owner instruction (2026-10-07): for each divergence in
`AG_ST_ASIAN_SWEEP_5R_V1_1_1_PHASE_B_RECONCILIATION_2026-10-06.md`, the engine's behavior
becomes the spec. Where engine behavior is undefined or unsafe, the spec fails closed instead.
The unconsumed EMA_50 filter is removed. Every resolution is a **recommendation** pending
owner confirmation (Phase B table below).

Version naming: this `1.1.2` is not the never-registered research label `1.1.2-RC1` (Model A,
25 % stop, `AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md`).

## Changed paths

| Path | Change |
|---|---|
| `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml` | New candidate contract, with a changelog entry per divergence row |
| `src/strategy_engine/loader.py`, `models.py` | `stop_loss_range_pct` is required only for `PERCENT_OF_SESSION_RANGE`; `max_range_pips_eurusd` is required only when `range_session_check` is declared. v1.1.1 still loads identically, and a v1.1.1-style file missing either field still raises `KeyError`. No decision logic changed. |
| `src/v1_tickets/logic_gate.py` | L2 evaluates what the YAML declares: the new candidate rules (`R.regime_branch`, body-edge `R.entry_level`, wick `R.stop_loss`, `R.max_spread_fraction`, `R.signal_expiry`, `R.target_order`, `R.structural_invalidation` NONE). v1.1.1 checks are unchanged. |
| `src/v1_tickets/fx.py` | `build_fx_ticket(strategy_path=...)` for offline candidate replay; runtime default unchanged |
| `src/v1_tickets/authority.py` | `CANDIDATE_CONTRACTS` binds a candidate's logic identity to its own contract file |
| `strategies/registry.yaml`, `STRATEGY_LEDGER.md` | `candidate_versions."1.1.2"` added: `LOGIC_VERIFIED` with an identity digest, `ticket_ready: PAUSED_PENDING_OWNER_CONFIRM` |
| `tests/test_asian_sweep_v1_1_2_l2_closure.py` | 10 focused tests |

Identity: `logic_verified_identity = d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5`
(engine `243c4ff1…`, contract `941dec55…`). Any change to the engine files or the candidate
contract invalidates it. A test pins this.

## Phase B table — recommended resolutions (all PENDING_OWNER_CONFIRM)

| Row | v1.1.1 YAML | Engine / implemented | **RECOMMENDED (v1.1.2)** | Kind | Owner |
|---|---|---|---|---|---|
| B-REGIME | Sweep entries only | ER_ONLY_V2: TREND → Entry 1 (entry box mid); RANGE → Entry 2 sweep, else Entry 3 rejection (entry box boundary) | Declare all three branches. TREND and RANGE_REJECTION → **FAIL_CLOSED** (`ENTRY_LEVEL_NOT_MARKET_AT_SIGNAL`): their MARKET entry is a level the market is not at when the signal fires. Only SWEEP is ticket-eligible. | engine + fail-closed | PENDING_OWNER_CONFIRM |
| B-ENTRY | `Sweep_Candle_Body_Close` | Body edge `min/max(open, close)` | `SWEEP_CANDLE_BODY_EDGE` with `entry_must_equal_close: true`. When the body edge is the open (a pre-signal price), **FAIL_CLOSED** (`ENTRY_NOT_AVAILABLE_AT_SIGNAL`) | engine + fail-closed | PENDING_OWNER_CONFIRM |
| B-STOP | 25 % of reference range | Sweep-candle wick extreme | `SWEEP_CANDLE_WICK_EXTREME`; `stop_loss_range_pct` removed; risk ≤ 0 → **FAIL_CLOSED** | engine + fail-closed | PENDING_OWNER_CONFIRM |
| B-TGT-ORDER | No ordering rule | No rule (TP1 may pass TP2) | `FAIL_CLOSED_IF_TP1_BEYOND_TP2` (same predicate as L3) | fail-closed | PENDING_OWNER_CONFIRM |
| B-EMA | `Price >/< EMA_50` | Not consumed | **Removed** | removed | PENDING_OWNER_CONFIRM |
| B-RANGECHK | ≤ 25 pips (EURUSD), no stated effect | Parsed, not consumed | **Removed** | engine | PENDING_OWNER_CONFIRM |
| B-MINRANGE | None | None (zero stop emitted) | No minimum; risk > 0 only (B-STOP). Suggested later value: ≥ 2.0 pips EURUSD/GBPUSD, **not enforced** | engine + fail-closed | PENDING_OWNER_CONFIRM (value) |
| B-SPREAD | 2.0-pip cap | V1 guard: spread ≤ 15 % of stop | Both: 2.0-pip cap (pip-evidenced symbols) **and** ≤ 0.15 × stop. Not measurable → **FAIL_CLOSED** (USDJPY/XAUUSD always fail L2 until pip size is evidenced) | implemented + fail-closed | PENDING_OWNER_CONFIRM |
| B-EXPIRY | None | 15 min after signal-bar close | `signal_expiry_minutes: 15` | implemented | PENDING_OWNER_CONFIRM |
| B-TIMEINV | 15:00 GMT global | Ticket 15:00 (agrees); R5 resolver per-pair end | Keep 15:00 GMT global (spec and ticket already agree). R5 evidence stays attributed to v1.1.1 | agree | PENDING_OWNER_CONFIRM |
| B-STRUCT | Close beyond wick "with expansion volume" | Not consumed (unmeasurable) | `NONE`: removed. A close beyond the wick extreme means the wick-extreme stop was already hit | engine | PENDING_OWNER_CONFIRM |
| B-REF, B-TRADE, B-SWEEP, B-DIR, B-SPLIT, B-MAXENTRY, B-INSTR | — | agree | Unchanged | agree | PENDING_OWNER_CONFIRM |

Not decided here, still in the owner template: session anchoring (packet §4) and the Phase D
rename of `SETUP_WINDOW_OPEN` (packet §5).

## Logic Gate L1–L6 on the recorded EURUSD fixtures (ASIAN_LONDON, evaluated 11:00Z)

`tests/fixtures/manual_ticket/EURUSD_M15_recorded.csv`. Spread is a test input
(tight = 0.2 pip, wide = 0.8 pip). It is not recorded data.

| Day | Engine output | L1 | L2 | L3 | L4 | L5 | L6 | L2 FAIL ids (all declared fail-closed) |
|---|---|---|---|---|---|---|---|---|
| 2026-06-15 | NO_SETUP | — | — | — | — | — | — | no ticket levels |
| 2026-06-16 | TREND SHORT | PASS | FAIL | FAIL | PASS | WARN | PASS | regime_branch, entry_trigger, entry_level, stop_loss |
| 2026-06-17 | SWEEP LONG (entry = open 1.16075 ≠ close 1.16134) | PASS | FAIL | FAIL | PASS | WARN | PASS | entry_level, target_order |
| 2026-06-23 | SWEEP SHORT 1.14300 / SL 1.14351, tight spread | **PASS** | **PASS** | **PASS** | **PASS** | WARN | PASS | — |
| 2026-06-23 | same, wide spread | PASS | FAIL | PASS | PASS | WARN | PASS | max_spread_fraction (0.157 > 0.15) |
| 2026-07-17 | SWEEP SHORT, zero stop | PASS | FAIL | FAIL | PASS | WARN | PASS | entry_level, stop_loss, target_leg2, max_spread_fraction, target_order |

L5 shows WARN only because the owner has not set `cost_warn_R` (advisory, never blocks).
No candidate check is `NOT_EVALUABLE` on any fixture. **`logic_status = LOGIC_VERIFIED`
(candidate 1.1.2)**: the spec and engine have no remaining divergence. Every blocking FAIL
comes from a declared fail-closed rule, and the conforming sweep passes L1–L4.
v1.1.1 on the same fixtures is unchanged: L2 FAIL (`trend_bias_filter`, `range_session_check`,
`structural_invalidation` NOT_EVALUABLE; `stop_loss` FAIL).

## Tests (2026-10-07, Linux Codespace, Python 3)

- `python -m pytest tests/test_asian_sweep_v1_1_2_l2_closure.py -q`: **10 passed**
- 44 affected test files (v1_tickets / strategy_engine / registry): **880 passed, 2 skipped**
- `python -m pytest tests -q`: **1154 passed, 2 skipped**

No live MT5 or host run was performed. Only unit tests on the recorded fixtures have run.

## Next

Owner fills `AG_ST_ASIAN_SWEEP_5R_V1_1_1_PHASE_B_OWNER_DECISIONS.md` (confirm or amend each
row above). Promotion of 1.1.2, i.e. switching `config_source` and un-pausing READY, is a
separate, explicit owner step.
