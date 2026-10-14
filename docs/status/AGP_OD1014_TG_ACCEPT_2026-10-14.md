# AGP-OD1014-TG-ACCEPT-R1 — REPORT_ONLY Telegram acceptance (2026-10-14, first checkpoint)

**Verdict: PARTIAL.** This PR is never COMPLETE (owner addendum).
- **LSMC:** evidenced.
- **ASW GBPUSD × ASIAN_LONDON:** FAIL. The cycles ran in-window, but no Telegram message was sent.
- **CCFD and ASW LONDON_NEWYORK:** PENDING their windows.

Evidence was read without changes from the host tree and its journal/log files. Messages were
re-rendered offline with the same code (`render_report` is unchanged between `726b16a` and
`50bd6db`). Nothing was sent and no host file was written.

## 1. Host binding

| Item | Value |
|---|---|
| Host tree HEAD | `50bd6db5b2d3253ee8fdb70ec463201ab852da9d` (pulled `--ff-only` 06:37Z; before that `726b16a`) |
| `origin/main` at capture end (07:19Z) | `e01ba87` = #215 (VT 60d FX data, script and test only; merged 07:04:51Z; head `6fab878` = squash, 0 file diffs). The host lag has no runtime effect |
| Tasks | All run `D:\wp3-main-integ\.venv\Scripts\pythonw.exe scripts\host\live_candles_smoke.py`, every 15 min (PT15M); no schedule change made |

| Task | Mode | Last run (UTC) | Result | Next run (UTC) |
|---|---|---|---|---|
| AG-V1-FX-Cycles | `--mode fx --canonical` | 07:16:16 | 0 | 07:31:31 |
| AG-V1-Crypto-Daily | `--mode crypto` | 07:17:17 | 0 | 07:32:32 |
| AG-V1-LSMC-Watch | `--mode lsmc` | 07:18:18 | 0 | 07:33:33 |

Run identity in the host logs: VTMarkets-Demo, terminal `C:\Program Files\MetaTrader 5`. Records
since 06:37Z carry `code_sha 50bd6db…`.

## 2. Per-family result

| Family / scope | Window | Result | Evidence |
|---|---|---|---|
| ASW@1.1.2 GBPUSD × ASIAN_LONDON | 07:01Z, 07:16Z cycles | **FAIL — silent** | See §3 |
| LSMC@1.1.2, 6 symbols | 07:03Z, 07:18Z runs (plus overnight) | **EVIDENCE** | See §4 |
| CCFD@1.0.0 BTCUSD/ETHUSD | ~13:00Z | **PENDING** | Crypto log: `OUTSIDE_WINDOW (BEFORE_WINDOW)` every cycle to 07:17Z |
| ASW LONDON_NEWYORK | ~15:00Z | **PENDING** | |

## 3. ASW GBPUSD × ASIAN_LONDON — FAIL (silent)

| Cycle | Decision | Reason | Delivery | message_id |
|---|---|---|---|---|
| 07:01:09Z | BLOCKED | `LOGIC_SCOPE_NOT_VERIFIED` | `summary_only`, ticket `ARCHIVE_ONLY` | none |
| 07:16:16Z | BLOCKED | `LOGIC_SCOPE_NOT_VERIFIED` | `summary_only`, ticket `ARCHIVE_ONLY` | none |

- Both cycles logged `REPORT_LANE ASW observations=3 classes=NO_OPPORTUNITY` and `REPORT_DELIVERY ASW none`.
- No FX send appears in `canonical_fx/delivery.sqlite` after 06:55Z.
- Under the addendum's rule ("a correct 'no setup + reason' message counts; silence counts as FAIL"), both cycles are **FAIL**.
- A session summary is sent at the window close; on 2026-10-13 it arrived at 11:31Z (`FX_SESSION_SUMMARY … delivery=sent`). Today's is not yet evidenced and does not change the per-cycle verdict.
- **Reason ambiguity:** the evaluation ran `ST_ASIAN_SWEEP_5R_V1@1.1.2` (`code_sha 50bd6db`), while `resolve_ticket_scope` gives S1 `LOGIC_VERIFIED`. `src/v1_tickets/fx.py` emits `LOGIC_SCOPE_NOT_VERIFIED` on two paths:
  - an S1 identity mismatch (L172–187);
  - an emitted branch other than RANGE_SWEEP (L217–219).
- The archived record keeps no `detail`, so which path fired cannot be determined from the evidence. `entry`, `sl` and `tp*` are null (no priced plan).

## 4. LSMC@1.1.2 — six symbols

### Runs in the 07:00–07:30Z window

| Run | Symbol | State | Report class | Delivery | message_id |
|---|---|---|---|---|---|
| 07:03Z | EURUSD | NEAR_POI | WATCH | duplicate-suppressed | — |
| 07:03Z | GBPUSD | NEAR_POI | — (no new observation) | — | — |
| 07:03Z | USDJPY | REJECTED | BLOCKED: OPPORTUNITY blocked by `FAIL_CLOSED_RR_BELOW_SPEC_MINIMUM` | sent | **12813** |
| 07:03Z | XAUUSD | NEAR_POI | — | — | — |
| 07:03Z | BTCUSD | NEAR_POI | WATCH (+ NO_OPPORTUNITY suppressed by policy) | sent | **12814** |
| 07:03Z | ETHUSD | NEAR_POI | — | — | — |
| 07:18Z | EURUSD | DEVELOPING | WATCH | duplicate-suppressed | — |
| 07:18Z | GBPUSD | NEAR_POI | WATCH | duplicate-suppressed | — |
| 07:18Z | USDJPY, XAUUSD, BTCUSD, ETHUSD | REJECTED / NEAR_POI | — (no transition) | — | — |

All 12 symbol-runs read `data=FRESH`, `source=MT5_VT_MARKETS_DEMO`. LSMC is a continuous watch, so a
symbol with no state transition emits no message by design. That is not a silent session.

### Per-message check (re-rendered from the archived canonical records)

| Check | 12813 USDJPY | 12814 BTCUSD |
|---|---|---|
| strategy@version | `ST_LARGE_SMC_V1 v1.1.2` | same |
| 1.1.2 NOT_VERIFIED stamp | `scope=NOT_VERIFIED (VERSION_NOT_IN_SCOPE:1.1.2)` | same |
| Class + reason | `OPPORTUNITY (BLOCKED)`; `also: FAIL_CLOSED_RR_BELOW_SPEC_MINIMUM` | `NEAR_POI (WATCH)` |
| Entry / SL / targets | none (correct: no valid plan) | none (WATCH) |
| Spread / cost verdict | **absent** | absent (n/a for WATCH) |
| REPORT_ONLY tag | header `REPORT ONLY -- NON-ACTIONABLE`, footer `REPORT ONLY - NOT AN ORDER \| EXECUTION: DISABLED` | same |
| Proposal / READY wording | none | none |
| ASCII | yes | yes |

Defects (cosmetic, no authority impact):
1. The first `blocked by:` line shows the state code `LSMC_OPPORTUNITY`; the real gate appears only under `also:`.
2. A BLOCKED OPPORTUNITY has no spread/cost verdict line.

### Since 2026-10-13T17:00Z (report-lane journal)

| Item | Value |
|---|---|
| Report-lane results (all LSMC, 1.1.0 then 1.1.2) | 32 sent (message_id 12781–12814, unique), 37 duplicate-suppressed, 0 delivery failures |
| `execution_authorized` | `False` on every record |
| Policy-suppressed observations (`NOT_SENT_POLICY`, INFO / NO_OPPORTUNITY) | 37 today, recorded in `delivery_status` |

## 5. Execution isolation

| Item | Before (07:01Z) | After (07:19Z) |
|---|---|---|
| Order / intent / queue stores in host `journal/` | 0 | 0 |
| `DEMO_ORDER` routes in `journal/ticket_store` | 0 | 0 |
| `journal/paper_trades` files | 3 | 3 |
| `journal/ticket_store` files | 3 | 4 (new `evaluations/2026-10-14.jsonl`, all BLOCKED, `ARCHIVE_ONLY`) |

The code has no order-queue implementation; the only `queue` hit is `src/edge_discovery/models.py`,
which is unrelated. No OPPORTUNITY entered any execution path.

**MT5 guard (Oct 13–14):** 235 + 4 (07:01–07:18Z) guard records:
- `ORDER_SEND_ATTEMPTS=0`, `ORDER_CHECK_ATTEMPTS=0`, `PROHIBITED_ORDER_API_ATTEMPTS=0` throughout;
- `BROKER_MUTATION_REQUESTS_FORWARDED=0`, `BROKER_HISTORY_CLEAN`.

**Zero broker mutation.**

**S1 READY:** `strategies/registry.yaml` 1.1.2 `ticket_ready: PAUSED_PENDING_OWNER_CONFIRM`
(unchanged), and `config/demo_execution_s1.yaml` `enabled: false`.

## 6. Next checkpoint

A separate commit or PR after 15:00Z covering:
- CCFD BTCUSD/ETHUSD in the ~13:00Z crypto window;
- the ASW LONDON_NEWYORK window;
- today's AL session summary (~11:30Z).

For the ASW silent-cycle FAIL, the owner needs to decide whether per-cycle BLOCKED tickets must be
delivered rather than `summary_only`. Persisting the block `detail` would also resolve the
reason ambiguity in §3.
