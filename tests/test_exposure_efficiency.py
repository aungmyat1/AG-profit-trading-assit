import csv
from datetime import datetime, timedelta, timezone

import pytest

from research.exposure_efficiency import Candle, EvidenceError, Trade, entry_population_hash, load_trades, policy_metrics, replay_trade, run

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def trade(side="LONG", **kw):
    base = dict(trade_id="T1", symbol="EURUSD", side=side, entry_time=T0, entry_price=100.0,
                stop_loss=99.0 if side == "LONG" else 101.0, original_exit_time=T0 + timedelta(minutes=150),
                original_exit_price=102.0 if side == "LONG" else 98.0, spread_cost_r=.1,
                commission_cost_r=.05, slippage_cost_r=.05, strategy_id="S", strategy_version="1")
    base.update(kw); return Trade(**base)


def candles(side="LONG", count=180):
    out = []
    for i in range(1, count + 1):
        close = 100 + (i / 60 if side == "LONG" else -i / 60)
        out.append(Candle("EURUSD", T0 + timedelta(minutes=i), 100, max(100, close) + .01, min(100, close) - .01, close))
    return out


def test_long_short_direction_time_stop_and_friction():
    a = replay_trade(trade(), candles(), "30"); b = replay_trade(trade("SHORT"), candles("SHORT"), "30")
    assert a["gross_r"] == pytest.approx(.5); assert b["gross_r"] == pytest.approx(.5)
    assert a["net_r"] == pytest.approx(.3); assert a["exit_reason"] == "TIME_STOP"


def test_stop_precedes_time_stop_and_control_is_original():
    cs = candles(); cs[4] = Candle("EURUSD", T0 + timedelta(minutes=5), 100, 100.1, 98.9, 99)
    assert replay_trade(trade(), cs, "30")["exit_reason"] == "STOP_LOSS"
    control = replay_trade(trade(), cs, "CONTROL")
    assert control["exit_price"] == 102 and control["exit_reason"] == "ORIGINAL_EXIT"


def test_mfe_mae_and_threshold_times():
    cs = [Candle("EURUSD", T0 + timedelta(minutes=i), 100, 100 + i / 30, 99.9, 100 + i / 30) for i in range(1, 181)]
    r = replay_trade(trade(), cs, "120")
    assert r["mfe_r"] >= 4; assert r["mae_r"] < 0
    assert r["time_to_1r_minutes"] == 30; assert r["time_to_2r_minutes"] == 60; assert r["time_to_3r_minutes"] == 90
    assert r["mfe_after_30m"] < r["mfe_after_60m"]


def test_metrics_profit_factor_drawdown_exposure():
    rows = [{"policy":"30", "entry_time":T0.isoformat(), "trade_id":str(i), "net_r":r, "gross_r":r,
             "hold_minutes":60, "spread_cost_r":0, "commission_cost_r":0, "slippage_cost_r":0, "mfe_r":max(r,0), "mae_r":min(r,0)}
            for i, r in enumerate([2.0, -1.0, -1.0])]
    m = policy_metrics(rows)
    assert m["profit_factor"] == 1; assert m["max_drawdown_r"] == 2; assert m["r_per_position_hour"] == 0


def test_fail_closed_validation_and_hash():
    with pytest.raises(EvidenceError, match="coverage"):
        replay_trade(trade(), candles(count=10), "30")
    with pytest.raises(EvidenceError, match="stop distance"):
        replay_trade(trade(stop_loss=100), candles(), "30")
    assert entry_population_hash([trade()]) == entry_population_hash([trade()])


def test_evidence_generation(tmp_path):
    trades = tmp_path / "trades.csv"; bars = tmp_path / "bars.csv"; out = tmp_path / "out"
    with trades.open("w", newline="") as f:
        fields = ["trade_id","symbol","side","entry_time","entry_price","stop_loss","original_exit_time","original_exit_price","take_profit","spread_cost_r","commission_cost_r","slippage_cost_r","strategy_id","strategy_version"]
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerow({**{k:"" for k in fields}, **{"trade_id":"T1","symbol":"EURUSD","side":"LONG","entry_time":T0.isoformat(),"entry_price":100,"stop_loss":99,"original_exit_time":(T0+timedelta(minutes=150)).isoformat(),"original_exit_price":102,"spread_cost_r":.1,"commission_cost_r":.05,"slippage_cost_r":.05,"strategy_id":"S","strategy_version":"1"}})
    with bars.open("w", newline="") as f:
        fields=["symbol","timestamp","open","high","low","close"]; w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for c in candles(): w.writerow({"symbol":c.symbol,"timestamp":c.timestamp.isoformat(),"open":c.open,"high":c.high,"low":c.low,"close":c.close})
    result=run(trades,bars,out)
    assert len(result["metrics"]) == 6
    assert {"experiment_manifest.json","input_manifest.json","policy_results.csv","per_trade_results.csv","exposure_efficiency_results.json","GEN_001_REPORT.md"} <= {p.name for p in out.iterdir()}


def test_timezone_rejection(tmp_path):
    path = tmp_path / "trades.csv"
    fields = ["trade_id","symbol","side","entry_time","entry_price","stop_loss","original_exit_time","original_exit_price","spread_cost_r","commission_cost_r","slippage_cost_r"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        w.writerow({"trade_id":"T1","symbol":"EURUSD","side":"LONG","entry_time":"2026-01-01T00:00:00","entry_price":100,"stop_loss":99,"original_exit_time":"2026-01-01T01:00:00+00:00","original_exit_price":101,"spread_cost_r":0,"commission_cost_r":0,"slippage_cost_r":0})
    with pytest.raises(EvidenceError, match="timezone-aware"):
        load_trades(path)
