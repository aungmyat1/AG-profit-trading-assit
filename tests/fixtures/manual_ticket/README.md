# Manual Trade Ticket V1 logic-gate fixtures

`EURUSD_M15_recorded.csv` is an unmodified excerpt (OHLC columns, 00:00-16:00 UTC) of
`data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/raw/EURUSD_M15.csv`
for 2026-06-15, 2026-06-16, 2026-06-17, 2026-06-23 and 2026-07-17. Used only to replay
the frozen `ST_ASIAN_SWEEP_5R_V1@1.1.1` engine offline for logic verification (no
performance claim, no research evidence). Engine branches on these dates (ASIAN_LONDON):
NO_SETUP, TREND, SWEEP LONG, SWEEP SHORT, SWEEP SHORT with zero stop distance.
