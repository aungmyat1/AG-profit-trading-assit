"""D6 hotfix (owner decision 2026-10-07): ST_ASIAN_SWEEP_5R_V1 READY authority OFF.

Every test here requests `production_ready_authority`, so it runs against the real
config/v1_tickets/ready_authority.yaml (tests/conftest.py switches READY ON only for tests written
before D6). The engine is stubbed to return a SIGNAL that the gates would pass as READY: the
switch must still prevent any READY, on the legacy ticket and on the manual ticket.
"""
from __future__ import annotations

import datetime as dt
import types

import pytest

from host_delivery import telegram_message as tg
from strategy_engine.session import Candle
from v1_tickets import fx as fx_tickets
from v1_tickets import manual_ticket
from v1_tickets import ready_authority as ra
from v1_tickets.paper import paper_eligibility
from v1_tickets.scan_record import TICKET_BLOCKED, TICKET_READY, classify_fx_ticket

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 7)
AT = dt.datetime(2026, 10, 7, 7, 16, 8, tzinfo=UTC)          # the 2026-10-07 07:16 READY slot


@pytest.fixture
def engine_signal(monkeypatch):
    sig = types.SimpleNamespace(status="SIGNAL", reason_code="BOX_DIRECTION_V1", regime="RANGE", setup="entry_1",
                                signal_id="s1", box_high=1.1720, box_low=1.1660, box_mid=1.1690,
                                # engine bar time (STALE-FIX-1): keeps this stub on the READY-authority path
                                signal_timestamp=dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), direction="LONG", entry=1.1665, stop_loss=1.16515,
                                risk_distance=0.00135)
    monkeypatch.setattr(fx_tickets, "evaluate", lambda *a, **k: sig)
    return sig


def _build(symbol="EURUSD", cycle="ASIAN_LONDON"):
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
    return fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                      evaluated_at=AT, data_close=AT, spread=0.00015)


def test_production_config_turns_asian_sweep_ready_authority_off(production_ready_authority):
    assert production_ready_authority.replace("\\", "/").endswith("config/v1_tickets/ready_authority.yaml")
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1") == (False, "READY_AUTHORITY_OFF_D6")


def test_no_ready_ticket_is_emitted_and_shadow_is_clearly_labelled(production_ready_authority, engine_signal):
    t = _build()
    assert t["decision"] == ra.SHADOW_INFO_ONLY != "READY"
    assert (t["suppressed_decision"], t["reason_code"], t["engine_reason_code"]) == (
        "READY", "READY_AUTHORITY_OFF_D6", "BOX_DIRECTION_V1")
    assert t["label"].startswith("SHADOW / INFO ONLY") and "NOT ACTIONABLE" in t["label"]
    assert (t["entry"], t["stop_loss"], t["direction"]) == (1.1665, 1.16515, "LONG")    # levels kept for audit
    assert t["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1"
    # downstream: archived as NO_TRADE, no paper trade, never in the Telegram READY scope
    assert fx_tickets._STATE[t["decision"]] == fx_tickets.CYCLE_STATE_NO_TRADE
    eligible, reasons, _ = paper_eligibility(t, AT)
    assert not eligible and "DECISION_NOT_READY" in reasons
    state, _stage, reason = classify_fx_ticket(t, now=AT, window_end=AT + dt.timedelta(hours=3))
    assert (state, reason) == (TICKET_BLOCKED, "READY_AUTHORITY_OFF_D6")


def test_telegram_ticket_scope_never_carries_the_shadow_decision(tmp_path, production_ready_authority):
    (tmp_path / "config" / "local").mkdir(parents=True)
    (tmp_path / "config" / "local" / "delivery_override.yaml").write_text(
        "mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY, LSMC_OPPORTUNITY]\n")
    assert tg.should_send("TICKET", "READY", str(tmp_path))
    assert not tg.should_send("TICKET", ra.SHADOW_INFO_ONLY, str(tmp_path))


@pytest.mark.parametrize("symbol", fx_tickets.V1_FX_SYMBOLS)
@pytest.mark.parametrize("cycle", fx_tickets.V1_CYCLES)
def test_no_symbol_or_cycle_can_emit_ready(production_ready_authority, engine_signal, symbol, cycle):
    windows = fx_tickets.session_windows_utc(DAY)[cycle]
    at = windows["trade"][0] + dt.timedelta(minutes=16)
    bar = Candle(windows["trade"][0], 1.1665, 1.1670, 1.1660, 1.1666)
    t = fx_tickets.build_fx_ticket(symbol, cycle, DAY, [], 2, [bar], data_source="MT5_VT_MARKETS_DEMO",
                                   evaluated_at=at, data_close=at, spread=0.00015)
    assert t["decision"] != "READY"


def test_manual_ticket_cannot_reach_ticket_ready(production_ready_authority, engine_signal):
    bar = Candle(dt.datetime(2026, 10, 7, 7, 0, tzinfo=UTC), 1.1665, 1.1670, 1.1660, 1.1666)
    m = manual_ticket.build_manual_ticket("EURUSD", "ASIAN_LONDON", DAY, [], 2, [bar], now=AT, data_close=AT,
                                          spread=0.00015, owner=manual_ticket.load_owner_config(), balance=10000.0, commission_r=0.0)
    assert m["state"] != TICKET_READY and m["legacy_informational_ready"] is False
    assert m["legacy_informational_decision"] == ra.SHADOW_INFO_ONLY


def test_switch_fails_closed_and_only_explicit_on_restores_ready(tmp_path):
    missing = str(tmp_path / "absent.yaml")
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1", missing) == (False, ra.READY_AUTHORITY_UNREADABLE)
    bad = tmp_path / "bad.yaml"
    bad.write_text("strategies: [not, a, mapping]\n")
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1", str(bad))[0] is False
    other = tmp_path / "other.yaml"
    other.write_text("strategies:\n  ST_ASIAN_SWEEP_5R_V1:\n    ready: MAYBE\n")
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1", str(other))[0] is False
    on = tmp_path / "on.yaml"
    on.write_text("strategies:\n  ST_ASIAN_SWEEP_5R_V1:\n    ready: 'ON'\n")
    assert ra.ready_authority("ST_ASIAN_SWEEP_5R_V1", str(on), strategy_version="1.1.2",
                              contract_sha256="a" * 64, symbol="EURUSD", session="ASIAN_LONDON",
                              owner_register_path=missing) == (False, ra.OWNER_DECISION_RECORD_MISSING)
    assert ra.ready_authority("SOME_OTHER_STRATEGY", str(on))[0] is False
    # A symbol verified for its version in strategies/registry.yaml (per-symbol gate, see
    # test_d6_per_symbol_verification.py); with D6 ON it stays READY.
    ready = {"decision": "READY", "strategy_id": "ST_ASIAN_SWEEP_5R_V1", "reason_code": "X",
             "strategy_version": "1.1.2", "symbol": "EURUSD"}
    assert ra.apply_ready_authority(ready, str(on))["reason_code"] == ra.OWNER_DECISION_RECORD_MISSING
    assert ra.apply_ready_authority(ready, missing)["decision"] == ra.SHADOW_INFO_ONLY
    no_trade = {"decision": "NO_TRADE", "strategy_id": "ST_ASIAN_SWEEP_5R_V1"}
    assert ra.apply_ready_authority(no_trade, missing) is no_trade                 # only READY is affected
