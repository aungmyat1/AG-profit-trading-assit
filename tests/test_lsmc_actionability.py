"""Operational gates on synthetic opportunities; no broker/Telegram contact."""
import json
import subprocess
import types
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml

from host_delivery import telegram_message as tg
from large_smc_watch import watch as W


def opportunity(direction="LONG", **changes):
    return {"opp_id": "setup", "poi_id": "poi", "direction": direction,
            "entry_reference": 100.0, "stop_c10": 99.0 if direction == "LONG" else 101.0,
            "target_c11": 101.0 if direction == "LONG" else 99.0,
            "stop_reason": None, "target_reason": None,
            "expires_at": "2026-01-06T11:00:00+00:00", **changes}


def snapshot(**changes):
    return W.Snapshot("EURUSD", "2026-01-06T09:30:00+00:00", "OPPORTUNITY",
                      reason_codes=("D30_BADGE_ECONOMICS_NOT_EVALUATED",),
                      opportunity=opportunity(**changes))


@pytest.mark.parametrize("changes,reason", [
    ({"stop_c10": None}, "REJECT_NO_STOP"),
    ({"stop_c10": 100.0}, "REJECT_NO_STOP"),
    ({"stop_c10": 101.0}, "REJECT_NO_STOP"),
    ({"stop_c10": float("nan")}, "REJECT_NO_STOP"),
    ({"stop_reason": "C10_PIP_SIZE_NOT_EVIDENCED"}, "REJECT_NO_STOP"),
    ({"target_c11": None}, "REJECT_NO_TARGET"),
    ({"target_c11": 100.0}, "REJECT_NO_TARGET"),
    ({"target_c11": 99.0}, "REJECT_NO_TARGET"),
    ({"target_c11": float("inf")}, "REJECT_NO_TARGET"),
    ({"target_reason": "REJECT_NO_TARGET"}, "REJECT_NO_TARGET"),
])
def test_incomplete_or_invalid_levels_rejected(changes, reason):
    original = snapshot(**changes)
    result = W.gate_opportunity(original, 100.25)
    assert result.state == "REJECTED" and result.reason_codes[0] == reason
    assert result.opportunity == original.opportunity  # never manufacture levels


@pytest.mark.parametrize("direction,price,accepted", [
    ("LONG", 100.5, True), ("LONG", 100.5001, False), ("LONG", 101.0, False),
    ("SHORT", 99.5, True), ("SHORT", 99.4999, False), ("SHORT", 99.0, False),
    ("LONG", 99.0, False), ("SHORT", 101.0, False), ("LONG", None, False),
    ("LONG", float("nan"), False),
])
def test_remaining_reward_boundary_and_direction(direction, price, accepted):
    original = snapshot(direction=direction)
    result = W.gate_opportunity(original, price)
    if accepted:
        assert result is original
    else:
        assert result.state == "REJECTED" and result.reason_codes[0] == "REJECT_STALE"


@pytest.mark.parametrize("value", [None, True, "0.5", -0.1, 0, 1.1, float("nan")])
def test_missing_or_invalid_policy_fails_closed(tmp_path, value):
    path = tmp_path / "config/local/actionability_policy.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({"lsmc_min_remaining_reward_fraction": value}))
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) == "REJECT_STALE"


def test_missing_file_key_and_malformed_local_policy_fail_closed(tmp_path):
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) == "REJECT_STALE"
    tracked = tmp_path / "config/policy/actionability_policy.yaml"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("lsmc_min_remaining_reward_fraction: 0.5")
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) == "REJECT_STALE"
    local = tmp_path / "config/local/actionability_policy.yaml"
    local.parent.mkdir()
    local.write_text("{}")
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) == "REJECT_STALE"
    local.write_text("lsmc_min_remaining_reward_fraction: 0.5")
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) is None
    local.write_text("[")
    assert W.opportunity_rejection(opportunity(), 100.25, root=tmp_path) == "REJECT_STALE"


def test_rejected_transition_archived_suppressed_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(tg, "load_mode", lambda root: {"mode": tg.MESSAGE_DELIVERY,
                                                      "scopes": tg.SCOPES})
    tracker = W.WatchTracker(str(tmp_path / "state.json"), str(tmp_path / "archive"))
    rejected = W.gate_opportunity(snapshot(target_c11=None), 100.25)
    event, = tracker.poll(rejected)
    assert (event.to_state, event.alert_level) == ("REJECTED", "INFO")
    assert event.payload["reason_codes"][0] == "REJECT_NO_TARGET"
    assert not tg.should_send("LSMC", event.alert_level)
    text = tg.format_alert(asdict(event), price=100.25)
    assert "LARGE-SMC REJECTION" in text and "REJECT_NO_TARGET" in text
    assert tracker.poll(rejected) == []
    restarted = W.WatchTracker(str(tmp_path / "state.json"), str(tmp_path / "archive"))
    assert restarted.poll(rejected) == []
    assert len(list((tmp_path / "archive").rglob("*.json"))) == 1


def test_complete_fresh_opportunity_and_sent_text_byte_exact(tmp_path, monkeypatch):
    # R:R = 1.0: no authorized R:R minimum, so this must remain eligible.
    original = snapshot()
    before = json.dumps(asdict(original), sort_keys=True).encode()
    accepted = W.gate_opportunity(original, 100.25)
    assert accepted is original and json.dumps(asdict(accepted), sort_keys=True).encode() == before
    event = W.AlertEvent("transition", "EURUSD", None, "OPPORTUNITY", "OPPORTUNITY", "setup",
                         original.evaluated_at, "2026-01-06", payload={"opportunity": original.opportunity})
    monkeypatch.setattr(tg, "_normalizer", lambda *args: None)
    monkeypatch.setattr(tg, "load_mode", lambda root: {"mode": tg.MESSAGE_DELIVERY,
                                                      "scopes": tg.SCOPES})
    text = tg.format_alert(asdict(event), price=100.25)
    # Re-check the unchanged golden against the formatter on the rebase target main.
    main_sha = "d8ee56a17795aea064b9741f98cbe3fdb00383a3"
    source = subprocess.run(["git", "show", f"{main_sha}:src/host_delivery/telegram_message.py"],
                            check=True, capture_output=True, text=True).stdout
    baseline = types.ModuleType("host_delivery._main_formatter")
    baseline.__file__ = tg.__file__
    baseline.__package__ = "host_delivery"
    exec(compile(source, baseline.__file__, "exec"), baseline.__dict__)
    monkeypatch.setattr(baseline, "_normalizer", lambda *args: None)
    monkeypatch.setattr(baseline, "load_mode", tg.load_mode)
    main_text = baseline.format_alert(asdict(event), price=100.25)
    golden = Path(__file__).parent / "fixtures/lsmc_complete_alert.txt"
    assert main_text.encode() == golden.read_bytes()
    assert text.encode() == main_text.encode()
    assert tg.should_send("LSMC", event.alert_level)
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True}
    class Transport:
        def post(self, url, **kwargs):
            sent.append(kwargs["data"]["text"])
            return Response()
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TEST")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "TEST")
    tg.send_message(text, session=Transport())
    assert sent[0].encode() == golden.read_bytes()


def test_defensive_formatter_never_labels_raw_stale_event_opportunity(monkeypatch):
    monkeypatch.setattr(tg, "_normalizer", lambda *args: None)
    e = W.AlertEvent("t", "EURUSD", None, "OPPORTUNITY", "OPPORTUNITY", "setup",
                     snapshot().evaluated_at, "2026-01-06", payload={"opportunity": opportunity()})
    text = tg.format_alert(asdict(e), price=100.75)
    assert "REJECTED (INFO)" in text and "REJECT_STALE" in text and "OPPORTUNITY" not in text


def test_snapshot_pipeline_preserves_valid_detection_bytes(monkeypatch):
    from _lsmc_v110_fixtures import NOW, d1_bars, h1_bars, m5_bars
    monkeypatch.setattr(W.C, "resolve_point", lambda symbol: (0.00001, "HOST_CAPTURED"))
    monkeypatch.setattr(W, "c11_causal_target", lambda *args: 1.12)
    gate = W.gate_opportunity
    monkeypatch.setattr(W, "gate_opportunity", lambda snap, price: snap)
    raw = W.evaluate_snapshot("EURUSD", d1_bars(), h1_bars(), m5_bars(), NOW)
    monkeypatch.setattr(W, "gate_opportunity", gate)
    valid = W.evaluate_snapshot("EURUSD", d1_bars(), h1_bars(), m5_bars(), NOW)
    assert valid.state == "OPPORTUNITY"
    assert json.dumps(asdict(raw), sort_keys=True).encode() == json.dumps(asdict(valid), sort_keys=True).encode()
