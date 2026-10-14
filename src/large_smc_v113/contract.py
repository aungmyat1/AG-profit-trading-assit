"""Append-only ST_LARGE_SMC_V1@1.1.3 constants and OD1014 D2 evidence.

Frozen detector constants are reused. The candidate has no execution authority.
"""
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import yaml

from large_smc_watch.contract import *  # noqa: F403
from large_smc_watch.contract import V1_SYMBOLS

STRATEGY_VERSION = '1.1.3'
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((REPO_ROOT/'strategies/ST_LARGE_SMC_V1_1_1_3.yaml').read_text())
POI_MAX_AGE_TRADING_DAYS = SPEC['rules']['poi']['max_age_trading_days']
if (isinstance(POI_MAX_AGE_TRADING_DAYS, bool) or not isinstance(POI_MAX_AGE_TRADING_DAYS, int)
        or POI_MAX_AGE_TRADING_DAYS < 0):
    raise ValueError('invalid rules.poi.max_age_trading_days')


def resolve_pip(symbol, root=None):
    from .metadata import load_pip
    return load_pip(symbol, root)


def resolve_point(symbol):
    pip, _source = resolve_pip(symbol)
    return (float(Decimal(str(pip))/10), 'HOST_CAPTURED') if pip is not None else (None, 'MISSING')


class EvidencedPips(Mapping):
    """Compatibility view for audit lanes; never retains an evidenced value after file failure."""
    def __getitem__(self, symbol):
        pip, _source = resolve_pip(symbol)
        if pip is None:
            raise KeyError(symbol)
        return pip

    def __iter__(self):
        return (symbol for symbol in V1_SYMBOLS if resolve_pip(symbol)[0] is not None)

    def __len__(self):
        return sum(1 for _ in self)


C10_PIP_SIZE = EvidencedPips()
