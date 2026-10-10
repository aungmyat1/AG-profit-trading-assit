"""No invented market fixtures: unit policy math and explicit missing-feed rows only."""
import datetime as dt
from pathlib import Path

import pytest

from v1_tickets.authority import ADAPTERS, REPO_ROOT, logic_identity
from v1_tickets.crypto_cfd import build_crypto_cfd_cycle, run_crypto_cfd_windows
from v1_tickets.crypto_cfd_policy import POLICY_PATH, load_ticket_policy
from v1_tickets.manual_ticket import crypto_cfd_commission, crypto_cfd_cost_gate

UTC = dt.timezone.utc


@pytest.mark.parametrize("spread,expected_blocks,expected_warns", [
    (9.99, [], []), (10, [], ["COST_WARN"]),
    (20, [], ["SPREAD_WARN", "COST_WARN"]),
    (20.01, ["SPREAD_TOO_WIDE"], ["COST_WARN"]),
    (25, ["SPREAD_TOO_WIDE", "COST_TOO_HIGH"], []),
])
def test_spread_boundary_percent_of_stop(spread, expected_blocks, expected_warns):
    block, warn, pct, cost = crypto_cfd_cost_gate(100, spread, None, load_ticket_policy())
    assert (block, warn, pct, cost) == (expected_blocks, expected_warns, spread, spread / 100)


def test_commission_absent_is_unknown(tmp_path):
    assert crypto_cfd_commission("BTCUSD", tmp_path) is None
    block, warn, pct, cost = crypto_cfd_cost_gate(100, 10, None, load_ticket_policy())
    assert (pct, cost) == (10, 0.1) and block == [] and "COST_WARN" in warn


@pytest.mark.parametrize("invalid", [
    "strategy_id: ST_CRYPTO_CFD_SWEEP_RETEST_V1\nstrategy_version: 1.0.0\nspread_ok_pct: foo\nspread_block_pct: 20\nrisk_pct: 0.5\ncost_warn_R: 0.1\ncost_block_R: 0.25\n",
    "strategy_id: ST_CRYPTO_CFD_SWEEP_RETEST_V1\nstrategy_version: 1.0.0\nspread_ok_pct: 10\nspread_block_pct: 20\nrisk_pct: nope\ncost_warn_R: 0.1\ncost_block_R: 0.25\n",
    "not: [valid: yaml",
])
def test_missing_or_invalid_policy_blocks(tmp_path, invalid):
    strategy = tmp_path / "config" / "v1_tickets" / "crypto_cfd_ticket_policy.yaml"
    strategy.parent.mkdir(parents=True)
    strategy.write_text(invalid)
    row = build_crypto_cfd_cycle("BTCUSD", dt.datetime(2026, 10, 9, 14, tzinfo=UTC),
                                 feed=None, root=tmp_path)
    assert row["decision"] == "BLOCKED"
    assert set(row["reason_codes"]) & {"SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS"}


@pytest.mark.parametrize("now,name", [
    (dt.datetime(2026, 10, 9, 14, tzinfo=UTC), "WEEKDAY"),
    (dt.datetime(2026, 10, 10, 21, 30, tzinfo=UTC), "WEEKEND"),
])
def test_both_windows_have_terminal_rows_without_feed(now, name, tmp_path):
    rows = run_crypto_cfd_windows(now, feed=None, archive_root=str(tmp_path))
    assert len(rows) == 2
    assert {t["symbol"] for t, _ in rows} == {"BTCUSD", "ETHUSD"}
    for ticket, path in rows:
        assert ticket["cycle"] == name and ticket["decision"] == "DATA_ERROR"
        assert ticket["reason_codes"] == ["FEED_UNAVAILABLE"]
        assert Path(path).is_file()


def test_absent_keys_and_missing_policy_block_both_instruments(tmp_path):
    now = dt.datetime(2026, 10, 10, 21, 30, tzinfo=UTC)
    for symbol in ("BTCUSD", "ETHUSD"):
        absent = build_crypto_cfd_cycle(symbol, now, feed=None, root=tmp_path)
        assert absent["decision"] == "BLOCKED"
        assert absent["reason_codes"] == ["SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS"]
    path = tmp_path / POLICY_PATH
    path.parent.mkdir(parents=True)
    path.write_text("strategy_id: ST_CRYPTO_CFD_SWEEP_RETEST_V1\nstrategy_version: 1.0.0\n"
                    "spread_ok_pct: 10\nspread_block_pct: 20\nrisk_pct: 0.5\ncost_warn_R: 0.1\n")
    row = build_crypto_cfd_cycle("ETHUSD", now, feed=None, root=tmp_path)
    assert row["decision"] == "BLOCKED" and row["reason_codes"] == ["RISK_POLICY_AMBIGUOUS"]


def test_wrong_policy_identity_is_fail_closed(tmp_path):
    path = tmp_path / POLICY_PATH
    path.parent.mkdir(parents=True)
    path.write_text((REPO_ROOT / POLICY_PATH).read_text().replace("strategy_version: 1.0.0", "strategy_version: 9.0.0"))
    assert load_ticket_policy(path)["open_authorities"] == ["SPREAD_POLICY_UNDEFINED", "RISK_POLICY_AMBIGUOUS"]


def test_ticket_policy_is_in_logic_identity(tmp_path):
    strategy = "ST_CRYPTO_CFD_SWEEP_RETEST_V1"
    contract, engine = ADAPTERS[strategy]
    assert POLICY_PATH in engine
    for rel in (contract, *engine):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((REPO_ROOT / rel).read_bytes())
    before = logic_identity(strategy, "1.0.0", tmp_path)
    policy = tmp_path / POLICY_PATH
    policy.write_text(policy.read_text().replace("spread_ok_pct: 10", "spread_ok_pct: 11"))
    after = logic_identity(strategy, "1.0.0", tmp_path)
    assert before["contract_hash"] == after["contract_hash"]
    assert before["engine_identity"] != after["engine_identity"]
    assert before["digest"] != after["digest"]


def test_commission_unavailable_uses_spread_only(tmp_path):
    import json
    path = tmp_path / "status" / "evidence" / "host_symbol_info_ETHUSD.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"symbol": "ETHUSD", "commission_status": "COMMISSION_UNAVAILABLE", "commission_R": 1.0}))
    commission = crypto_cfd_commission("ETHUSD", tmp_path)
    assert commission is None
    _, _, _, cost = crypto_cfd_cost_gate(100, 10, commission, load_ticket_policy())
    assert cost == 0.1
