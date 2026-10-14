"""AGP-C24 addendum: LSMC 1.1.3 L5 per OD1011-L5 -- PASS or INSUFFICIENT; a cost-blocked plan is an
actionability outcome, never an L5 FAIL; missing evidence never PASS."""
import datetime as dt
from types import SimpleNamespace

from v1_tickets.lsmc_v113_logic_gate import (
    INSUFFICIENT,
    NOT_APPLICABLE,
    PASS,
    l5_od1011,
)

NOW = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.timezone.utc)
BINDING = {"value": 0.0, "source": "OD1011-COMMISSION"}


def _sig(entry=100.0, stop=90.0, state="OPPORTUNITY"):
    return SimpleNamespace(state=state, opportunity={"entry_reference": entry, "stop_c10": stop})


def _case(spread=0.5, binding=BINDING, symbol="BTCUSD", close=NOW):
    return {"symbol": symbol, "now": NOW, "cost_evidence": {
        "spread": spread, "spread_bar_close_utc": close.isoformat(), "commission_binding": binding}}


def test_pass_with_accepted_evidence():
    g = l5_od1011(_case(spread=0.5), _sig())
    assert g["status"] == PASS and g["actionability"] == "OK" and g["cost_R"] == 0.05


def test_cost_blocked_plan_is_actionability_not_fail():
    g = l5_od1011(_case(spread=3.0), _sig())          # 0.30R >= 0.25R block, 30% > 20% spread block
    assert g["status"] == PASS and g["actionability"] == "BLOCK"


def test_missing_evidence_is_insufficient():
    assert l5_od1011(_case(binding=None), _sig())["status"] == INSUFFICIENT
    assert l5_od1011(_case(spread=None), _sig())["status"] == INSUFFICIENT
    assert l5_od1011(_case(close=NOW - dt.timedelta(minutes=30)), _sig())["status"] == INSUFFICIENT
    assert l5_od1011(_case(symbol="EURUSD"), _sig())["status"] == INSUFFICIENT


def test_no_priced_opportunity_is_not_applicable():
    assert l5_od1011(_case(), _sig(state="WATCH"))["status"] == NOT_APPLICABLE
    assert l5_od1011(_case(), _sig(stop=None))["status"] == NOT_APPLICABLE
