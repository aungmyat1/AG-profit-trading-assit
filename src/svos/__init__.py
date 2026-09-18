"""SVOS -- Strategy Validation Operating System (historical -> optimization -> virtual
forward -> demo eligibility), WORK PACKAGES SVOS1-SVOS8.

This package implements the permanent SVOS flow as a RECONCILIATION over the
repository's existing canonical authorities, never as a competing one:

    * Lifecycle authority  -> validation_framework.models.LifecycleStage, read via
                              lifecycle_registry.get_lifecycle_stage (config/governance/
                              strategy_lifecycle.yaml). This package NEVER invents a new
                              lifecycle-stage label.
    * Gate vocabulary      -> validation_framework.ag_validation_methodology
                              AG_VALIDATION_G0_G10_V1 (G0..G10). This package reports
                              progress exclusively as canonical gate names.
    * Economic gate        -> validation_framework.economic_gate /
                              validation_framework.g3_gate (fail-closed while
                              config/governance/economic_gate_contract.yaml is PROPOSED).
    * Friction             -> FrictionProfile (svos.friction_profile) consuming the
                              repository's cost model / per-strategy friction estimates.
    * Execution            -> NEVER touched. The VirtualBroker is statically isolated
                              from src/execution/, src/mt5/, and order_send/order_check.

Safety invariants held throughout (see tests/test_svos_mt5_isolation.py):
    BROKER_MUTATION=false, DEMO_ORDER_SUBMITTED=false, LIVE_ORDER_SUBMITTED=false,
    LIVE_AUTHORIZED=false, PROTECTED_DATA_ACCESSED=false (unless an explicit lifecycle
    state authorizes it), H2_CAMPAIGN_MODIFIED=false, FOREIGN_WIP_STAGED=false.
"""
from __future__ import annotations

SVOS_SCHEMA_VERSION = "SVOS_HISTORICAL_TO_VIRTUAL_FORWARD_V1"

__all__ = ["SVOS_SCHEMA_VERSION"]
