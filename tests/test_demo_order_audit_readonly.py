"""Pure classification of the read-only DEMO order audit (no MT5)."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "host"))
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts" / "host" / "demo_order_audit_readonly.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

S1 = 777001
HOST = {0: "manual", 112201: "Crypto_VBO_EA"}


def deal(ticket, order, pos, typ, entry, magic=0, comment="", t=1_700_000_000, profit=0.0):
    return NS(ticket=ticket, order=order, position_id=pos, symbol="GBPUSD-VIP", type=typ, entry=entry,
              reason=3, volume=0.1, price=1.3, profit=profit, commission=-0.5, swap=0.0, magic=magic,
              comment=comment, time=t)


def horder(ticket, state, magic=0, comment="", t=1_700_000_000):
    return NS(ticket=ticket, symbol="GBPUSD-VIP", type=0, state=state, magic=magic, comment=comment,
              time_setup=t)


def run(**kw):
    base = dict(positions=[], orders=[], hist_orders=[], hist_deals=[], s1_magic=S1, host_magics=HOST, offset_s=10800)
    base.update(kw)
    return audit.classify(**base)


def test_empty_history_is_no_demo_orders():
    r = run()
    assert audit.verdict(r, history_complete=True) == "NO_DEMO_ORDERS_CONFIRMED"
    assert audit.verdict(r, history_complete=False) == "HISTORY_INCOMPLETE"


def test_foreign_closed_trade_is_not_attributed_to_ag():
    r = run(hist_orders=[horder(11, 4), horder(12, 4)],
            hist_deals=[deal(21, 11, 11, 0, 0), deal(22, 12, 11, 1, 1, profit=5.0), deal(23, 0, 0, 2, 0)])
    assert r["counts"]["closed_trades"] == 1 and r["counts"]["non_trade_deals"] == {"BALANCE": 1}
    assert r["closed_trades"][0]["owner"] == "FOREIGN" and r["closed_trades"][0]["net_profit"] == 4.0
    assert audit.verdict(r, True) == "NO_DEMO_ORDERS_CONFIRMED"


def test_ag_attribution_by_magic_or_comment():
    r = run(hist_orders=[horder(31, 4, magic=S1), horder(32, 5, comment="AG 0123456789abcdef")],
            hist_deals=[deal(41, 31, 31, 0, 0, magic=S1)])
    ag = r["ag_profit_trading"]["counts"]
    assert ag["executed_deals"] == 1 and ag["rejected_orders"] == 1
    assert audit.verdict(r, True) == "DEMO_ORDERS_FOUND"
    assert r["ag_profit_trading"]["first_broker_confirmed"]["utc"].endswith("Z")


def test_filled_order_without_deal_and_request_state_are_uncertain():
    r = run(hist_orders=[horder(51, 4), horder(52, 7)])
    states = sorted(u["state"] for u in r["uncertain"])
    assert states == ["FILLED_WITHOUT_DEAL", "REQUEST_ADD"]


def test_comment_must_match_adapter_format():
    assert audit.attribute(0, "AG manual note", S1, HOST)["owner"] == "FOREIGN"
    assert audit.attribute(5, "", S1, HOST)["foreign_source"] == "UNREGISTERED_MAGIC"
