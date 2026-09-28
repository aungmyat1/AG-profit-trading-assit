"""FX discovery V1 semantic parity harness (research only; run in an ISOLATED venv).

Runs the same deterministic candle fixtures through:
  AG canonical (src/fx_discovery/features.py), the AG session sweep rule
  (strategy_engine.session.setups.entry_2_sweep), smart-money-concepts, smc-mcp's pure
  smc subpackage, and pandas-ta-classic (ATR/EMA).
The OSS packages are loaded from pinned local clones and never installed into the
project. smc-mcp's MCP server / yfinance data module is never imported.

    SMC_SRC=<clone>/smart-money-concepts SMC_MCP_SRC=<clone>/smc-mcp/src \
      <isolated-venv>/python scripts/research/fx_discovery_parity_harness.py > report.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.environ["SMC_SRC"])
_pkg = types.ModuleType("smc_mcp")
_pkg.__path__ = [os.path.join(os.environ["SMC_MCP_SRC"], "smc_mcp")]
sys.modules["smc_mcp"] = _pkg

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pandas_ta_classic as ta  # noqa: E402
from smartmoneyconcepts.smc import smc as JSMC  # noqa: E402
from smc_mcp.smc import detect_structure, find_fair_value_gaps, find_liquidity_sweeps, find_swings  # noqa: E402

from fx_discovery import features as AG  # noqa: E402
from strategy_engine.session import Candle, build_reference_box  # noqa: E402
from strategy_engine.session.setups import entry_2_sweep  # noqa: E402

K = 2
T0 = dt.datetime(2025, 5, 5, tzinfo=dt.timezone.utc)


def mk(ohlc):
    return [Candle(time=T0 + dt.timedelta(minutes=15 * i), open=o, high=h, low=l, close=c)
            for i, (o, h, l, c) in enumerate(ohlc)]


def flat(p, n):
    return [(p, p + 2, p - 2, p)] * n


FIX = {
    "swing_high": flat(100, 3) + [(100, 105, 99, 104), (104, 110, 103, 106), (106, 107, 101, 102), (102, 103, 98, 99)] + flat(99, 3),
    "swing_low": flat(100, 3) + [(100, 101, 95, 96), (96, 97, 90, 94), (94, 99, 93, 98), (98, 102, 97, 101)] + flat(101, 3),
    "equal_highs": flat(100, 3) + [(100, 110, 99, 105), (105, 106, 100, 101), (101, 110, 100, 104), (104, 105, 98, 99)] + flat(99, 3),
    "wick_sweep": flat(100, 3) + [(100, 101, 95, 96), (96, 97, 90, 94), (94, 99, 93, 98), (98, 102, 97, 101), (101, 102, 99, 100),
                                  (100, 101, 88, 95)] + flat(96, 2),
    "close_through": flat(100, 3) + [(100, 101, 95, 96), (96, 97, 90, 94), (94, 99, 93, 98), (98, 102, 97, 101), (101, 102, 99, 100),
                                     (100, 101, 86, 87)] + flat(87, 2),
    "bos_up": flat(100, 2) + [(100, 104, 99, 103), (103, 108, 102, 104), (104, 105, 100, 101), (101, 103, 99, 102),
                              (102, 112, 101, 111), (111, 115, 110, 112), (112, 113, 107, 108), (108, 110, 106, 109),
                              (109, 120, 108, 119)] + flat(119, 2),
    "choch_down": flat(100, 2) + [(100, 104, 99, 103), (103, 108, 102, 104), (104, 105, 100, 101), (101, 103, 99, 102),
                                  (102, 112, 101, 111), (111, 115, 110, 112), (112, 113, 104, 105), (105, 109, 103, 108),
                                  (108, 109, 104, 106), (106, 107, 95, 96)] + flat(96, 2),
    "fvg_bull": flat(100, 3) + [(100, 101, 99, 100.5), (100.5, 108, 100.5, 107.5), (107.5, 110, 103, 109)] + flat(109, 3),
    "incomplete_forming": flat(100, 4) + [(100, 105, 99, 104), (104, 110, 103, 106), (106, 107, 101, 102)],
    "unconfirmed_swing_sweep": flat(100, 3) + [(100, 101, 95, 96), (96, 97, 90, 94), (94, 99, 89, 98)] + flat(98, 3),
}


def ag(bars):
    sw = AG.swings(bars, K)
    return {
        "swings": [(s.index, s.known_at, s.kind, s.price) for s in sw],
        "breaks": [(b.index, b.event, b.direction, b.level) for b in AG.structure_breaks(bars, sw)],
        "sweeps": [(s.index, s.direction, s.level) for s in AG.sweeps(bars, sw)],
        "fvg": [(f.index, f.known_at, f.direction, f.top, f.bottom) for f in AG.fvgs(bars)],
    }


def mcp(bars):
    h, l, c = [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
    sw = find_swings(h, l, K)
    ev, _ = detect_structure(c, sw, K)
    return {
        "swings": [(s.index, s.index + K, s.kind, s.price) for s in sw],
        "breaks": [(e.index, e.event, e.direction, e.price) for e in ev],
        "sweeps": [(s.index, s.kind, s.swept_level) for s in find_liquidity_sweeps(h, l, c, sw)],
        "fvg": [(f.index, f.index + 1, f.kind, f.top, f.bottom) for f in find_fair_value_gaps(h, l)],
    }


def jsmc(bars):
    df = pd.DataFrame({"open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars],
                       "close": [b.close for b in bars], "volume": [1.0] * len(bars)})
    shl = JSMC.swing_highs_lows(df, swing_length=K)
    bc = JSMC.bos_choch(df, shl, close_break=True)
    liq = JSMC.liquidity(df, shl)
    fv = JSMC.fvg(df)
    rows = lambda frame, col: [int(i) for i in np.where(~np.isnan(frame[col].to_numpy(dtype=float)) & (frame[col].to_numpy(dtype=float) != 0))[0]]
    return {
        "swings": [(i, None, "high" if shl["HighLow"][i] == 1 else "low", float(shl["Level"][i])) for i in rows(shl, "HighLow")],
        "breaks": [(i, "BOS" if bc["BOS"][i] else "CHoCH", "bullish" if (bc["BOS"][i] or bc["CHOCH"][i]) > 0 else "bearish",
                    float(bc["Level"][i]), None if np.isnan(bc["BrokenIndex"][i]) else int(bc["BrokenIndex"][i]))
                   for i in sorted(set(rows(bc, "BOS")) | set(rows(bc, "CHOCH")))],
        "liquidity": [(i, int(liq["Liquidity"][i]), float(liq["Level"][i])) for i in rows(liq, "Liquidity")],
        "fvg": [(i, "bullish" if fv["FVG"][i] > 0 else "bearish", float(fv["Top"][i]), float(fv["Bottom"][i])) for i in rows(fv, "FVG")],
    }


def ag_session_sweep(bars):
    """AG's own session-box sweep rule, with the first 7 bars as the reference box."""
    ref, post = bars[:7], bars[7:]
    box = build_reference_box("fixture", ref, len(ref))
    d = entry_2_sweep("FIXTURE", "EURUSD", box, T0.date(), post)
    return {"status": d.decision_status.value, "reason": d.reason_code,
            "at_index": None if d.signal_timestamp is None else 7 + next(i for i, b in enumerate(post) if b.time == d.signal_timestamp)}


def future_mutation():
    base = mk(FIX["bos_up"])
    cut = 9
    mutated = base[:cut + 1] + [Candle(time=b.time, open=b.open * 3, high=b.high * 3, low=b.low * 0.1, close=b.close * 2)
                                for b in base[cut + 1:]]
    def known(res):
        return {"swings": [s for s in res["swings"] if s[1] is not None and s[1] <= cut],
                "breaks": [b for b in res["breaks"] if b[0] <= cut]}
    out = {"AG": known(ag(base)) == known(ag(mutated)), "smc_mcp": known(mcp(base)) == known(mcp(mutated))}
    jb, jm = jsmc(base), jsmc(mutated)
    out["smart_money_concepts"] = ([s for s in jb["swings"] if s[0] <= cut] == [s for s in jm["swings"] if s[0] <= cut])
    return out


def indicators():
    rng = np.random.default_rng(7)
    closes = 1.1 + np.cumsum(rng.normal(0, 0.0005, 300))
    highs = closes + rng.uniform(0.0001, 0.0008, 300)
    lows = closes - rng.uniform(0.0001, 0.0008, 300)
    bars = [Candle(time=T0 + dt.timedelta(minutes=15 * i), open=float(closes[i - 1] if i else closes[0]),
                   high=float(highs[i]), low=float(lows[i]), close=float(closes[i])) for i in range(300)]
    ag_atr, ag_ema = AG.atr(bars, 14), AG.ema([b.close for b in bars], 50)
    ta_atr = ta.atr(pd.Series(highs), pd.Series(lows), pd.Series(closes), length=14)
    ta_ema = ta.ema(pd.Series(closes), length=50)
    def diff(a, b, start):
        pairs = [(x, y) for x, y in zip(a[start:], b.tolist()[start:]) if x is not None and not np.isnan(y)]
        return max(abs(x - y) for x, y in pairs) if pairs else None
    return {"atr14_maxabs_diff_from_bar_14": diff(ag_atr, ta_atr, 14), "atr14_maxabs_diff_after_150": diff(ag_atr, ta_atr, 150),
            "ema50_maxabs_diff_from_bar_49": diff(ag_ema, ta_ema, 49), "atr_typical_value": float(np.nanmedian(ta_atr))}


def main():
    report = {"k": K, "fixtures": {}}
    for name, ohlc in FIX.items():
        bars = mk(ohlc)
        report["fixtures"][name] = {"AG": ag(bars), "smc_mcp": mcp(bars), "smart_money_concepts": jsmc(bars)}
    report["fixtures"]["wick_sweep"]["AG_session_sweep"] = ag_session_sweep(mk(FIX["wick_sweep"]))
    report["fixtures"]["close_through"]["AG_session_sweep"] = ag_session_sweep(mk(FIX["close_through"]))
    report["future_mutation_prefix_stable"] = future_mutation()
    report["indicators_vs_pandas_ta_classic"] = indicators()
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
