"""Manual Trade Ticket V1 host-acceptance integration fixes: sizing-metadata authority order (I3)
and the legacy-informational vs manual-ticket Telegram separation (I4). Offline, no MT5."""
from __future__ import annotations

import datetime as dt

from mt5.symbol_resolver import SymbolMeta
from host_delivery import telegram_message as tg
from v1_tickets import manual_ticket as mt

from test_manual_ticket_build import META, OWNER, READY_DAY, l2_pass, manual  # noqa: F401  (fixture re-export)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 6, 7, 30, tzinfo=UTC)


def test_live_symbol_info_is_preferred_over_the_captured_snapshot():
    meta, prov = mt.resolve_symbol_meta("EURUSD", META, NOW)
    assert meta is META and prov == {"source": mt.META_LIVE, "broker_symbol": "EURUSD-VIP"}


def test_live_meta_for_the_wrong_broker_symbol_is_not_trusted(monkeypatch, tmp_path):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "none"))
    wrong = SymbolMeta(**{**META.__dict__, "symbol": "EURUSD"})         # non -VIP symbol
    meta, prov = mt.resolve_symbol_meta("EURUSD", wrong, NOW)
    assert meta is None and prov["source"] == mt.META_NONE


def test_captured_snapshot_is_an_explicit_fallback_with_provenance_and_age():
    meta, prov = mt.resolve_symbol_meta("EURUSD", None, NOW)               # repo host capture exists
    assert meta is not None and meta.symbol == "EURUSD-VIP"
    assert prov["source"] == mt.META_CAPTURE_FALLBACK and prov["captured_at"] and prov["live_unavailable"] is True
    assert isinstance(prov["capture_age_h"], int) and prov["capture_age_h"] >= 0


def test_no_live_and_no_capture_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("AG_EVIDENCE_ROOT", str(tmp_path / "none"))
    meta, prov = mt.resolve_symbol_meta("EURUSD", None, NOW)
    assert meta is None and prov["source"] == mt.META_NONE
    assert mt.lot_size(1.1, 1.099, OWNER, 1000.0, meta)["status"] == "SYMBOL_METADATA_MISSING"


def test_ticket_exposes_sizing_metadata_provenance(l2_pass):  # noqa: F811
    prov = {"source": mt.META_CAPTURE_FALLBACK, "broker_symbol": "EURUSD-VIP",
            "captured_at": "2026-09-30T08:37:24+00:00", "capture_age_h": 143, "live_unavailable": True}
    t = manual(READY_DAY, "07:20", owner=OWNER, balance=10000.0, meta=META, meta_provenance=prov)
    assert t["state"] == "TICKET_READY" and t["risk"]["symbol_meta"] == prov
    assert "SIZED FROM CAPTURED METADATA 2026-09-30T08:37:24+00:00, age 143 h" in mt.render_text(t)


def test_legacy_ready_and_manual_blocked_are_distinguishable():
    t = manual()                                                          # real v1.1.1: L2 fails
    assert t["state"] == "TICKET_BLOCKED" and t["stop_reason"] == "LOGIC_GATE_FAIL:L2"
    assert t["legacy_informational_decision"] == t["decision"]
    assert t["legacy_informational_ready"] is (t["decision"] == "READY")


def test_manual_ticket_telegram_scope_cannot_widen_tracked_policy(tmp_path):
    (tmp_path / "config" / "local").mkdir(parents=True)
    override = tmp_path / "config" / "local" / "delivery_override.yaml"
    override.write_text("mode: MESSAGE_DELIVERY\nscopes: [TICKET_READY]\n")
    r = str(tmp_path)
    assert tg.should_send("TICKET", "READY", r)                            # legacy informational unchanged
    assert not tg.should_send(tg.MANUAL_TICKET, tg.MANUAL_TICKET_READY, r)  # legacy scope never sends manual
    assert not tg.should_send("TICKET", tg.MANUAL_TICKET_READY, r)
    override.write_text("mode: MESSAGE_DELIVERY\nscopes: [MANUAL_TICKET_READY]\n")
    assert tg.load_mode(r)["error"] == "SCOPE_WIDENING_REJECTED"
    assert not tg.should_send(tg.MANUAL_TICKET, tg.MANUAL_TICKET_READY, r)
    assert not tg.should_send("TICKET", "READY", r)                        # manual scope never sends legacy
    assert tg.SCOPES == ("TICKET_READY", "LSMC_OPPORTUNITY")              # legacy surface pin unchanged
