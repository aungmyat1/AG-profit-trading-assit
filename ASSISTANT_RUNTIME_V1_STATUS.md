# ASSISTANT_RUNTIME_V1 — Status / Evidence Report

2026-08-27. Evidence only — see `ASSISTANT_RUNTIME_V1.md` for architecture/design.

## Strategy registry resolution

`strategies/registry.yaml`: `SESSION_TRADE_V1` → `registered: true`, `active: true`,
`demo_authorized: true`. Live-verified via `strategy_manager.manager.evaluate()`
(below) — resolved without error.

## ASIAN_LONDON authority

`strategies/session_trade/contract.yaml`: `supported_cycles.ASIAN_LONDON` →
`status: ACTIVE`, `execution_authority: SIGNED`. Live run below reached the adapter and
returned a real strategy result — authority check passed as designed.

## LONDON_NEWYORK block (live evidence)

```bash
$ python scripts/trade_assistant.py --strategy SESSION_TRADE_V1 --symbol EURUSD \
    --cycle LONDON_NEWYORK --mode ANALYZE_ONLY --json
{"run_id": "bc61dc8c20bb", "status": "UNSIGNED_CYCLE", "strategy_status": "BLOCKED",
 "setup": null, "direction": null, "entry": null, "stop_loss": null, "target": null,
 "signal_id": null, "reason_codes": ["UNSIGNED_CYCLE"], "execution_mode": "ANALYZE_ONLY"}
```

Zero subprocess invocations (proven in `tests/test_strategy_manager.py::
test_london_newyork_cycle_is_blocked_and_adapter_never_called` and
`tests/test_assistant_runtime.py::test_london_newyork_blocked_end_to_end_zero_subprocess_calls`)
— the block happens in `strategy_manager/manager.py` before
`session_trade_adapter.run_session_trade_v1()` is ever called.

## ANALYZE_ONLY result (live, real MT5 + real Session Trade Codex subprocess)

```bash
$ python scripts/trade_assistant.py --strategy SESSION_TRADE_V1 --symbol EURUSD \
    --cycle ASIAN_LONDON --mode ANALYZE_ONLY --json
{"run_id": "917b6e07f471", "status": "NO_SETUP", "strategy_status": "NO_SETUP",
 "setup": null, "direction": null, "entry": null, "stop_loss": null, "target": null,
 "signal_id": null, "reason_codes": ["INVALID_ASIAN_RANGE"], "execution_mode": "ANALYZE_ONLY"}
```

`INVALID_ASIAN_RANGE` is `SESSION_TRADE_V1`'s own reason code, copied verbatim from
`analysis.json` — not invented by this runtime. Human-readable report (same run,
`--mode ANALYZE_ONLY` without `--json`):

```
AG PROFIT TRADING ASSISTANT

Strategy: SESSION_TRADE_V1
Symbol: EURUSD
Cycle: ASIAN_LONDON
Mode: ANALYZE_ONLY

MARKET CONTEXT
CONTEXT_READY

STRATEGY
Status: NO_SETUP
Setup: -
Direction: -

TRADE
Entry: -
SL: -
TP: -
Signal ID: -

EXECUTION
BLOCKED_BY_ANALYZE_ONLY

RESULT
NO_SETUP
Reasons: INVALID_ASIAN_RANGE
```

## SHADOW_DEMO result (live, partial)

Same live run in `SHADOW_DEMO` mode (`--check` passed to the subprocess) returned the
identical `NO_SETUP`/`INVALID_ASIAN_RANGE` result — the subprocess's own logic returns
before ever reaching its `order_check` branch when no signal was accepted today. This
proves the mode-to-flag wiring is correct but **does not** constitute evidence of a
real `order_check` call succeeding. **`REAL_ORDER_CHECK_VERIFIED = NO`** — pending a day
with an accepted `ASIAN_LONDON` signal. `SHADOW_CHECKED`/`ORDER_CHECK_REJECTED` mapping
logic is unit-tested with mocked `broker_check` payloads
(`tests/test_assistant_runtime.py`).

## DEMO execution result

Not attempted live this pass (no `--confirm` run against real MT5), per this session's
established practice of deferring live order-changing validation until explicitly
requested. Gating logic (three independent switches, `EXECUTED`/`EXECUTION_FAILED`
mapping) is fully unit-tested with a mocked adapter
(`tests/test_assistant_runtime.py::test_demo_execution_gate_executed`).

## Journal evidence

`journal/assistant_runs.jsonl`, one entry per live run above, e.g.:

```json
{"context_status": "CONTEXT_READY", "cycle": "ASIAN_LONDON", "direction": null,
 "entry": null, "execution_mode": "ANALYZE_ONLY", "execution_report": null,
 "reason_codes": ["INVALID_ASIAN_RANGE"], "run_id": "917b6e07f471",
 "status": "NO_SETUP", "strategy_id": "SESSION_TRADE_V1", "strategy_status": "NO_SETUP",
 "strategy_version": "1.0", "symbol": "EURUSD", "target": null,
 "timestamp_utc": "2026-08-27T16:16:57.809218+00:00"}
```

## Test evidence

- New this pass: 26 tests (`test_market_context.py` 4, `test_session_trade_adapter.py`
  7, `test_strategy_manager.py` 6, `test_assistant_runtime.py` 9).
- Full AG suite: **278 passed, 0 failed** (was 252 before this pass).
- Session Trade Codex full suite (run for audit, not modified): **314 passed, 2 failed,
  1 skipped** — matches the mission's own expected numbers exactly. The 2 failures are
  the governance-hash drift and golden-fixture classifier drift described in
  `ASSISTANT_RUNTIME_V1.md`'s "Known blockers" — **not fixed here**, reported per the
  mission's own instruction not to resolve authority ambiguity by guessing.

---

```
AG_PROFIT_TRADING_ASSISTANT = PRESERVED

ASSISTANT_RUNTIME_V1 = PARTIAL

MARKET_CONTEXT = READY
STRATEGY_MANAGER = READY
STRATEGY_REGISTRY = READY
ASSISTANT_DECISION = READY
REPORTING = READY
JOURNALING = READY

SESSION_TRADE_V1
REGISTERED = YES
ASIAN_LONDON = ACTIVE
LONDON_NEWYORK = UNSIGNED
STRATEGY_EXECUTION_CRITICAL_BLOCKERS = 0

RUNTIME MODES
ANALYZE_ONLY = READY
SHADOW_DEMO = READY (mode wiring live-verified; NOT_REAL_MT5_VALIDATED for the actual
  order_check call itself -- no signal was accepted on the live run to exercise it)
DEMO_EXECUTION = READY (gating logic implemented + unit-tested; NOT_ATTEMPTED live)
LIVE_EXECUTION = HARD_BLOCKED

MT5
REAL_TERMINAL_VERIFIED = YES
DEMO_ACCOUNT_VERIFIED = YES
REAL_ORDER_CHECK_VERIFIED = NO
REAL_ORDER_SEND_TESTED = NO

TESTS — AG PROFIT TRADING
PASSED = 278
FAILED = 0

TESTS — SESSION TRADE CODEX
PASSED = 314
FAILED = 2
RETIRED_LEGACY = 1

OPEN ISSUES
1. Session Trade Codex governance config-hash drift (test_engine.py) -- needs trader
   re-signoff, GOVERNANCE_RESIGN_REQUIRED, not fixed here.
2. Session Trade Codex golden-fixture classifier drift (test_golden_fixtures.py,
   UNCERTAIN vs RANGE) -- needs its own investigation, out of scope for this pass.
3. Real order_check/order_send evidence still pending a live day with an accepted
   ASIAN_LONDON signal (or explicit authorization to force one for validation).

ASSISTANT_ANALYZE_ONLY_READY = YES
ASSISTANT_SHADOW_DEMO_READY = NO (mode wiring proven; real order_check call unverified)
ASSISTANT_DEMO_EXECUTION_READY = NO (never attempted live, by design this pass)

READY_FOR_ASSISTANT_MANAGED_SESSION_TRADING = NO (ANALYZE_ONLY only; SHADOW_DEMO/
  DEMO_EXECUTION need a live accepted-signal day or explicit further authorization)
```
