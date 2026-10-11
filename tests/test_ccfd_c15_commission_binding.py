"""C15: OD1011 commission binding must fail closed outside the captured VT demo server."""
from scripts.ccfd_sweep_retest_replay import commission_binding, l5_od1011, INSUFFICIENT


def test_commission_requires_matching_server_and_source():
    policy = {"server": "VTMarkets-Demo", "source": "MT5_VT_MARKETS_DEMO"}
    binding = commission_binding(policy)
    assert binding is not None
    assert binding["value"] == 0.0
    assert binding["source"] == "OD1011-COMMISSION"


def test_missing_or_foreign_server_fails_closed():
    for server in (None, "", "OTHER-DEMO", "VTMarkets-Live"):
        assert commission_binding({"server": server, "source": "MT5_VT_MARKETS_DEMO"}) is None
    assert commission_binding({"server": "VTMarkets-Demo", "source": "OTHER_SOURCE"}) is None
    assert commission_binding({}) is None


def test_l5_insufficient_without_bound_commission():
    result = l5_od1011(spread=1.0, risk=10.0, ticket={}, policy={}, binding=None)
    assert result["status"] == INSUFFICIENT
    assert result["reason"] == "COMMISSION_EVIDENCE_MISSING"
