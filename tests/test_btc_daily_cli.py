from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path


UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def _load_cli():
    path = ROOT / "scripts" / "run_btc_daily_report.py"
    spec = importlib.util.spec_from_file_location("run_btc_daily_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_rejects_outside_report_window_before_network(capsys):
    cli = _load_cli()
    rc = cli.main([], clock=lambda: dt.datetime(2026, 1, 6, 6, 29, tzinfo=UTC))
    assert rc == 2
    assert "BTC_DAILY_REPORT_WINDOW_BEFORE_WINDOW" in capsys.readouterr().err


def test_diagnostic_mode_requires_no_archive(capsys):
    cli = _load_cli()
    rc = cli.main(
        ["--allow-outside-window"],
        clock=lambda: dt.datetime(2026, 1, 6, 1, 0, tzinfo=UTC),
    )
    assert rc == 2
    assert "requires --no-archive" in capsys.readouterr().err


def test_in_window_builds_and_archives_previous_utc_day(monkeypatch, capsys):
    cli = _load_cli()
    now = dt.datetime(2026, 1, 6, 6, 35, tzinfo=UTC)
    captured = {}

    class _Feed:
        pass

    class _Meta:
        pass

    monkeypatch.setattr(cli, "fetch_exchange_symbol_meta", lambda symbol: _Meta())
    monkeypatch.setattr(cli, "to_symbol_meta", lambda meta: "NORMALIZED_META")
    monkeypatch.setattr(cli, "BybitLinearPerpFeed", _Feed)

    def _build(feed, observation_date, **kwargs):
        captured["date"] = observation_date
        captured["now"] = kwargs["now"]
        return {
            "observation_date": observation_date.isoformat(), "decision": "NO_TRADE",
            "data_quality": {"status": "PASS"}, "reason_codes": ["NO_SETUP"],
            "proposal_count": 0, "occurrences": [],
        }

    monkeypatch.setattr(cli, "build_btc_daily_report", _build)
    monkeypatch.setattr(cli, "archive_btc_daily_report", lambda date, report: "archive.json")

    rc = cli.main(["--json"], clock=lambda: now)
    output = capsys.readouterr()
    assert rc == 0
    assert captured["date"] == dt.date(2026, 1, 5)
    assert captured["now"] == now
    assert '"qualification_evidence_eligible": true' in output.out
    assert "archive.json" in output.err


def test_diagnostic_uses_disposable_runtime_state(monkeypatch, capsys):
    cli = _load_cli()
    now = dt.datetime(2026, 1, 6, 1, 0, tzinfo=UTC)

    class _Meta:
        pass

    monkeypatch.setattr(cli, "fetch_exchange_symbol_meta", lambda symbol: _Meta())
    monkeypatch.setattr(cli, "to_symbol_meta", lambda meta: "NORMALIZED_META")
    monkeypatch.setattr(cli, "BybitLinearPerpFeed", lambda: object())

    def _build(feed, observation_date, **kwargs):
        assert kwargs["runtime"] is not None
        assert kwargs["ledger"] is not None
        assert kwargs["daily_loss_guard"] is not None
        assert kwargs["open_position_guard"] is not None
        return {
            "observation_date": observation_date.isoformat(), "decision": "NO_TRADE",
            "data_quality": {"status": "PASS"}, "reason_codes": [],
            "proposal_count": 0, "occurrences": [],
        }

    monkeypatch.setattr(cli, "build_btc_daily_report", _build)
    rc = cli.main(
        ["--allow-outside-window", "--no-archive"], clock=lambda: now,
    )
    assert rc == 0
    assert "qualification_evidence_eligible" not in capsys.readouterr().err


def test_cli_source_has_no_order_or_private_api_path():
    source = (ROOT / "scripts" / "run_btc_daily_report.py").read_text(encoding="utf-8")
    forbidden = (
        "execution.executor", "execution.coordinator", "mt5.management_gateway",
        "order_send", "order_check", "/v5/order", "/v5/account", "api_key",
    )
    assert not any(term in source for term in forbidden)


def test_cli_import_does_not_contaminate_stdout(capsys):
    _load_cli()
    assert capsys.readouterr().out == ""
