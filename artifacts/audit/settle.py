"""When does the feature value for BAR i become FINAL (== full-series value)?
settle_lag(i) = min k >= 0 such that computing on bars[0:i+k+1] yields the
full-series value for bar i AND it never changes again."""
import warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from smartmoneyconcepts import smc
import pandas_ta_classic as ta

rng = np.random.default_rng(11); n = 300
close = 1.1 + np.cumsum(rng.normal(0, 0.0007, n))
high = close + np.abs(rng.normal(0, 0.0005, n)); low = close - np.abs(rng.normal(0, 0.0005, n))
df = pd.DataFrame({"open": np.r_[close[0], close[:-1]], "high": high, "low": low,
                   "close": close, "volume": rng.integers(100,1000,n).astype(float)},
                  index=pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"))
SL = 5
def sw(d): return smc.swing_highs_lows(d, swing_length=SL)
FE = {
 "swing_highs_lows": lambda d: sw(d),
 "bos_choch": lambda d: smc.bos_choch(d, sw(d), close_break=True),
 "fvg": lambda d: smc.fvg(d),
 "ob": lambda d: smc.ob(d, sw(d)),
 "liquidity": lambda d: smc.liquidity(d, sw(d), range_percent=0.01),
}
MAXK = 25
bars = list(range(120, 200, 4))
out = {}
for name, fn in FE.items():
    fullr = fn(df).reset_index(drop=True)
    cols = list(fullr.columns)
    lags = {c: [] for c in cols}
    for i in bars:
        series = {}
        for k in range(0, MAXK+1):
            if i+k >= n: break
            r = fn(df.iloc[:i+k+1]).reset_index(drop=True)
            series[k] = {c: r[c].iloc[i] for c in cols}
        for c in cols:
            fv = fullr[c].iloc[i]
            settle = None
            ks = sorted(series)
            for k in ks:
                v = series[k][c]
                eq = (pd.isna(fv) and pd.isna(v)) or (v == fv)
                if eq and all(((pd.isna(fv) and pd.isna(series[k2][c])) or series[k2][c]==fv) for k2 in ks if k2>=k):
                    settle = k; break
            lags[c].append(MAXK+1 if settle is None else settle)
    out[name] = {c: {"max_settle_lag": max(v), "median": int(np.median(v))} for c,v in lags.items()}

# pandas-ta-classic indicator causality
res = {}
for label, f in {
  "ema14": lambda d: ta.ema(d["close"], length=14),
  "atr14_rma": lambda d: ta.atr(d["high"], d["low"], d["close"], length=14),
  "atr14_sma": lambda d: ta.atr(d["high"], d["low"], d["close"], length=14, mamode="sma"),
  "stdev20": lambda d: ta.stdev(d["close"], length=20),
  "bbands20": lambda d: ta.bbands(d["close"], length=20).iloc[:,0],
  "true_range": lambda d: ta.true_range(d["high"], d["low"], d["close"]),
}.items():
    fullv = f(df).reset_index(drop=True)
    bad = 0; drift = 0.0
    for T in range(120, 290, 5):
        tv = f(df.iloc[:T+1]).reset_index(drop=True).iloc[T]
        fv = fullv.iloc[T]
        if pd.isna(fv) and pd.isna(tv): continue
        d_ = abs(float(fv)-float(tv))
        drift = max(drift, d_)
        if d_ > 1e-12: bad += 1
    res[label] = {"mismatches_vs_truncated": bad, "max_abs_drift": drift}
print(json.dumps({"smc_settle_lags_bars": out, "pandas_ta_classic_causality": res}, indent=2, default=str))
