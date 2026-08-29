"""DUAL_DAYTRADING_RUNTIME_V1 spec section 28: CLI mode flags only -- no live MT5 call."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_daytrading_runtime as cli  # noqa: E402


def test_once_and_watch_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli._parse_args(["--once", "--watch"])


def test_once_parses_cleanly():
    args = cli._parse_args(["--once", "--json"])
    assert args.once is True
    assert args.json is True


def test_status_parses_cleanly():
    args = cli._parse_args(["--status"])
    assert args.status is True


def test_watch_default_interval_is_60_seconds():
    args = cli._parse_args(["--watch"])
    assert args.interval == 60
