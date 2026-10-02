"""Frozen constants of AG_CRYPTO_CFD_STRATEGY_CONTRACT_V1 (ST_CRYPTO_CFD_SWEEP_RETEST_V1).

Single source of the contract's identity, scope, policies, and status vocabulary. The
YAML authority is strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml; this module mirrors it
in code so tests and the (future) scanner adapter consume one frozen surface.

Instrument authority is the VT Markets BTCUSD/ETHUSD crypto CFDs verified by the frozen
crypto observation layer (docs/status/AG_CRYPTO_SCANNER_V1_OBSERVATION_STATUS.md,
PR #28). Explicitly NOT in scope and NOT imported anywhere in this package (the YAML
authority names each forbidden identity explicitly; this package enforces scope through
the INSTRUMENTS allow-list so none of those identities even appears in code):

  - the USDT-perpetual instrument identities of the perp strategy profile
  - the perp tick-model module of strategy_engine/sweep_retest
  - the perp strategy-activity time window
  - any perp funding-rate or perp risk assumption
  - FX session gating and FX pip conventions

Research separation (never conflated): STRATEGY_CONTRACT_VALID means reproducible logic
only. EDGE_VERIFIED is False. RISK_AUTHORIZED is False. Proposal authority is BLOCKED
while SPREAD_POLICY_UNDEFINED / RISK_POLICY_AMBIGUOUS hold, and execution authority does
not exist anywhere in this package.
"""
from __future__ import annotations

from typing import Tuple

CONTRACT_ID = "ST_CRYPTO_CFD_SWEEP_RETEST_V1"
CONTRACT_VERSION = "1.0.0"
CONTRACT_YAML = "strategies/ST_CRYPTO_CFD_SWEEP_RETEST_V1.yaml"

# ------------------------------------------------------------------ instrument authority
ASSET_CLASS = "CRYPTO_CFD"
INSTRUMENTS: Tuple[str, ...] = ("BTCUSD", "ETHUSD")
EXPECTED_DIGITS = 2
BROKER_POINT = 0.01  # verified live 2026-10-02 (crypto observation status)

# Scope is a positive allow-list: ANY symbol outside INSTRUMENTS (including every
# USDT-perpetual identity) is rejected as SYMBOL_NOT_IN_CONTRACT, fail-closed.

# ------------------------------------------------------------------ liquidity reference
REFERENCE_KIND = "PREVIOUS_UTC_DAY"
REFERENCE_LABEL = "PreviousUtcDay"
REFERENCE_TIMEFRAME = "M5"
# CRYPTO_24H_OBSERVATION declares no expected daily break, so a complete previous UTC
# day is exactly 288 closed M5 bars. Fewer -> REFERENCE_INCOMPLETE, fail-closed; any
# tolerance would be an invented number.
REFERENCE_EXPECTED_M5_BARS = 288

# ------------------------------------------------------------------ POI authority
ALLOWED_POI_TYPES: Tuple[str, ...] = ("PREV_UTC_DAY_EXTREME", "BROKEN_M5_SWING")
# fvg_or_order_block_alternative=false is the frozen family evidence; no FVG / order
# block / range-boundary detection rule exists for these CFDs, so none is authorized.
UNAUTHORIZED_POI_TYPES: Tuple[str, ...] = ("FVG", "ORDER_BLOCK", "RANGE_BOUNDARY")

# ------------------------------------------------------------------ trigger geometry
# STOP_BUFFER_POLICY_V1 = ZERO_PRICE_BUFFER -- a PREREGISTERED_RESEARCH_HYPOTHESIS.
# Zero is frozen because it is the only buffer value that adds no invented number to
# the geometry; it is NOT a claim that a zero buffer is economically correct. The
# broker's reported tick_size/tick_value of 0.0 is insufficient metadata (a reporting
# gap), not justification: whether the exact sweep extreme survives real spread/wick
# noise is precisely what research must measure. Any non-zero buffer is a NEW
# candidate/version under its own governance amendment, never an in-place edit.
STOP_BUFFER_POINTS = 0
STOP_BUFFER_PRICE = STOP_BUFFER_POINTS * BROKER_POINT

RETEST_TOLERANCE_PRICE = 0.0  # exact touch of the broken swing (frozen family rule)
ENTRY_TIMING = "AT_FIRST_VALID_RETEST_TOUCH"  # limit level = broken swing price

TP1_VOLUME_PCT = 0.5
TP1_ACTION = "MOVE_REMAINING_TO_BREAKEVEN"

# ------------------------------------------------------------------ session / time policy
SESSION_POLICY = "BROKER_DEFINED / 24H_OBSERVATION"
FX_SESSION_GATE_APPLIED = False
EXECUTION_WINDOWS: Tuple = ()  # none: no FX session window, no perp activity window

# ------------------------------------------------------------------ spread / cost policy
SPREAD_POLICY = "SPREAD_POLICY_UNDEFINED"  # no validated threshold exists
SPREAD_UNITS: Tuple[str, ...] = ("BROKER_POINTS", "PRICE", "PERCENT")  # never FX pips

# ------------------------------------------------------------------ risk policy interface
RISK_POLICY_STATUS = "RISK_POLICY_AMBIGUOUS"  # no governance-authorized risk percentage
POSITION_SIZE = "NOT_CALCULATED"
REQUIRED_SIZING_INPUTS: Tuple[str, ...] = (
    "account_equity",
    "authorized_risk_percent",  # must come from an explicit governance decision
    "stop_distance_price",      # produced by this contract
    "tick_size",                # currently 0.0 from broker -> unusable
    "tick_value",               # currently 0.0 from broker -> unusable
    "volume_min",
    "volume_max",
    "volume_step",
)

# ------------------------------------------------------------------ research separation
STRATEGY_CONTRACT_VALID = True   # reproducible logic only
EDGE_VERIFIED = False
RISK_AUTHORIZED = False
PROPOSAL_AUTHORITY = "BLOCKED"
EXECUTION_AUTHORIZED = False

# ------------------------------------------------------------------ status vocabulary
CONTRACT_COMPLETE = "CONTRACT_COMPLETE"
CONTRACT_PARTIAL = "CONTRACT_PARTIAL"
CONTRACT_BLOCKED = "CONTRACT_BLOCKED"
SYMBOL_NOT_IN_CONTRACT = "SYMBOL_NOT_IN_CONTRACT"

OPEN_AUTHORITIES: Tuple[str, ...] = (
    "SPREAD_POLICY_UNDEFINED",
    "RISK_POLICY_AMBIGUOUS",
    "SIZING_METADATA_INCOMPLETE",  # broker tick_size/tick_value returned as 0.0
)


def contract_status(symbol: str) -> dict:
    """Deterministic per-instrument contract classification. CONTRACT_COMPLETE means
    every rule is deterministic and machine-testable -- it does NOT mean EDGE_VERIFIED,
    RISK_AUTHORIZED, or any proposal/execution authority."""
    if symbol not in INSTRUMENTS:
        return {
            "contract_id": CONTRACT_ID,
            "symbol": symbol,
            "status": SYMBOL_NOT_IN_CONTRACT,
            "reason": "only BTCUSD/ETHUSD CRYPTO_CFD are in scope; USDT perpetual "
                      "instruments are governed by their own separate contract and are "
                      "never reused here",
        }
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "symbol": symbol,
        "asset_class": ASSET_CLASS,
        "status": CONTRACT_COMPLETE,
        "open_authorities": list(OPEN_AUTHORITIES),
        "strategy_contract_valid": STRATEGY_CONTRACT_VALID,
        "edge_verified": EDGE_VERIFIED,
        "risk_authorized": RISK_AUTHORIZED,
        "proposal_authority": PROPOSAL_AUTHORITY,
        "execution_authorized": EXECUTION_AUTHORIZED,
        "session_policy": SESSION_POLICY,
        "spread_policy": SPREAD_POLICY,
        "risk_policy_status": RISK_POLICY_STATUS,
    }
