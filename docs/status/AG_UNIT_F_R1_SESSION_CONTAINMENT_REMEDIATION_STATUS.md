# Unit F R1 — Session Containment Remediation (2026-09-29)

**Classification:** `UNIT_F_R1_READY_FOR_REAUDIT`

| | |
|---|---|
| Base (audited Unit F tip) | `76348c728b2229de2ad0a5c22f857bf0263de60f` (tree `5f27bf5e56f4412361482c9329ebe8bb3a837c71`) |
| Audited range | `6fdc921a91bcd1913dc8804495cdcd5ed1395d7a..76348c728b2229de2ad0a5c22f857bf0263de60f` |
| Arena result | `UNIT_F_AUDIT_FAIL` — two blocking findings |
| Scope | only BF-F-001 and BF-F-002; no redesign, no economic-semantics change |

## Arena blocking findings (verbatim)

> **BF-F-001**
> Explicit `--session OTHER` permits broker initialization outside POST_ASIAN / POST_LONDON.

> **BF-F-002**
> The target-session gate is checked before initialization, but not revalidated immediately before actual capture start, so preparation latency could push a 12-minute capture beyond the requested window.

## Remediation

Production change is limited to `scripts/capture_vt_spread_evidence.py`.
`src/fx_friction_capture/spread_capture.py` is unchanged, as are the serialization, hash,
validity and spread semantics.

### BF-F-001: `OTHER` removed as a capture request mode

- `CAPTURE_REQUEST_SESSIONS = ("POST_ASIAN", "POST_LONDON")`.
- `session_gate()` returns `UNSUPPORTED_CAPTURE_SESSION` for every other requested value:
  `OTHER`, unknown names, a wrong-case name, and the empty string.
- `main()` stops with status `UNSUPPORTED_CAPTURE_SESSION` (exit 2, JSON) before lineage
  checks and before any MetaTrader5 call. That means no `initialize`, `symbol_info`,
  `symbol_info_tick`, server-time acquisition, or other broker read.
- argparse no longer uses `choices=`. An argparse rejection would bypass the JSON
  fail-closed status. The gate is the single validator.
- The unreachable `OTHER` branch of the manifest status mapping was removed. A POST_*
  request yields `VT_<SESSION>_CAPTURE_COMPLETE` or `VT_SESSION_CAPTURE_FAILED`, exactly as
  before.

**`OTHER` is still an allowed evidence classification. It is a forbidden live-capture
request mode.** `spread_capture.classify_session()` and the row field
`session_classification` are unchanged. Historical capture
`VT_SPREAD_20260928T190357Z_18ee81e6` (classification `OTHER`, collector V1) remains valid,
attributed evidence and was not touched. R1 changes only future capture-request authority.

### BF-F-002: second containment gate immediately before capture

Gate 1 is the precheck. It is unchanged in position: first, before lineage and before
`MetaTrader5.initialize()`. It uses the injectable `_utcnow()`, and a failure gives
`TARGET_SESSION_NOT_ACTIVE` with 0 broker calls.

Gate 2 is new. It runs after lineage, the stub check, `initialize`, venue/server/DEMO
validation, the symbol spec checks and server-time setup (`server_time_provenance`,
`server_time_timeline`), and immediately before the monotonic cadence origin and the first
`symbol_info_tick`. It takes a fresh `_utcnow()` and re-runs `session_gate(session,
capture_start, duration)`. On failure it returns
`TARGET_SESSION_WINDOW_EXPIRED_DURING_SETUP`, with `reason`, `precheck_utc` and
`capture_start_utc`, from inside the existing `try`. The `finally` then calls
`MetaTrader5.shutdown()`. No capture directory, raw row or manifest is created, because
evidence is written only after the loop.

### Window arithmetic (exact `datetime`/`timedelta`, no minute rounding)

The canonical windows are unchanged and weekday-only: POST_ASIAN is `07:00 <= t < 11:00`
UTC and POST_LONDON is `12:00 <= t < 15:00` UTC.

A capture passes when three conditions hold: the start is on a weekday,
`window_start <= start`, and `start + duration <= window_end`. The end may equal
`window_end` because every sample is taken strictly before the end.

For 720 s, the latest valid start is **10:48:00** for POST_ASIAN and **14:48:00** for
POST_LONDON. Tested boundaries: 10:47:59 and 10:48:00 pass, 10:48:01 is blocked; 14:47:59
and 14:48:00 pass, 14:48:01 is blocked.

## Evidence

Deterministic tests only. A fake MetaTrader5 module records every broker read, and an
injected clock replaces timing. The tests contain no `sleep()`. There was no live broker
contact: the optional read-only smoke check was not run, because the current time
(~17:00Z) is outside both target windows and would only exercise gate 1.

| Probe | Result |
|---|---|
| `--session OTHER` / `LONDON` / `post_london` at Mon 19:44Z | `UNSUPPORTED_CAPTURE_SESSION`, broker calls `[]`, server-time calls `[]`, no evidence dir |
| Precheck fail (10:48:01, 14:48:01, Saturday) | `TARGET_SESSION_NOT_ACTIVE`, broker calls `[]` |
| Setup latency POST_ASIAN 10:47:50 → capture start 10:48:05 | `TARGET_SESSION_WINDOW_EXPIRED_DURING_SETUP`; `initialize` 1, server-time setup done, `symbol_info_tick` 0, `shutdown` 1 (last call), mutations 0, no evidence dir |
| Setup latency POST_LONDON 14:47:50 → 14:48:05 | same |
| Valid POST_ASIAN 07:05 (60 s, 12 rounds) | reaches the collector: 24 ticks, `VT_POST_ASIAN_CAPTURE_COMPLETE`, zero-spread preserved (12/12 flagged), commission `UNKNOWN`, slippage `UNKNOWN/INSUFFICIENT_SAMPLE`, authority all NONE / `NOT_CREATED` |
| Static AST (`test_collector_has_no_execution_capability`) | no `order_send`/`order_check`/positions/orders/trade_* calls, no execution/strategy imports |
| Runtime mutation traps | `broker_mutation_calls` all 0 in every runtime test |

Unchanged prior gates were re-run in the same file: pip sizes, spread arithmetic,
zero-spread flagging, venue/server/environment/symbol isolation, stale tick, NaN/Inf,
ask < bid, deterministic serialization and hash, secret-free serialization, metadata probe,
and canonical window equality with the pilot configs.

The regression check ran the same file against the unremediated base script. The two
`OTHER` gate rows failed, which confirms the tests detect BF-F-001. Against the base
script, the runtime tests proceed into the real 720 s sampling loop instead of stopping,
which is BF-F-002 itself.

Commands (Windows host, Python venv, 2026-09-29):

```
python -m pytest -q tests/test_fx_friction_capture.py   -> 69 passed (base: 42)
python -m pytest -q tests/test_fx_*.py                  -> 167 passed
```

## Unchanged

- Spread semantics: `spread_price = ask - bid` and `spread_pips = spread_price / pip_size`.
- Pip sizes, venue and server identity, the DEMO requirement, and the 60 s stale threshold.
- Zero-spread preservation and the metadata schema.
- Raw serialization, hash semantics, write-once behavior, `.gitattributes` evidence pinning
  and secret filtering.
- `COMMISSION_STATUS = UNKNOWN`, `SLIPPAGE_STATUS = UNKNOWN/INSUFFICIENT_SAMPLE`.
- Authority: PROPOSAL, DEMO and LIVE are NONE; `TRADE_TICKET = NOT_CREATED`.
- Nothing in StrategyBinding, ProposalEligibility, TradeTicket, MarketState, the
  instrument registry, the Opportunity scanner, risk, execution, strategy code or
  SEALED_OOS was touched.

## Next step

`ARENA_REAUDIT_ONLY_BF_F_001_BF_F_002_PLUS_REGRESSION_OF_PREVIOUS_PASSING_GATES`. Arena
closes the audit.
