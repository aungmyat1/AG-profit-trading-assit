"""AGP-TKT-HOST-R1 steps 2a + 4: read-only risk snapshot build and USDJPY/XAUUSD symbol/spread capture.

Runs against the worktree given by --root. The MT5 module is wrapped in an allowlist proxy: only
read calls pass; anything else (order_check/order_send/...) raises and is recorded.
"""
import argparse, dataclasses, datetime as dt, json, os, subprocess, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True)
ap.add_argument("--out-dir", required=True)
ap.add_argument("--part", choices=["risk", "spread"], required=True)
args = ap.parse_args()
ROOT = Path(args.root).resolve()
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts" / "host")]

from _host_common import import_mt5, mt5_access_lock, mt5_initialize, require_pinned_demo_account
from demo_execution import risk_snapshot as RS
from demo_execution.scope import load_scope_policies
from mt5.mt5_candles_readonly import default_symbol_map

ALLOWED = {"initialize", "shutdown", "account_info", "terminal_info", "history_deals_get",
           "positions_get", "symbol_info", "symbol_select", "copy_rates_range", "copy_rates_from_pos",
           "last_error", "symbol_info_tick", "version"}
CONSTS = lambda n: n.isupper()


class ReadOnly:
    def __init__(self, mt5):
        self._m, self.calls, self.refused = mt5, [], []

    def __getattr__(self, name):
        if CONSTS(name):
            return getattr(self._m, name)
        if name not in ALLOWED:
            self.refused.append(name)
            raise PermissionError(f"READ_ONLY_PROXY_REFUSED:{name}")
        self.calls.append(name)
        return getattr(self._m, name)


def plain(o):
    if dataclasses.is_dataclass(o):
        return {k: plain(v) for k, v in dataclasses.asdict(o).items()}
    if isinstance(o, dict):
        return {str(k): plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [plain(v) for v in o]
    return o if isinstance(o, (int, float, str, bool, type(None))) else str(o)


out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
terminal = os.environ["MT5_TERMINAL_PATH"]
real = import_mt5()
mt5 = ReadOnly(real)
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
with mt5_access_lock():
    ok, _ = mt5_initialize(mt5, terminal)
    if not ok:
        raise SystemExit("MT5_INITIALIZE_FAILED")
    try:
        pinned, _ = require_pinned_demo_account(mt5, root=str(ROOT), terminal_path=terminal)
        acct = mt5.account_info()
        ident = {"server": acct.server, "login_suffix": str(acct.login)[-3:],
                 "trade_mode": acct.trade_mode, "pinned_demo": bool(pinned)}
        now = dt.datetime.now(dt.timezone.utc)

        rs, cap = {}, {"symbols": {}}
        if args.part == "risk":
          rs = {"evaluated_at_utc": now.isoformat(), "code_sha": sha, "account": ident}
          if not pinned or acct.trade_mode != 0:
              rs["status"] = "SKIPPED_ACCOUNT_PIN_OR_NOT_DEMO"
          else:
              scopes = load_scope_policies(repo_root=ROOT)
              meta = json.loads((ROOT / "config/symbol_metadata/host_captured/GBPUSD.json").read_text())
              build = RS.build_risk_snapshots(mt5, list(scopes), metadata=meta, now_utc=now)
              rs["scopes"] = [RS.scope_key(s) for s in scopes]
              rs["build"] = plain(build)
          rs["mt5_calls"], rs["refused_calls"] = sorted(set(mt5.calls)), mt5.refused
          rs["order_api_calls"] = 0
          (out / "risk_snapshot.json").write_text(json.dumps(rs, indent=2) + "\n")

        if args.part == "spread":
          smap = default_symbol_map()
          cap = {"captured_at_utc": now.isoformat(), "code_sha": sha, "account": ident,
                 "source": "MT5_VT_MARKETS_DEMO", "window": "last 5 server days, M15 bars", "symbols": {}}
          start = now - dt.timedelta(days=7)
          for canon in ("USDJPY", "XAUUSD"):
              broker = smap.get(canon, canon) if isinstance(smap, dict) else canon
              info = mt5.symbol_info(broker)
              entry = {"broker_symbol": broker}
              if info is None:
                  entry["status"] = "SYMBOL_INFO_UNAVAILABLE"
              else:
                  d = info._asdict()
                  entry["symbol_info"] = {k: d.get(k) for k in (
                      "digits", "point", "spread", "spread_float", "trade_contract_size", "trade_tick_size",
                      "trade_tick_value", "trade_tick_value_loss", "volume_min", "volume_step", "volume_max",
                      "trade_stops_level", "trade_freeze_level", "trade_mode", "trade_calc_mode",
                      "currency_base", "currency_profit", "currency_margin", "swap_long", "swap_short")}
                  rates = mt5.copy_rates_range(broker, real.TIMEFRAME_M15, start, now)
                  if rates is None or len(rates) == 0:
                      entry["status"] = "RATES_UNAVAILABLE"
                  else:
                      days = {}
                      for r in rates:
                          day = dt.datetime.fromtimestamp(int(r["time"]), dt.timezone.utc).date().isoformat()
                          days.setdefault(day, []).append(int(r["spread"]))
                      keep = sorted(days)[-5:]
                      entry["spread_points_by_server_day"] = {
                          k: {"bars": len(days[k]), "min": min(days[k]), "median": sorted(days[k])[len(days[k]) // 2],
                              "p95": sorted(days[k])[int(0.95 * (len(days[k]) - 1))], "max": max(days[k])}
                          for k in keep}
                      entry["status"] = "OK"
              cap["symbols"][canon] = entry
          cap["mt5_calls"], cap["refused_calls"] = sorted(set(mt5.calls)), mt5.refused
          (out / "asw_l5_symbol_spread_capture.json").write_text(json.dumps(cap, indent=2) + "\n")
    finally:
        real.shutdown()
print(json.dumps({"risk_snapshot": rs.get("build", {}).get("status", rs.get("status")),
                  "capture": {k: v["status"] for k, v in cap["symbols"].items()},
                  "refused": mt5.refused}))
