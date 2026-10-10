"""Host policy, bad archive and archive ownership tests; fake transport only."""
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/host"))

import canonical_fx_delivery as cfd  # noqa: E402
import live_candles_smoke as runner  # noqa: E402
from test_canonical_fx_delivery import NOW, sender  # noqa: E402

from large_smc_watch.watch import Snapshot, WatchTracker  # noqa: E402


def policy(root, text):
    path = root / "config/local/actionability_policy.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("text", [None, "{}", "[", "lsmc_min_remaining_reward_fraction: null",
                                  "lsmc_min_remaining_reward_fraction: true",
                                  "lsmc_min_remaining_reward_fraction: 1.1"])
def test_read_only_preflight_names_missing_key_and_fails(tmp_path, text):
    path = policy(tmp_path, text) if text is not None else None
    before = path.read_bytes() if path else None
    before_tree = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/host/preflight_actionability.py"),
                             "--root", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "LSMC_CONFIG_MISSING key=lsmc_min_remaining_reward_fraction" in result.stdout
    assert (path.read_bytes() if path else None) == before
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before_tree


def test_preflight_passes_without_importing_broker_or_strategy(tmp_path, monkeypatch, capsys):
    path = policy(tmp_path, "lsmc_min_remaining_reward_fraction: 0.5")
    spec = importlib.util.spec_from_file_location("preflight_actionability", ROOT / "scripts/host/preflight_actionability.py")
    module = importlib.util.module_from_spec(spec)
    import builtins
    original = builtins.__import__

    def forbidden_import(name, *args, **kwargs):
        assert not name.startswith(("MetaTrader5", "mt5", "large_smc_watch", "strategy_engine"))
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbidden_import)
    before = path.read_bytes()
    spec.loader.exec_module(module)
    assert module.main(["--root", str(tmp_path)]) == 0
    assert "PASS lsmc_min_remaining_reward_fraction=0.5" in capsys.readouterr().out
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode", ["fx", "crypto", "lsmc", "lsmc-weekend"])
def test_config_missing_logged_once_per_runner_invocation(tmp_path, monkeypatch, mode):
    from v1_tickets import crypto
    policy(tmp_path, "{}")
    logs = []
    monkeypatch.setattr(runner, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(runner, "log_line", lambda name, line: logs.append((name, line)))

    class StopBeforeBroker(Exception):
        pass

    def stop(*args, **kwargs):
        raise StopBeforeBroker

    monkeypatch.setattr(crypto, "load_ticket_config", stop)
    with pytest.raises(StopBeforeBroker):
        runner.main(["--mode", mode])
    assert logs == [(f"ag_v1_{mode}", "LSMC_CONFIG_MISSING key=lsmc_min_remaining_reward_fraction")]


def rejected_archive(journal, symbol, reason, at, identity):
    tracker = WatchTracker(str(journal / f"{identity}.json"), str(journal / "ticket_delivery/archive"))
    event, = tracker.poll(Snapshot(symbol, at.isoformat(), "REJECTED", reason_codes=(reason,),
                                  opportunity={"opp_id": identity, "poi_id": "test"}))
    return event


@pytest.mark.parametrize("bad", ["{", "{}", '{"strategy_id":"ST_LARGE_SMC_V1","payload":null}',
                                 '{"strategy_id":"ST_LARGE_SMC_V1","payload":{"to_state":"REJECTED"}}'])
def test_bad_file_skipped_good_rejection_retained_and_summary_sends(tmp_path, monkeypatch, bad):
    journal = tmp_path / "journal"
    monkeypatch.setattr(cfd, "POLICY_ROOT", tmp_path)
    policy(tmp_path, "{}")
    rejected_archive(journal, "EURUSD", "REJECT_NO_STOP", NOW.replace(hour=8), "good")
    path = journal / "ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/GBPUSD/LSMC_WATCH-bad/2026/2026-10-07.json"
    path.parent.mkdir(parents=True)
    path.write_text(bad)
    send, calls = sender(tmp_path, enabled=True)
    summary = cfd.build_session_summary(str(journal), session_date=NOW.date(), session="ASIAN_LONDON", sender=send)
    assert summary["large_smc"]["rejection_counts"]["REJECT_NO_STOP"] == 1
    assert summary["large_smc"]["archive_error_count"] == 1
    assert send.send_session_summary(summary) == "sent"
    assert "ARCHIVE_ERROR n=1" in calls[-1][1]
    assert "CONFIG_MISSING key=lsmc_min_remaining_reward_fraction" in calls[-1][1]
    assert "LSMC_WATCH-bad" not in calls[-1][1]


def test_archived_crypto_inside_fx_window_has_one_crypto_owner(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    monkeypatch.setattr(cfd, "POLICY_ROOT", tmp_path)
    policy(tmp_path, "lsmc_min_remaining_reward_fraction: 0.5")
    at = NOW.replace(hour=8)
    for symbol, reason in [("BTCUSD", "REJECT_NO_STOP"), ("ETHUSD", "REJECT_NO_TARGET")]:
        rejected_archive(journal, symbol, reason, at, symbol)
    # The tested source is the real archive path, with no crypto evaluation journal.
    paths = list((journal / "ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1").rglob("*.json"))
    assert len(paths) == 2
    assert not (journal / "ticket_delivery/canonical_fx/sessions").exists()
    record = json.loads(paths[0].read_text())
    assert record["symbol"] in ("BTCUSD", "ETHUSD")
    paths[0].with_name("2026-10-08.json").write_bytes(paths[0].read_bytes())
    paths[0].with_name("2026-10-07.correction-001.json").write_text("{")
    send, calls = sender(tmp_path, enabled=True)
    for cycle in cfd.V1_CYCLES:
        fx = cfd.build_session_summary(str(journal), session_date=NOW.date(), session=cycle, sender=send)
        assert set(fx["large_smc"]["rejection_counts"].values()) == {0}
        assert fx["large_smc"]["archive_error_count"] == 0
        assert not {"BTCUSD", "ETHUSD"} & set(fx["expected_instruments"])
    assert set(cfd.lsmc_rejection_counts(str(journal), at - dt.timedelta(hours=1),
                                       at + dt.timedelta(hours=1)).values()) == {0}
    window = (at.replace(hour=0, minute=0, second=0), at.replace(hour=0, minute=0, second=0) + dt.timedelta(days=1))
    crypto = cfd.build_lsmc_crypto_summary(str(journal), session_date=NOW.date(),
                                          session=cfd.LSMC_CRYPTO_DAY, window=window, sender=send)
    assert crypto["rejection_counts"] == {"REJECT_NO_STOP": 1, "REJECT_NO_TARGET": 1}
    # A matching evaluation journal must not count the same archived transition again.
    for symbol, reason in [("BTCUSD", "REJECT_NO_STOP"), ("ETHUSD", "REJECT_NO_TARGET")]:
        cfd.record_lsmc_crypto_evaluation(str(journal), now=at, session=cfd.LSMC_CRYPTO_DAY,
                                         symbol=symbol, state="REJECTED", reason_codes=[reason], deliveries=[])
    again = cfd.build_lsmc_crypto_summary(str(journal), session_date=NOW.date(),
                                         session=cfd.LSMC_CRYPTO_DAY, window=window, sender=send)
    assert again["rejection_counts"] == crypto["rejection_counts"]
    assert send.send_session_summary(again) == "sent"
    assert "CONFIG_MISSING" not in calls[-1][1] and "ARCHIVE_ERROR" not in calls[-1][1]


def test_crypto_summary_reports_config_and_archive_errors_and_sends(tmp_path, monkeypatch):
    monkeypatch.setattr(cfd, "POLICY_ROOT", tmp_path)
    journal = tmp_path / "journal"
    path = journal / "ticket_delivery/archive/fx_ticket_archive/ST_LARGE_SMC_V1/BTCUSD/LSMC_WATCH-bad/2026/2026-10-07.json"
    path.parent.mkdir(parents=True)
    path.write_text("{")
    send, calls = sender(tmp_path, enabled=True)
    summary = cfd.build_lsmc_crypto_summary(str(journal), session_date=NOW.date(), session=cfd.LSMC_CRYPTO_DAY,
                                           window=(NOW.replace(hour=0), NOW.replace(hour=23)), sender=send)
    assert send.send_session_summary(summary) == "sent"
    assert "CONFIG_MISSING key=lsmc_min_remaining_reward_fraction" in calls[-1][1]
    assert "ARCHIVE_ERROR n=1" in calls[-1][1]
