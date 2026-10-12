"""OD1012 run identity: every record of a scheduled run carries the scheduled binding's identity
(strategy, version, contract SHA256), whether the candle read succeeds or fails; and every host
run logs the terminal/account it attached to (suffix only)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "host"))
sys.path.insert(0, str(REPO / "tests"))

import _host_common as hc  # noqa: E402
import canonical_fx_delivery as cfd  # noqa: E402
from test_canonical_fx_delivery import NOW, signal_provider  # noqa: E402

import v1_tickets.daily_evaluator as de  # noqa: E402
from ticket_store.adapter import evaluation_from_canonical  # noqa: E402
from v1_tickets import fx as v1_fx  # noqa: E402

BINDING_SHA = hashlib.sha256((REPO / v1_fx.SCOPED_CANDIDATE_PATH).read_bytes()).hexdigest()


def _identity(result, source):
    record = evaluation_from_canonical(result.canonical, source=source)
    return (result.canonical["strategy_id"], result.canonical["strategy_version"], record["spec_sha256"])


def _failing(*_):
    raise cfd.HostAcquisitionFailure("DATA_MISSING", "copy_rates returned None")


def test_failing_run_carries_same_identity_as_succeeding_run(tmp_path):
    ok = de.evaluate_fx_pair("GBPUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(), candle_provider=signal_provider(),
                             archive_root=str(tmp_path / "ok"), ticket_source="LIVE")
    bad = de.evaluate_fx_pair("GBPUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(), candle_provider=_failing,
                              archive_root=str(tmp_path / "bad"), ticket_source="LIVE")
    assert bad.canonical["reason_code"] != ok.canonical["reason_code"]   # one failed, one evaluated
    assert _identity(bad, "LIVE") == _identity(ok, "LIVE") == ("ST_ASIAN_SWEEP_5R_V1", "1.1.2", BINDING_SHA)


@pytest.mark.parametrize("provider", [_failing, lambda *_: None])
def test_canonical_host_failure_run_carries_scheduled_binding(tmp_path, provider):
    # Host prerequisite failures run labelled REPLAY (no live data) but belong to the LIVE binding.
    results = de.run_daily_evaluation(now=NOW, day=NOW.date(), candle_provider=provider,
                                      archive_root=str(tmp_path), include_crypto=False, policy_root=str(REPO),
                                      ticket_source="REPLAY", cycles=("ASIAN_LONDON",),
                                      strategy_path=v1_fx.SCOPED_CANDIDATE_PATH)
    assert results and {_identity(r, "REPLAY") for r in results} == {
        ("ST_ASIAN_SWEEP_5R_V1", "1.1.2", BINDING_SHA)}


def test_out_of_scope_block_carries_binding_identity(tmp_path):
    r = de.evaluate_fx_pair("EURUSD", "ASIAN_LONDON", now=NOW, day=NOW.date(), candle_provider=_failing,
                            archive_root=str(tmp_path), ticket_source="LIVE")
    assert _identity(r, "LIVE") == ("ST_ASIAN_SWEEP_5R_V1", "1.1.2", BINDING_SHA)


def test_canonical_failure_lines_pass_scheduled_binding():
    import inspect

    import live_candles_smoke as smoke
    src = inspect.getsource(smoke._main)
    block = src[src.index("def canonical_failure_lines"):src.index("def lsmc_failure_lines")]
    assert "strategy_path=fx_tickets.SCOPED_CANDIDATE_PATH" in block


class _MT5:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self, path="C:\\Program Files\\VT Markets MT5 Terminal", login=1234999):
        self._path, self._login = path, login

    def terminal_info(self):
        return SimpleNamespace(path=self._path)

    def account_info(self):
        return SimpleNamespace(server="VTMarkets-Demo", login=self._login, trade_mode=0)


@pytest.mark.parametrize("requested,ok", [
    ("", True),                                                               # auto-detect: no path pin
    ("C:\\Program Files\\VT Markets MT5 Terminal\\terminal64.exe", True),
    ("c:/program files/vt markets mt5 terminal/", True),
    ("C:\\Program Files\\MetaTrader 5\\terminal64.exe", False),               # another terminal attached
])
def test_requested_terminal_path_is_honoured(monkeypatch, requested, ok):
    monkeypatch.delenv("MT5_TERMINAL_PATH", raising=False)
    got = hc.require_pinned_demo_account(_MT5(), terminal_path=requested)
    assert got == ((True, "ACCOUNT_PIN_VERIFIED") if ok else (False, "ACCOUNT_PIN_MISMATCH TERMINAL_PATH"))
    if requested:
        monkeypatch.setenv("MT5_TERMINAL_PATH", requested)                    # env alone is honoured too
        assert hc.require_pinned_demo_account(_MT5()) == got


def test_run_identity_is_suffix_only_and_never_raises(monkeypatch):
    monkeypatch.delenv("MT5_TERMINAL_PATH", raising=False)
    ident = hc.run_identity(_MT5(login=7654985))
    assert ident == {"requested_terminal_path": "AUTO", "terminal_path": "C:\\Program Files\\VT Markets MT5 Terminal",
                     "server": "VTMarkets-Demo", "login_suffix": "985"}
    assert "7654985" not in hc.format_run_identity(ident)
    broken = SimpleNamespace(terminal_info=lambda: 1 / 0, account_info=lambda: 1 / 0)
    assert set(hc.run_identity(broken).values()) == {"AUTO", "NOT_AVAILABLE"}
    assert hc.run_identity(None, "D:/mt5/terminal64.exe")["requested_terminal_path"] == "D:/mt5/terminal64.exe"
