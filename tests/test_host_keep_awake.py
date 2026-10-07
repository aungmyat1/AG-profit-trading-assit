"""Keep-awake during active host runs (owner decision 2026-10-07): SetThreadExecutionState
(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) held only while a session window or watch run is active,
always released afterwards. Uses a fake setter: no real power state is touched."""
from __future__ import annotations

import datetime as dt
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "host"))

import _host_common as hc  # noqa: E402
import live_candles_smoke as smoke  # noqa: E402

UTC = dt.timezone.utc
HOLD, RELEASE = hc.ES_CONTINUOUS | hc.ES_SYSTEM_REQUIRED, hc.ES_CONTINUOUS
MT5_VENUE = {"venue": {"kind": "MT5"}}


class _Setter:
    def __init__(self, ok: int = 1):
        self.calls, self.ok = [], ok

    def __call__(self, flags: int) -> int:
        self.calls.append(flags)
        return self.ok


def test_hold_then_release_around_the_run():
    s = _Setter()
    with hc.keep_awake(setter=s) as held:
        assert held is True and s.calls == [HOLD]
    assert s.calls == [HOLD, RELEASE]
    assert HOLD == 0x80000001 and RELEASE == 0x80000000          # no display / away-mode flags


def test_released_even_when_the_run_raises():
    s = _Setter()
    with pytest.raises(RuntimeError):
        with hc.keep_awake(setter=s):
            raise RuntimeError("run failed")
    assert s.calls == [HOLD, RELEASE]


def test_disabled_failed_or_unsupported_never_holds(monkeypatch):
    s = _Setter()
    with hc.keep_awake(enabled=False, setter=s) as held:
        assert held is False
    assert s.calls == []
    failing = _Setter(ok=0)                                           # SetThreadExecutionState returned NULL
    with hc.keep_awake(setter=failing) as held:
        assert held is False
    assert failing.calls == [HOLD]                                    # nothing to release
    monkeypatch.setattr(hc, "_execution_state_setter", lambda: None)  # e.g. not Windows
    with hc.keep_awake() as held:
        assert held is False


def test_scope_is_session_window_or_watch_run_only():
    mon = dt.datetime(2026, 10, 5, tzinfo=UTC)                        # Monday
    assert smoke.run_is_active("lsmc", mon.replace(hour=3), MT5_VENUE)
    assert smoke.run_is_active("crypto", mon.replace(hour=3), MT5_VENUE)
    assert not smoke.run_is_active("smoke", mon.replace(hour=8), MT5_VENUE)
    assert smoke.run_is_active("fx", mon.replace(hour=8), MT5_VENUE)               # ASIAN_LONDON trade 07-11
    assert smoke.run_is_active("fx", mon.replace(hour=11, minute=30), MT5_VENUE)   # + 30 min tail
    assert not smoke.run_is_active("fx", mon.replace(hour=11, minute=45), MT5_VENUE)
    assert not smoke.run_is_active("fx", mon.replace(hour=3), MT5_VENUE)
    assert not smoke.run_is_active("fx", mon.replace(hour=8), MT5_VENUE, cycle="LONDON_NEWYORK")
    sat = dt.datetime(2026, 10, 10, 21, 0, tzinfo=UTC)
    assert smoke.run_is_active("lsmc-weekend", sat, MT5_VENUE)
    assert not smoke.run_is_active("lsmc-weekend", sat, {"venue": {"kind": "PUBLIC_PERP"}})
    assert not smoke.run_is_active("lsmc-weekend", mon.replace(hour=21), MT5_VENUE)


def test_main_holds_keep_awake_for_the_run(tmp_path, monkeypatch):
    seen = []

    @contextmanager
    def fake_keep_awake(enabled=True, setter=None):
        seen.append(("enter", enabled))
        try:
            yield enabled
        finally:
            seen.append(("exit", enabled))

    monkeypatch.setattr(smoke, "keep_awake", fake_keep_awake)
    monkeypatch.setattr(smoke, "import_mt5", lambda: None)            # stop right after the guard
    monkeypatch.setattr(smoke, "archive_fx_runtime_failure", lambda *a, **k: [])   # no journal writes
    monkeypatch.setattr(hc, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(smoke, "utcnow", lambda: dt.datetime(2026, 10, 5, 3, 0, tzinfo=UTC))
    assert smoke.main(["--mode", "lsmc"]) == 1
    assert smoke.main(["--mode", "fx"]) == 1                          # 03:00: no FX session window
    assert seen == [("enter", True), ("exit", True), ("enter", False), ("exit", False)]
