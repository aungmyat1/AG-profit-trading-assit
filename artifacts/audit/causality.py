"""Causality / look-ahead probe.

Protocol (Phase 3): for each cut index T, compute features on the truncated
series bars[0:T+1] ("knowable at T") and on the full series, then compare the
row at index T. If the full-series value differs from the truncated value, the
feature at T depends on bars after T -> look-ahead / repaint.
"""
import warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from smartmoneyconcepts import smc

rng = np.random.default_rng(7)
n = 400
close = 1.1 + np.cumsum(rng.normal(0, 0.0007, n))
high = close + np.abs(rng.normal(0, 0.0005, n))
low = close - np.abs(rng.normal(0, 0.0005, n))
op = np.r_[close[0], close[:-1]]
idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
df = pd.DataFrame({"open": op, "high": high, "low": low, "close": close,
                   "volume": rng.integers(100, 1000, n).astype(float)}, index=idx)

def swings(d, l=5):
    return smc.swing_highs_lows(d, swing_length=l)

FEATURES = {
    "swing_highs_lows": lambda d: swings(d),
    "bos_choch":        lambda d: smc.bos_choch(d, swings(d), close_break=True),
    "fvg":              lambda d: smc.fvg(d, join_consecutive=False),
    "ob":               lambda d: smc.ob(d, swings(d)),
    "liquidity":        lambda d: smc.liquidity(d, swings(d), range_percent=0.01),
    "previous_high_low":lambda d: smc.previous_high_low(d, time_frame="1h"),
    "retracements":     lambda d: smc.retracements(d, swings(d)),
}

full = {}
for name, fn in FEATURES.items():
    try:
        full[name] = fn(df).reset_index(drop=True)
    except Exception as e:
        full[name] = e

cuts = list(range(150, 380, 7))
report = {}
for name, fn in FEATURES.items():
    if isinstance(full[name], Exception):
        report[name] = {"error": repr(full[name])}; continue
    fullres = full[name]
    cols = list(fullres.columns)
    mismatch = {c: 0 for c in cols}
    first_stable_lag = {c: None for c in cols}
    checked = 0
    for T in cuts:
        try:
            trunc = fn(df.iloc[:T+1]).reset_index(drop=True)
        except Exception:
            continue
        checked += 1
        for c in cols:
            a = fullres[c].iloc[T]; b = trunc[c].iloc[T]
            same = (pd.isna(a) and pd.isna(b)) or (a == b)
            if not same:
                mismatch[c] += 1
    # settle-lag: how many extra bars are needed until value at T equals final value
    lag = {c: None for c in cols}
    for c in cols:
        worst = 0
        for T in cuts[:20]:
            k = None
            for extra in range(0, 40):
                if T+extra >= n: break
                try:
                    tr = fn(df.iloc[:T+extra+1]).reset_index(drop=True)
                except Exception:
                    continue
                a = fullres[c].iloc[T]; b = tr[c].iloc[T]
                if (pd.isna(a) and pd.isna(b)) or (a == b):
                    k = extra; break
            if k is None: k = 99
            worst = max(worst, k)
        lag[c] = worst
    report[name] = {"cuts_checked": checked, "mismatch_counts": mismatch,
                    "max_settle_lag_bars": lag}

print(json.dumps(report, indent=2, default=str))
