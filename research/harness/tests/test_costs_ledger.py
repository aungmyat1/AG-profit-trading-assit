import pandas as pd
import pytest

from research.harness.costs import CostModel, SymbolCosts, apply_costs, rollover_nights
from research.harness.ledger import load_engine_ledger
from research.harness.tests.fixtures import cost_model, trade


def test_itemized_columns_and_net():
    lg = load_engine_ledger([trade(1, reason="TARGET"), trade(2, reason="STOP")])
    cm = cost_model(spread=0.0001, commission=0.00007, slippage_per_side=0.00002, stop_extra_slippage=0.0001)
    out = apply_costs(lg, cm).set_index("trade_id")
    assert out.loc["T1", "gross_R"] == pytest.approx(2.0) and out.loc["T2", "gross_R"] == pytest.approx(-1.0)
    assert out.loc["T1", "spread_R"] == pytest.approx(0.1)
    assert out.loc["T1", "commission_R"] == pytest.approx(0.07)
    assert out.loc["T1", "slippage_R"] == pytest.approx(0.04)
    assert out.loc["T2", "slippage_R"] == pytest.approx(0.14)  # stop exits pay extra slippage
    assert out.loc["T1", "swap_R"] == 0.0
    assert out.loc["T1", "net_R"] == pytest.approx(2.0 - 0.21)
    assert apply_costs(lg, cm, 2.0).set_index("trade_id").loc["T1", "total_cost_R"] == pytest.approx(0.42)


def test_summer_rollover_is_2100_utc():  # EDT: 17:00 New York = 21:00 UTC
    t = pd.Timestamp
    assert rollover_nights(t("2024-07-02T20:30Z"), t("2024-07-02T21:30Z"), 3) == 1
    assert rollover_nights(t("2024-07-02T21:30Z"), t("2024-07-02T22:30Z"), 3) == 0


def test_winter_rollover_is_2200_utc():  # EST: 17:00 New York = 22:00 UTC
    t = pd.Timestamp
    assert rollover_nights(t("2024-01-09T20:30Z"), t("2024-01-09T21:30Z"), 3) == 0
    assert rollover_nights(t("2024-01-09T21:30Z"), t("2024-01-09T22:30Z"), 3) == 1


def test_non_wednesday_triple_day_from_input():
    t = pd.Timestamp
    fri, wed = ("2024-01-12T21:30Z", "2024-01-12T22:30Z"), ("2024-01-10T21:30Z", "2024-01-10T22:30Z")
    assert rollover_nights(t(fri[0]), t(fri[1]), 5) == 3   # MT5 5 = Friday
    assert rollover_nights(t(wed[0]), t(wed[1]), 5) == 1
    assert rollover_nights(t(wed[0]), t(wed[1]), 3) == 3   # MT5 3 = Wednesday
    lg = load_engine_ledger([trade(1, direction="SHORT", entry=1.1, stop=1.101, target=1.098,
                                   entry_time=fri[0].replace("Z", ":00Z"), exit_time=fri[1].replace("Z", ":00Z"))])
    out = apply_costs(lg, cost_model(swap_short_per_night=-0.0002, swap_rollover3days=5))
    assert out.loc[0, "swap_nights"] == 3 and out.loc[0, "swap_R"] == pytest.approx(-0.6)


def test_missing_triple_day_refused():
    lg = load_engine_ledger([trade(1)])
    with pytest.raises(KeyError, match="swap_rollover3days"):
        apply_costs(lg, CostModel(per_symbol={"EURUSD": SymbolCosts()}))


def test_missing_symbol_costs_refused():
    lg = load_engine_ledger([trade(1, symbol="USDJPY", entry=150.0, stop=149.9, target=150.2)])
    with pytest.raises(KeyError, match="refusing to assume zero"):
        apply_costs(lg, cost_model())


@pytest.mark.parametrize("mutate,msg", [
    (lambda r: r.pop("strategy_version"), "missing required"),
    (lambda r: r.update(stop_price=1.2), "loss side"),
    (lambda r: r.update(direction="BUY"), "direction"),
    (lambda r: r.update(entry_time="2024-01-02T00:00:00"), "naive"),
])
def test_ledger_rejects_non_canonical_rows(mutate, msg):
    r = trade(1)
    mutate(r)
    with pytest.raises(ValueError, match=msg):
        load_engine_ledger([r])
