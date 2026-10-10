"""AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1 -- deterministic BTCUSD/ETHUSD CFD strategy contract.

RESEARCH_ONLY and NON-EXECUTING. See contract.py (frozen constants) and rules.py
(pure evaluation functions). No module in this package may import any broker-mutating
capability, any FX session gate, or any USDT-perpetual identity.
"""
from .contract import (
    ASSET_CLASS,
    CONTRACT_ID,
    CONTRACT_VERSION,
    INSTRUMENTS,
    SESSION_POLICY,
    SPREAD_POLICY,
    RISK_POLICY_STATUS,
    contract_status,
)
from .guard import evaluate  # fail-closed open-bar guard over the frozen rules.evaluate

__all__ = [
    "ASSET_CLASS", "CONTRACT_ID", "CONTRACT_VERSION", "INSTRUMENTS",
    "SESSION_POLICY", "SPREAD_POLICY", "RISK_POLICY_STATUS",
    "contract_status", "evaluate",
]
