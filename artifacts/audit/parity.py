import warnings, json, sys; warnings.filterwarnings("ignore")
sys.path.insert(0,"/home/user/AG-profit-trading-assit")
import numpy as np, pandas as pd, pandas_ta_classic as ta
from research_external.semantic.wilder_atr import wilder_atr

rng=np.random.default_rng(3); n=250
c=1.1+np.cumsum(rng.normal(0,7e-4,n)); h=c+abs(rng.normal(0,5e-4,n)); l=c-abs(rng.normal(0,5e-4,n))
df=pd.DataFrame({"open":np.r_[c[0],c[:-1]],"high":h,"low":l,"close":c})
candles=[{"high":r.high,"low":r.low,"close":r.close} for r in df.itertuples()]
ag=wilder_atr(candles,14)
oss=ta.atr(df["high"],df["low"],df["close"],length=14,mamode="rma")
rows=[]
for i in (13,14,15,20,50,120,249):
    rows.append({"i":i,"AG":ag[i],"OSS_rma":None if pd.isna(oss.iloc[i]) else float(oss.iloc[i]),
                 "abs_diff":None if (ag[i] is None or pd.isna(oss.iloc[i])) else abs(ag[i]-float(oss.iloc[i]))})
tail=[abs(ag[i]-float(oss.iloc[i])) for i in range(60,n) if ag[i] is not None and not pd.isna(oss.iloc[i])]
# warmup / start-truncation sensitivity (history-length dependence of recursive MAs)
sens={}
for label,f in {"ema14":lambda d: ta.ema(d["close"],14),
                "atr14_rma":lambda d: ta.atr(d["high"],d["low"],d["close"],14),
                "sma14":lambda d: ta.sma(d["close"],14)}.items():
    full=f(df).reset_index(drop=True)
    diffs=[]
    for start in (0,10,40,100):
        sub=f(df.iloc[start:].reset_index(drop=True)).reset_index(drop=True)
        v=abs(float(full.iloc[249])-float(sub.iloc[249-start]))
        diffs.append({"warmup_start":start,"abs_diff_at_last_bar":v})
    sens[label]=diffs
# negative offset = explicit look-ahead switch
neg=ta.ema(df["close"],14,offset=-2).reset_index(drop=True)
base=ta.ema(df["close"],14).reset_index(drop=True)
lookahead_via_offset=bool(abs(float(neg.iloc[100])-float(base.iloc[102]))<1e-12)
print(json.dumps({"atr_parity_samples":rows,"atr_max_abs_diff_i>=60":max(tail),
 "recursive_warmup_sensitivity":sens,
 "negative_offset_injects_future_values":lookahead_via_offset}, indent=2, default=str))
