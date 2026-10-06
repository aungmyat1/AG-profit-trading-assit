# replay_pinned_cycle.py -- PRESERVED EVIDENCE HARNESS (verbatim copy, no logic change)
#
# Source commit: b92f529020321a71eb00957ca70dfe6a850bd603 (PR #37 head, claude/stoic-cerf-tjp8xm)
# Purpose: PASS B read-only replay of the 2026-10-06 ASIAN_LONDON FX cycle with the evaluation
#          clock pinned to 07:40:00 UTC. Bars are fetched live via copy_rates_from_pos and
#          truncated to those closed by the pinned clock; spreads replay the values recorded by
#          the original PASS B run (07:39:57 UTC). Output evidence:
#          docs/status/evidence/pass_b_replay_b92f529_0740Z/
# Read-only guarantees:
#   - MT5 is wrapped in a proxy that refuses any order_*/positions_*/orders_*/history_*/TRADE_ACTION
#     attribute and any callable not on a read-only allowlist (initialize, shutdown, last_error,
#     account_info, terminal_info, version, symbol_info, symbol_info_tick, symbol_select,
#     copy_rates_from_pos); refusals are recorded in mt5_refused.
#   - Runs only on an account whose trade_mode is DEMO (require_demo_account + trade_mode check).
#   - Stops if MetaTrader5 resolves to the repo-root placeholder rather than the installed package.
#   - Telegram _notify is replaced by an in-memory capture; nothing is sent.
#   - Writes only to the isolated journal given as argv[1]; never to the production journal.
# Paths (WT, interpreter) are host-specific and kept as run. Usage:
#   <host venv python> scripts/host/replay_pinned_cycle.py <output_dir>
"""PR #37 PASS B replay at b92f529 -- read-only, isolated journal, Telegram captured not sent.

Clock pinned to 2026-10-06 07:40:00 UTC. Bars are fetched live (read-only copy_rates_from_pos)
and truncated to those CLOSED by the pinned clock; spreads replay the values recorded by the
original PASS B run (07:39:57 UTC). MT5 proxy refuses every order/position/history attribute.
"""
import datetime as dt
import json
import math
import os
import sys

WT = r"D:\AG-pr37-host-acceptance"
sys.path[:0] = [os.path.join(WT, "src"), os.path.join(WT, "scripts", "host")]
OUT = sys.argv[1]
JOURNAL = os.path.join(OUT, "journal")
os.makedirs(JOURNAL, exist_ok=True)
UTC = dt.timezone.utc
PIN = dt.datetime(2026, 10, 6, 7, 40, 0, tzinfo=UTC)
ORIGINAL_SPREAD = {"EURUSD-VIP": 0.00013999999999980695, "GBPUSD-VIP": 0.00014999999999987246,
                   "USDJPY-VIP": 0.015999999999991132}
TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440}

import live_candles_smoke as host  # noqa: E402

ALLOWED = {"initialize", "shutdown", "last_error", "account_info", "terminal_info", "version", "symbol_info",
           "symbol_info_tick", "symbol_select", "copy_rates_from_pos"}
FORBIDDEN_PREFIX = ("order_", "TRADE_ACTION", "positions_", "orders_", "history_")
calls, refused = {}, []


class GuardedMT5:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name.startswith(FORBIDDEN_PREFIX):
            refused.append(name)
            raise PermissionError(f"BROKER_MUTATION_GUARD refused mt5.{name}")
        attr = getattr(self._real, name)
        if callable(attr) and not isinstance(attr, type):
            if name not in ALLOWED:
                refused.append(name)
                raise PermissionError(f"BROKER_MUTATION_GUARD unlisted mt5.{name}")

            def wrapped(*a, **k):
                calls[name] = calls.get(name, 0) + 1
                return attr(*a, **k)
            return wrapped
        return attr


sent = []
host._notify = lambda kind, value, text, root, **kw: sent.append({"kind": kind, "value": value, "text": text}) or "CAPTURED"

real = host.import_mt5()
result = {"pinned_now": PIN.isoformat(), "real_now": dt.datetime.now(UTC).isoformat(), "journal": JOURNAL,
          "MetaTrader5.__file__": getattr(real, "__file__", None) if real else None,
          "MetaTrader5.__version__": getattr(real, "__version__", None) if real else None}
mt5_file = os.path.normcase(os.path.abspath(result["MetaTrader5.__file__"] or ""))
if real is None or mt5_file.startswith(os.path.normcase(WT)) or "site-packages" not in mt5_file:
    result["verdict"] = "STOP_PLACEHOLDER_OR_MISSING_MT5"
    print(json.dumps(result, indent=1, default=str))
    sys.stdout.flush()
    os._exit(3)

mt5 = GuardedMT5(real)
with host.mt5_access_lock():
    ok, err = host.mt5_initialize(mt5, "")
    result["initialize"] = [ok, str(err)]
    if ok:
        try:
            demo_ok, demo_status = host.require_demo_account(mt5)
            ai = mt5.account_info()
            result["account"] = {"server": ai.server, "login_suffix": str(ai.login)[-3:],
                                 "trade_mode": ai.trade_mode, "trade_mode_is_demo": ai.trade_mode == real.ACCOUNT_TRADE_MODE_DEMO,
                                 "demo_ok": demo_ok, "demo_status": str(demo_status)}
            if demo_ok and ai.trade_mode == real.ACCOUNT_TRADE_MODE_DEMO:
                inner = host.host_fetch(mt5)
                live_quote = host.host_quote(mt5)
                lag = dt.datetime.now(UTC) - PIN

                def fetch(symbol, timeframe, count):
                    step = dt.timedelta(minutes=TF_MIN[timeframe])
                    extra = math.ceil(lag / step) + 8
                    bars = [b for b in inner(symbol, timeframe, count + extra) if b.time + step <= PIN]
                    if len(bars) < count:
                        raise RuntimeError(f"REPLAY_HISTORY_SHORT {symbol}/{timeframe} {len(bars)}<{count}")
                    return bars[-count:]

                def quote(symbol):
                    q = live_quote(symbol)
                    if q is None or symbol not in ORIGINAL_SPREAD:
                        return q
                    return q[0], q[0] + ORIGINAL_SPREAD[symbol]

                result["lines"] = host.run_fx(
                    fetch, PIN, JOURNAL, gated=False, notify=True, quote=quote,
                    balance=lambda: host.account_balance(mt5),
                    symbol_meta=lambda broker: host.live_symbol_meta(mt5, broker))
        finally:
            mt5.shutdown()

result.update({"mt5_calls": calls, "mt5_refused": refused,
               "BROKER_MUTATION_COUNT": sum(1 for n in calls if n.startswith(FORBIDDEN_PREFIX)),
               "telegram_captured": [(s["kind"], s["value"], s["text"].splitlines()[0]) for s in sent]})
with open(os.path.join(OUT, "run_result.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, default=str)
print(json.dumps(result, indent=1, default=str))
sys.stdout.flush()
os._exit(0)
