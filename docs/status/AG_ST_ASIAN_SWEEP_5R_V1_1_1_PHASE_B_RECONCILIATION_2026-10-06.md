# ST_ASIAN_SWEEP_5R_V1@1.1.1 — Phase B spec/engine reconciliation (2026-10-06)

Mission `AG_TRADE_TICKET_AND_WATCH_READINESS_R2`, Phase B. **Decision packet only: no behavior
change.** `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` and `src/strategy_engine/` are unchanged; v1.1.1
stays the frozen authority. Nothing here chooses a rule. Every row needs a written owner choice
before Phase C (successor version) can start. `EDGE_VERIFIED = FALSE`; `economic_status =
NOT_EVALUATED` for any successor.

Base: `main` at `13ffc38` (PR #37 and PR #39 merged). Builds on, and does not replace,
`AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION_STATUS.md`
(`ROOT_CAUSE_VERIFIED = ENGINE_GEOMETRY_DEFECT`, Model A `1.1.2-RC1`, never wired or promoted).

"Option A" is always *the YAML wins* and "Option B" is *the engine wins*, unless a row says
otherwise. A row may also need an Option C (both wrong, or the spec not evaluable).

## 1. Rule table

| # | Rule | YAML says | Engine does | Evidence (file:line) | Option A | Option B | Consequence |
|---|---|---|---|---|---|---|---|
| B-REF | Reference session | ASIAN_LONDON: Asian 00:00–06:00 GMT; LONDON_NEWYORK: London 06:00–11:00 GMT; box = High/Low/Mid/RangePips | Box from the window's own closed bars: high, low, mid, range, plus ER path metrics | YAML:43-65; `session/reference_box.py:32-72`; windows `v1_tickets/fx.py` `session_windows_utc` | — (agree) | — | No divergence. Anchoring is a separate owner choice (§4). |
| B-TRADE | Trading session | London_Open 07:00–11:00; New_York_Open 12:00–15:00 GMT | Same windows; candles filtered to the trade window | YAML:50-65; `v1_tickets/fx.py` (`session_windows_utc`) | — (agree) | — | No divergence. London_Open differs from canonical `london_am` (06:00) — already a recorded deviation (YAML:35-42). |
| B-REGIME | Regime / branches | Only sweep entries are declared (`entry_rules`); `regime_classification` declares EMA_50 + range check, with no TREND/RANGE routing | ER_ONLY_V2 classifier (ER ≥ 0.40 → TREND, else RANGE). TREND → Entry 1 (box direction, entry = box mid, stop = box extreme); RANGE → Entry 2 sweep, else Entry 3 boundary rejection | YAML:69-104; `session/classifier.py:13,26`; `session/router.py:48-55`; `session/setups.py:77-98,149-182` | Sweep only: TREND and Entry-3 paths produce no ticket | Declare TREND (Entry 1) and RANGE-rejection (Entry 3) in the successor spec, with their own geometry | A narrows ticket coverage to sweeps. B makes the spec describe three setups whose entry/stop/target rules differ from the sweep's (e.g. the TREND entry is the box mid, not a candle close). |
| B-SWEEP | Sweep definition | Wick breaches the reference boundary and the candle closes back inside the range | Strict: `high > box_high and close < box_high` (SHORT) / `low < box_low and close > box_low` (LONG); first qualifying candle; both sides on one candle → `AMBIGUOUS_DUAL_SWEEP` | YAML:97,102; `session/setups.py:109-144`; YAML:22-23 | — (agree) | — | No divergence. Strictness (no tolerance) is consistent with both. |
| B-DIR | Direction | Low sweep → LONG; high sweep → SHORT | Same | YAML:95-104; `session/setups.py:122-141` | — (agree) | — | No divergence. |
| B-ENTRY | Entry price | `entry_level: Sweep_Candle_Body_Close`, MARKET | `min(open, close)` (LONG) / `max(open, close)` (SHORT) — the body edge. When the sweep candle opens beyond the box, that is the candle's **open**, a price from 15 min before the signal exists | YAML:99,104 (and YAML:83-93, whose comment says "IS the close" but cites the body-edge code); `session/setups.py:128,138` | Entry = sweep candle close (the price available at signal time) | Keep body edge | **12 of 23 recorded sweeps have an engine entry outside the reference box** (§2 data), e.g. PASS B EURUSD LONG entry 1.12097 < box low 1.12112. Under B the ticket's MARKET entry can be a price the market was not at when the signal fired. A changes risk distance and therefore TP2 and lot size on every bullish-close LONG / bearish-close SHORT. |
| B-STOP | Stop geometry | `PERCENT_OF_SESSION_RANGE`, `stop_loss_range_pct: 0.25` | Sweep-candle wick extreme (`candle.high` / `candle.low`); `stop_loss_range_pct` is parsed, never read | YAML:108-109; `loader.py:33` (parsed only); `session/setups.py:128-129,138-139`; `engine.py:72` | Stop distance = 0.25 × reference range from entry | Wick extreme | Observed wick stops: 0.0–8.4 pips, including a zero stop (2026-07-17) and many sub-pip stops. A gives 2.7–9.4 pip stops on the 13 R5 sweeps (Model A record). **Linked to B-TGT-ORDER**: the stop choice changes how often TP1 lies beyond TP2. Under B the 15% spread/stop guard also blocks most tight stops (`SPREAD_TOO_WIDE`). |
| B-TGT-ORDER | Target ordering | Leg 1 `OPPOSITE_SESSION_BOUNDARY` (75 %), leg 2 `FIXED_R_MULTIPLE 5.0` (25 %); no ordering rule between them | Targets built as declared; nothing prevents TP1 beyond TP2. Manual L3 (`L3.target_order`) now **blocks** it | YAML:113-124; `v1_tickets/fx.py:151-158`; `v1_tickets/logic_gate.py` `L3.target_order` | Add an explicit ordering rule (e.g. reject, or drop/merge the leg) | No ordering rule: TP1 may lie beyond TP2 | **Geometry-only counts (§2):** body-edge entry + wick stop: TP1 beyond TP2 on **15/23**; body-edge entry + 25 % stop: **1/23** (entry outside box); close entry + wick stop: **4/10**; close entry + 25 % stop: **0/10**. Geometrically, a close-inside-box entry with a 25 % stop can never invert (TP1 distance < range < TP2 distance = 1.25 × range). |
| B-EMA | EMA_50 trend filter | `Price > EMA_50` bullish / `Price < EMA_50` bearish; no timeframe, price source or gating effect stated | Not consumed (no reference anywhere in `src/`) | YAML:70-73; repo-wide grep: 0 consumers | Implement it: owner must supply timeframe (e.g. M15/H1), price (close?), when it is measured (box close or signal bar), and whether it gates direction | Remove it from the successor spec | A cannot be implemented without those 4 owner inputs — not measurable as written. |
| B-RANGECHK | `range_session_check` | `Reference_Session_Range_Pips <= Max_Allowed_Pips`; 25 pips, EURUSD only; no stated effect | Not consumed (`max_range_pips_eurusd` parsed, never read) | YAML:74-79; `loader.py:76` | Implement as a gate (owner gives: effect = block? route to TREND? ; values for GBPUSD/USDJPY/XAUUSD) | Remove it | A also needs pip sizes per symbol (only EURUSD/GBPUSD are evidenced in the repo). |
| B-MINRANGE | Minimum range / stop | None declared | None; zero and sub-pip stops are emitted (2026-07-17 fixture: zero stop) | YAML (absent); `session/setups.py:129,139` | Add a minimum (owner value) | None | Under B-STOP=B a minimum stop is the only protection against zero/sub-pip risk; under B-STOP=A it becomes a minimum *range*. Owner must give the value; none is inferred here. |
| B-SPREAD | Spread / cost guard | `max_spread_allowed_pips: 2.0`; `slippage_limit_points: 10` | Engine: none. V1 ticket guard: spread > 15 % of stop → `SPREAD_TOO_WIDE` (not from the YAML). L2 checks the 2.0-pip cap only where pip size is evidenced | YAML:110-111; `v1_tickets/guards.py:15,35`; `logic_gate.py` `R.max_spread` | YAML 2.0-pip absolute cap is the guard | Keep the 15 % fraction guard (code constant) | Both, or neither, can be in the successor; the 15 % rule has no spec authority today. Slippage is a fill-time rule (N/A for a manual ticket). |
| B-EXPIRY | Signal expiry | None declared | V1 ticket: STALE after signal close + 15 min; manual ticket `valid_until` = min(signal close + 15 min, trade-window end, 15:00) | YAML (absent); `v1_tickets/guards.py:14`; `manual_ticket.py:204-206` | Spec declares the expiry (owner value) | Keep the code's 15 min | The 15 min is an implementation choice; it decides SIGNAL_STALE/TICKET_EXPIRED on every ticket. |
| B-TIMEINV | Time invalidation | "15:00 GMT" single global cutoff for both pairs | Ticket: 15:00 UTC. **R5 resolver: the pair's own trade-session end (11:00Z ASIAN_LONDON, 15:00Z LONDON_NEWYORK)**, owner-signed 2026-09-09 | YAML:129; `v1_tickets/fx.py:159`; `manual_ticket.py:204`; `scripts/resolve_forward_shadow_outcomes.py:42-57,112-115` | Global 15:00 for both pairs | Per-pair session end | The 13/13 evidence used B for exits; the ticket shows A. A successor must state one. |
| B-STRUCT | Structural invalidation | "M15 close fully outside the sweep wick low/high **with expansion volume**" | Not consumed; displayed only | YAML:130; `manual_ticket.py:211` | Define "expansion volume" measurably (owner: volume source — tick volume? — and threshold) | Drop the volume clause (close beyond wick only) | **Not deterministically measurable as written.** Option C: drop the rule entirely. |
| B-SPLIT | Position split / management | 75 % at TP1 then runner SL → breakeven; 25 % at 5R, trailing `NONE_OR_MANUAL_BE` | Ticket shows the split; management is post-fill (manual) | YAML:113-124; `v1_tickets/fx.py:157-158` | — (agree for a manual ticket) | — | `total_target_r: 5.0` is consistent with leg 2. Under B-TGT-ORDER inversion, leg 1 at TP1 is never reached before leg 2 — the split loses meaning. |
| B-MAXENTRY | Max entries per session | 1 | One decision per session (first qualifying candle) | YAML:54,65; `session/setups.py:109` | — (agree) | — | No divergence. |
| B-INSTR | Instruments | EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD | Engine accepts the list; V1 ticket universe is EURUSD/GBPUSD/USDJPY/XAUUSD | YAML:31; `engine.py:34` | — | — | AUDUSD is in the spec but not in the ticket universe; XAUUSD/USDJPY have no evidenced pip size for pip-denominated rules (B-RANGECHK, B-SPREAD A). |

## 2. B-TGT-ORDER — geometry-only counts (no win/loss)

Reproducible: `python -I scripts/research/phase_b_target_order_geometry.py --json
docs/status/evidence/AG_PHASE_B_TARGET_ORDER_GEOMETRY_V1.json`. It uses only recorded sweeps
already in the repo, and computes targets and TP1 vs TP2 position — no outcome, no R result, no cost.

| Source | Sweeps | Engine entry outside box | Body edge + wick (engine) | Body edge + 25 % | Close + wick | Close + 25 % (spec) |
|---|---|---|---|---|---|---|
| R5 forward-shadow (`artifacts/outcome_resolution/records/`, box from Model A records) | 13 | 7 | **10/13** | 1/13 | n/a (close not recorded) | n/a |
| PASS B replay (`docs/status/evidence/pass_b_replay_b92f529_0740Z/`) | 3 | 1 | 1/3 | 0/3 | 1/3 | 0/3 |
| Recorded EURUSD fixture (`tests/fixtures/manual_ticket/`) | 7 | 4 | 4/7 (+1 zero stop) | 0/7 | 3/7 | 0/7 |
| **All** | **23** | **12** | **15/23** | **1/23** | **4/10** | **0/10** |

The single 25 % inversion (R5 GBPUSD ASIAN_LONDON 2026-09-04 SHORT) is caused by the body-edge
entry lying 9.1 pips above the box high. It is a B-ENTRY effect, not a B-STOP effect.

## 3. Lineage of existing evidence: engine behavior vs spec behavior

| Evidence | Produced by | Detail |
|---|---|---|
| R5 13 forward-shadow trades, **13/13 losses, −1.00R gross, −3.38R net** (`AG_R5_EVIDENCE_PIPELINE_STATUS.md`, `AG_R6_ECONOMIC_GATE_OWNER_REVIEW_V1.md`) | **ENGINE behavior** | Wick stop (0.4–8.4 pips), body-edge entry (7/13 outside the box), TP1 = opposite boundary, TP2 = 5R (10/13 inverted). Fill model `MARKET_at_recorded_entry_price_at_ready_at`; exits cut at the pair's own session end (B-TIMEINV option B); net uses the CONTRACT_CEILING cost scenario. **No row of this evidence measures the YAML spec.** |
| Model A counterfactual, 13 events, 3W/10L, +0.86R gross (`artifacts/candidate_research/model_a_session_range_25/`) | **Hybrid** | YAML stop (25 % range) with the ENGINE entry (body edge) and engine TP1. Labelled `COUNTERFACTUAL_REPLAY`, `NOT_PROMOTION_EVIDENCE`. Not spec behavior either. |
| PASS A/B host acceptance (`AG_MANUAL_TRADE_TICKET_V1_STATUS.md`) | ENGINE behavior + manual gates | Infrastructure/logic-gate evidence only; L2 FAIL records the divergences above. No outcome. |
| Recorded fixture tests | ENGINE behavior | Test inputs; never economic evidence. |

Consequence: a successor that adopts any Option A above starts with **no** outcome evidence.
Evidence attributed to v1.1.1 stays attributed to v1.1.1 (AGENTS.md "Frozen strategy version
preservation").

## 4. Session anchoring options

Current rule: all windows are fixed GMT/UTC (`config/canonical_sessions.yaml` `dst_policy:
fixed_utc`; owner decision C3, DST is display only). UK BST ends **2026-10-25**; US DST ends
**2026-11-01**. UTC windows computed with `zoneinfo`:

| Window (as written) | Fixed UTC (current) | London-local, numbers as written | NY-local, EDT-equivalent (UTC−4 numbers kept) | NY-local, EST-equivalent |
|---|---|---|---|---|
| 2026-10-23 (BST, EDT) — Asian ref / London_Open / London ref / NY trade / time inv. | 00–06 / 07–11 / 06–11 / 12–15 / 15:00 | 23–05 / 06–10 / 05–10 / 11–14 / 14:00 | 00–06 / 07–11 / 06–11 / 12–15 / 15:00 | 23–05 / 06–10 / 05–10 / 11–14 / 14:00 |
| **2026-10-26** (GMT, EDT) | 00–06 / 07–11 / 06–11 / 12–15 / 15:00 | **same as fixed UTC** | **same as fixed UTC** | 23–05 / 06–10 / 05–10 / 11–14 / 14:00 |
| **2026-11-03** (GMT, EST) | 00–06 / 07–11 / 06–11 / 12–15 / 15:00 | same as fixed UTC | 01–07 / 08–12 / 07–12 / **13–16** / **16:00** | same as fixed UTC |

Readings for the owner:

- **Fixed UTC (current):** no change on any date. In London local terms the London_Open window
  is 08:00–12:00 in summer and 07:00–11:00 in winter; NY_Open is 08:00–11:00 EDT in summer and
  07:00–10:00 EST in winter.
- **London-local (numbers as written are GMT, so winter-equivalent):** identical to fixed UTC
  from 2026-10-26 through the winter; differs only during BST (one hour earlier in UTC).
- **NY-local for the NY trade window:** depends on which clock the numbers were written in.
  - Read as EDT (summer): 2026-10-26 is unchanged, but from **2026-11-02** the NY window
    moves to 13:00–16:00 UTC.
  - Read as EST (winter): the NY window is one hour earlier than now during **2026-10-26 to
    2026-10-31** (London has already left BST, New York has not).
- **Mixed (London-local for London windows, NY-local for NY):** between 2026-10-26 and
  2026-11-01 the London–NY offset is 4 h instead of 5 h. A per-window anchor makes the gap
  between the LONDON_NEWYORK reference end (11:00 UTC) and its trade start vary by date.
- **Conflict to resolve under any NY-local option:** the YAML's global "15:00 GMT" time
  invalidation (B-TIMEINV) falls *inside* a 13:00–16:00 UTC NY window after 2026-11-01.
  The owner must re-anchor or re-state it with the windows.

Existing tests pin fixed-UTC eligibility on 2026-10-23, 2026-10-27 and 2026-11-03
(`tests/test_manual_ticket_dst_clock.py:22-24`). **2026-10-26 is not pinned yet.** The mission
requires it, so it belongs to Phase C's test set. Any anchoring change is a successor-version
rule change (C3).

## 5. Phase D carry-in — rename the "no setup yet, window open" WATCH

`scan_record.classify_fx_ticket` (`src/v1_tickets/scan_record.py:79-80`, PR #37 Phase 3,
`f3b66d1`) relabels the frozen engine's `NO_TRADE` / `NO_SETUP_BY_WINDOW_END` (or
`NO_QUALIFIED_SWEEP_IN_WINDOW`) as state `WATCH`, reason `SETUP_WINDOW_OPEN:<engine reason>`,
while the trade window is open. It is a lifecycle state (never a block reason, never sent).
It is **not** the mission's WATCH ("rules satisfied up to, not including, the trigger"): it
asserts nothing about the range, regime or approach to a boundary. Keeping the name would
collide with Phase D's WATCH.

Owner choice of the new state name (no code change in this packet):

| Option | Name | Note |
|---|---|---|
| A | `SETUP_WINDOW_OPEN` | Matches the existing reason prefix; clearest about what it means |
| B | `AWAITING_TRIGGER` | Reads well, but implies the pre-trigger rules passed, which is not checked |
| C | `NO_SETUP_YET` | Pairs naturally with `NO_SETUP` at window end |

Phase D then needs owner thresholds for the real WATCH predicate. For example: does "range
formed" require B-RANGECHK or B-MINRANGE, and is there an "approaching boundary" distance?
None exists in the spec today.

## 6. Owner decisions required (Phase C cannot start without them)

1. One option per row: B-REGIME, B-ENTRY, B-STOP, B-TGT-ORDER, B-EMA, B-RANGECHK, B-MINRANGE,
   B-SPREAD, B-EXPIRY, B-TIMEINV, B-STRUCT (rows marked "agree" need only confirmation).
2. Any values an Option A needs: EMA timeframe/price/timing/effect; range-check effect and
   per-symbol values; minimum range/stop; expiry; volume definition.
3. Session anchoring (§4), including how the time invalidation is anchored.
4. The Phase D rename (§5).
