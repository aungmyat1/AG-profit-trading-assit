import pandas as pd
import pytest

from research.harness.costs import apply_costs, rollover_nights
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


def test_swap_triple_wednesday_and_direction():
    t = pd.Timestamp
    assert rollover_nights(t("2024-01-02T20:00Z"), t("2024-01-02T22:00Z"), 21, 2) == 1
    assert rollover_nights(t("2024-01-03T20:00Z"), t("2024-01-03T22:00Z"), 21, 2) == 3  # Wednesday
    assert rollover_nights(t("2024-01-02T10:00Z"), t("2024-01-02T20:00Z"), 21, 2) == 0
    lg = load_engine_ledger([trade(1, direction="SHORT", entry=1.1, stop=1.101, target=1.098,
                                   entry_time="2024-01-02T20:00:00Z", exit_time="2024-01-02T22:00:00Z")])
    out = apply_costs(lg, cost_model(swap_long_per_night=0.0005, swap_short_per_night=-0.0002))
    assert out.loc[0, "swap_nights"] == 1 and out.loc[0, "swap_R"] == pytest.approx(-0.2)


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
