"""OD1012-ACCOUNT runtime account pin: the ticket/scan runtime evaluates only on the pinned DEMO account."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/host"))

import _host_common as hc  # noqa: E402

from host_evidence.account_pin import (  # noqa: E402
    ACCOUNT_PIN_VERIFIED,
    check_account,
    load_pin,
)

DEMO, REAL = 0, 2
PIN = load_pin()


def _info(**kw):
    base = {"server": "VTMarkets-Demo", "login": 1234999, "trade_mode": DEMO}
    base.update(kw)
    return SimpleNamespace(**base)


def test_committed_pin_is_suffix_only_vt_demo():
    assert PIN == {"decision_id": "OD1012-ACCOUNT", "server": "VTMarkets-Demo", "login_suffix": "999",
                   "trade_mode": "DEMO"}


def test_pinned_account_matches():
    assert check_account(_info(), PIN, DEMO) == (True, ACCOUNT_PIN_VERIFIED)


@pytest.mark.parametrize("info,reason", [
    (_info(login=1234985), "LOGIN_SUFFIX"),               # owner sandbox ...985 is not the AG account
    (_info(trade_mode=REAL), "TRADE_MODE"),               # live trade mode
    (_info(server="VTMarkets-Live"), "SERVER"),
    (_info(login=None), "LOGIN_SUFFIX"),
    (None, "ACCOUNT_INFO_UNAVAILABLE"),                   # missing account_info
])
def test_mismatch_fails_closed(info, reason):
    assert check_account(info, PIN, DEMO) == (False, f"ACCOUNT_PIN_MISMATCH {reason}")


def test_missing_or_malformed_pin_fails_closed(tmp_path):
    assert load_pin(tmp_path) is None
    (tmp_path / "config").mkdir()
    (tmp_path / "config/account_pin.yaml").write_text(
        "account_pin: {server: VTMarkets-Demo, login_suffix: 999, trade_mode: DEMO}\n", encoding="utf-8")
    assert load_pin(tmp_path) is None                      # suffix must be a quoted digit string
    assert check_account(_info(), None, DEMO) == (False, "ACCOUNT_PIN_MISMATCH PIN_UNAVAILABLE")


class _MT5:
    ACCOUNT_TRADE_MODE_DEMO = DEMO

    def __init__(self, info=None, raise_exc=False):
        self._info, self._raise = info, raise_exc

    def account_info(self):
        if self._raise:
            raise RuntimeError("terminal gone")
        return self._info


@pytest.mark.parametrize("mt5,ok,status", [
    (_MT5(_info()), True, "ACCOUNT_PIN_VERIFIED"),
    (_MT5(_info(login=7654985)), False, "ACCOUNT_PIN_MISMATCH LOGIN_SUFFIX"),
    (_MT5(_info(trade_mode=REAL)), False, "ACCOUNT_PIN_MISMATCH TRADE_MODE"),
    (_MT5(None), False, "ACCOUNT_PIN_MISMATCH ACCOUNT_INFO_UNAVAILABLE"),
    (_MT5(raise_exc=True), False, "ACCOUNT_PIN_MISMATCH ACCOUNT_INFO_UNAVAILABLE RuntimeError"),
])
def test_host_guard_reads_account_info_and_never_reports_the_login(mt5, ok, status):
    got = hc.require_pinned_demo_account(mt5)
    assert got == (ok, status)
    assert "7654985" not in got[1] and "1234999" not in got[1]
