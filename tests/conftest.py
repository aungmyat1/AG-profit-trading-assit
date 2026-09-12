"""AG_AUDIT_REMEDIATION_A3: collection-time portability shim, nothing else.

`MetaTrader5` has no Linux/macOS wheel -- it wraps the native Windows MT5
terminal. Several core modules (`mt5.symbol_resolver`, `mt5.market_data`,
`execution.mt5_gateway`, `mt5.management_gateway`, `api.broker_service`)
import it unconditionally, and that import chain reaches deep into
`market_structure`/`liquidity`/`daytrading`/`execution`/`authorization`/
`api.app` -- so on a machine without the real package, ~170 otherwise
unrelated backend tests fail at COLLECTION time (ModuleNotFoundError),
before a single test body runs. That is a portability gap in the test
environment, not a defect in those 170 tests.

This file installs a placeholder into `sys.modules['MetaTrader5']` *only*
when the real package cannot be imported, so `import MetaTrader5` succeeds
everywhere it is written today -- zero source files in `src/mt5/` change.

DELIBERATELY STRICTER THAN A MagicMock. An unrestricted MagicMock would let
a test that actually exercises MT5 semantics *silently appear to work*,
returning truthy mock objects from `initialize()`, `copy_rates_from_pos()`,
`order_send()` and friends. That is precisely the failure mode this project
forbids: a real market/broker failure must never quietly become synthetic
data or a fake success. So instead:

  - Documented, version-stable MT5 *constants* are provided as real ints,
    because those are read at import time and in simple equality checks.
  - Every other attribute resolves to a callable that RAISES
    `MT5StubOperationAttempted` the moment it is CALLED. Importing a module
    never calls these, so collection succeeds; a test body that reaches a
    real MT5 operation fails loudly and legibly instead of being deceived.

On the real Windows/MT5 development environment the genuine package is
installed and the try/except below is a complete no-op -- verified: this
dev box has MetaTrader5 5.0.5735, so nothing here is active locally.

Tests that genuinely require a live terminal should be marked
`@pytest.mark.live_mt5` (registered in pyproject.toml) so they SKIP honestly
where MT5 is unavailable and run normally where it is.
"""
from __future__ import annotations

import sys
import types

import pytest


class MT5StubOperationAttempted(RuntimeError):
    """Raised when test code calls a real MT5 operation through the portability stub."""


def _install_mt5_collection_stub() -> None:
    module = types.ModuleType("MetaTrader5")
    module.__doc__ = (
        "Collection-time portability stub installed by tests/conftest.py. "
        "The real MetaTrader5 package is unavailable on this platform. "
        "Constants are real; every operation raises MT5StubOperationAttempted."
    )
    module.MT5StubOperationAttempted = MT5StubOperationAttempted

    # Real, stable MetaTrader5 constant values (documented, version-independent)
    # for the attributes this repo reads at import time or compares by equality.
    constants = {
        "TIMEFRAME_M1": 1,
        "TIMEFRAME_M5": 5,
        "TIMEFRAME_M15": 15,
        "TIMEFRAME_M30": 30,
        "TIMEFRAME_H1": 16385,
        "TIMEFRAME_H4": 16388,
        "TIMEFRAME_D1": 16408,
        "ORDER_TIME_GTC": 0,
        "ORDER_FILLING_IOC": 1,
        "TRADE_ACTION_DEAL": 1,
        "TRADE_ACTION_SLTP": 6,
        "TRADE_RETCODE_DONE": 10009,
        "ORDER_TYPE_BUY": 0,
        "ORDER_TYPE_SELL": 1,
        "DEAL_TYPE_BUY": 0,
        "DEAL_TYPE_SELL": 1,
        "ACCOUNT_TRADE_MODE_DEMO": 0,
        "ACCOUNT_TRADE_MODE_REAL": 2,
    }
    for name, value in constants.items():
        setattr(module, name, value)

    def _module_getattr(name: str):
        if name.startswith("__"):
            raise AttributeError(name)

        def _refuse(*args, **kwargs):
            raise MT5StubOperationAttempted(
                f"MetaTrader5.{name}() was called, but the real MetaTrader5 package is "
                "not installed on this platform. tests/conftest.py provides an "
                "import-only portability stub that deliberately refuses to emulate "
                "broker or market-data behavior. Mark this test "
                "@pytest.mark.live_mt5, or monkeypatch the MT5 surface explicitly."
            )

        _refuse.__name__ = name
        return _refuse

    module.__getattr__ = _module_getattr  # type: ignore[attr-defined]
    sys.modules["MetaTrader5"] = module


try:  # pragma: no cover - environment dependent
    import MetaTrader5  # noqa: F401 -- real package present (Windows dev box); no-op.

    MT5_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    _install_mt5_collection_stub()
    MT5_AVAILABLE = False


def pytest_collection_modifyitems(config, items):
    """Skip `live_mt5`-marked tests when the real MetaTrader5 package is absent.

    Where the genuine package IS installed (the project's Windows dev box) this
    is a no-op and those tests run normally -- it never hides a real failure on
    the environment that can actually observe one.
    """
    if MT5_AVAILABLE:
        return
    skip_live = pytest.mark.skip(
        reason="requires the real MetaTrader5 package / a live MT5 terminal"
    )
    for item in items:
        if "live_mt5" in item.keywords:
            item.add_marker(skip_live)
