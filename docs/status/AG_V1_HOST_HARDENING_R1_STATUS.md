# AG_V1_HOST_HARDENING_R1 — Status

## Governance

- Work done on the fixed session branch `arena/d1cea83b-ag-profit-trading-assit`
  (= PR #46's head). PR #46 (OPEN, draft) already exists on this branch — this session is
  pinned to this branch and may not create a second one (standing Arena-session policy); a
  "new branch + draft PR" could not be opened literally, so this work was added to the
  existing branch/PR instead, exactly as the two prior missions on this branch (R3 gap
  closure, `AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1`, `AG_CRYPTO_LOGIC_VERIFY_R1`)
  already did. No merge to `main` performed or proposed.
- **No `order_send`/`order_check`/`positions_get`/`position_close`/`orders_get` call added
  anywhere** — enforced both by the existing static test
  (`tests/test_host_go_live_kit.py::test_no_order_or_position_calls_anywhere_in_the_kit`,
  which globs every `scripts/host/*.py` including the new `export_crypto_history.py`) and by
  a dedicated new assertion for the new power scripts. `BROKER_MUTATION_COUNT=0`.
- **No strategy rule/threshold change beyond D1–D7.** `LSMC_ACTIONABILITY_POLICY_V1`
  (`src/lsmc_actionability_policy/`) is a new, separate decision layer that sits **after** an
  already-produced Large-SMC opportunity and **before** its Telegram send; it never recomputes
  or alters an entry/stop/target/direction/POI, and no FX/crypto strategy file, registry entry,
  or existing threshold (e.g. `v1_tickets.guards.STALE_AFTER`) was touched.
- `docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md` (the actual signed
  source for D1–D8) lives only on PR #48's branch (`audit/v1-followup-2026-10-07`, open,
  unmerged) — fetched and read directly from there for this mission (`git fetch origin
  pull/48/head`), not copied into this tree. Its full text is cross-referenced in
  `docs/specs/LSMC_ACTIONABILITY_POLICY_V1_SPEC.md`. D1–D8 are implemented/recorded exactly as
  written there (see "D5/D6/D8" below for the three that are statements, not code).

## Task / Status / Evidence / NOT_VERIFIED

| Task | Status | Evidence | NOT_VERIFIED |
|---|---|---|---|
| T1 — route sends through WP7 AttemptJournal | **PASS** | `send_message()` now returns the Telegram `message_id` (`src/host_delivery/telegram_message.py`); `_notify()` in `scripts/host/live_candles_smoke.py` writes one `ticket_delivery.AttemptJournal` line per actually-attempted send (LSMC alerts, FX tickets, manual tickets, crypto tickets) with a deterministic `delivery_attempt_id` and the captured `provider_response_id`. Tests: `tests/test_host_go_live_kit.py::test_wp7_attempt_journal_captures_attempt_id_and_message_id`, `..._records_failure_reason_without_secrets`, `..._skipped_when_policy_blocks_send` — all pass against synthetic sends (no live Telegram credentials in this sandbox). | A real Telegram message_id's exact shape/format from the live API (only a synthetic string is exercised here) |
| T2 — implement D1–D4, D7 with tests | **PASS** | `src/lsmc_actionability_policy/` (pure, no broker/network): `classify()` (D1 freshness, D2 remaining-R + send-time bid/ask + R_AT_TRIGGER, D4 unclosed-bar), `detect_downtime()`/`missed_digest()` (D3), `tag_and_rank_correlated()`/`correlated_exposure()` (D7, incl. the signed doc's XAUUSD `_SENSITIVE` bucket). Frozen spec `docs/specs/LSMC_ACTIONABILITY_POLICY_V1_SPEC.md` v1.0.0 (sha256 in the sidecar file). `tests/test_lsmc_actionability_policy.py`: 18 tests incl. the four named fixtures (07:01 case, XAUUSD late case, ETH low-R case, GBPUSD dedup case) — all pass. | **Not wired into the live `_watch_once`/`_notify` send path.** Doing so needs inputs that path does not currently carry at all: a live bid/ask quote for the LSMC watch loop (it has none today — only FX ticket building reads `Quote`), a `trigger_close_utc`/`signal_bar_closed` pair exposed per-alert (today's `AlertEvent` has `evaluated_at`/`trading_date` but not a separately tracked trigger-bar-close timestamp or closedness flag), and a persisted downtime checkpoint for D3. Wiring this is a distinct, larger follow-up mission, not fabricated here. |
| T3 — host power report + hardening proposal | **PARTIAL / scripts delivered, execution NOT_VERIFIED** | `scripts/host/report_power_settings.ps1` (read-only: `powercfg /lastwake`, `powercfg /devicequery wake_armed`, writes a timestamped report outside the tree) and `scripts/host/propose_power_hardening.ps1` (prints the current wake-armed devices + AC standby timeout + the exact proposed `powercfg`/scheduled-task commands; defaults to `-WhatIf`; even with `-Apply` it refuses unless `AG_OWNER_APPROVED_POWER_HARDENING=YES` is also set — a stronger gate than this kit's usual `-WhatIf`/`-Apply` convention, per this mission's explicit "do not apply without owner OK"). Static coverage: `tests/test_host_go_live_kit.py::test_power_scripts_are_read_only_or_gated_and_hold_no_secrets`. | **This sandbox is Linux; `powercfg` does not exist here and was never run.** No real `/lastwake` or `/devicequery wake_armed` output was captured — that requires the owner to run `report_power_settings.ps1` on the actual Windows host. Nothing was applied (by design: this task is PROPOSE-only). |
| T4 — export VT Markets MT5 BTCUSD/ETHUSD history | **PARTIAL / script delivered, execution NOT_VERIFIED** | `scripts/host/export_crypto_history.py`: `copy_rates_range(symbol, timeframe, date_from, date_to)` for BTCUSD/ETHUSD × M15/H1/H4 from 2015-01-01 (i.e. the terminal's full available history cache), `symbol_info()` dump (digits, tick size, contract size, spread, swap fields), per-(symbol,timeframe) CSV + sha256, bar-count/gap/first-last-timestamp reporting, and an `observed_trading_hours_utc_by_weekday` field. Refuses to run against a non-demo account (`require_demo_account`). 8 unit tests against a synthetic fake MT5 double (`tests/test_export_crypto_history.py`) verify the manifest/gap/hash logic deterministically. | **No real MT5 terminal exists in this sandbox** (`MetaTrader5.py` at the repo root is an explicit non-Windows stub that raises on every call — confirmed, see its own docstring) — **zero real bars were exported; no real bar counts/gaps/timestamps exist yet.** This is the same, previously-reported `AG_V1_HOST_HARDENING_R1 T4` data pack that `AG_CRYPTO_LOGIC_VERIFY_R1` searched for and did not find anywhere in the repo; it still does not exist as data — only the script that will produce it on the real host now exists. **Also confirmed (web search, 2026-10-07): the official MetaTrader5 Python package does not expose `symbol_info_session_quote`/`symbol_info_session_trade` at all** (MQL5 forum, "attribute missing" in the Python binding; `symbol_info().session_open/session_close` are price fields despite the name) — "trading hours incl. weekends" is therefore reported **empirically** (which UTC hour-of-day/weekday buckets actually contain a closed bar), not as a broker-declared schedule, and the manifest says so explicitly. |

## D5 / D6 / D8 — recorded, not code

- **D5** (precision stays display-only; "normalize-at-proposal" recorded as a Demo gate): no
  code change. `host_delivery.telegram_message.format_ticket()`'s tick-rounding (PR #48) already
  is display-only; nothing in this mission makes it executable. Recorded here as the Demo-gate
  checkpoint per the signed doc's own "Before Demo: executable normalization... = new frozen
  execution-compatible identity + re-verify affected geometry" — not attempted in this mission.
- **D6** (`ST_ASIAN_SWEEP_5R_V1` stays paused): no code change. Confirmed unchanged —
  `strategies/registry.yaml` / the strategy's own READY authority is untouched by this mission.
- **D8** (`SESSION_TRADE_V1` Demo authority DENIED): no code change. Confirmed unchanged — no
  Demo-authorization file or flag for `SESSION_TRADE_V1` was added, edited, or enabled.

## Tests

`python3 -m pytest tests/ -q` → **1090 passed, 4 skipped** (0 failed) on this branch after all
T1–T4 changes, including the pre-existing `AG_CRYPTO_LOGIC_VERIFY_R1` and
`AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1` suites. New files added this mission:
`tests/test_lsmc_actionability_policy.py` (18), `tests/test_export_crypto_history.py` (8), plus
4 new tests appended to `tests/test_host_go_live_kit.py`. No existing test was edited to make it
pass except the two LSMC `_notify()` call sites gaining additional identity kwargs, which no
existing assertion depended on.

## Next steps (not instructed this turn; for the owner/a future mission)

1. Run `scripts/host/report_power_settings.ps1` on the real Windows host and review
   `scripts/host/propose_power_hardening.ps1`'s printed plan before ever setting
   `AG_OWNER_APPROVED_POWER_HARDENING=YES`.
2. Run `scripts/host/export_crypto_history.py` against the real VT Markets demo terminal, then
   independently verify the resulting `manifest.json`'s sha256 values before treating any of
   that history as ticket evidence (per this mission's own fixtures-only constraint until then).
3. Wire `src/lsmc_actionability_policy` into the live LSMC watch/send path — needs live bid/ask
   quote plumbing into the LSMC loop, an explicit trigger-close-timestamp/bar-closedness field on
   `large_smc_watch.AlertEvent`, and a persisted downtime checkpoint for D3. Out of this
   mission's scope (T2 asked for "Implement D1-D4, D7 with tests", which is delivered).
4. Once (3) is done, `AG_CRYPTO_LOGIC_VERIFY_R1`'s own flagged dependency — crypto tickets
   emitting through `LSMC_ACTIONABILITY_POLICY_V1` instead of separate freshness/R logic — can
   finally be satisfied; `LsmcCandidate`/`classify()` are already generic enough to accept a
   crypto ticket's entry/stop/target/direction, but that adaptation is a distinct scoped mission.
