"""AGP-C16: regression pin + successor-version proposal for the ST_ASIAN_SWEEP_5R_V1 EURUSD L3 defect.

Reproduced by C16 (and by C15 before it) at
`recorded:EURUSD:ASIAN_LONDON:2026-07-31`:

* **D-ASW-1 zero-risk geometry.** `entry_2_sweep` and `entry_3_range` return
  `decision_status=VALID` while `risk_distance == 0`. The v1.1.2 contract already declares
  `risk_and_money_distance.min_risk_distance: POSITIVE  # risk_distance <= 0 -> FAIL_CLOSED`,
  so the engine contradicts its own frozen declaration (an L2 divergence). Downstream gates
  catch it (the ticket is `TICKET_BLOCKED` with `positive_stop: false`), so no degenerate
  ticket can reach READY — but the emission itself is wrong.
* **D-ASW-2 non-append-only emission.** `route_completed_session` is one-shot and re-evaluates
  Entry 2 before Entry 3 over an ever-growing post-session window, so a later qualifying sweep
  replaces an earlier valid range-rejection emission for the same day. The day-scoped
  `signal_id` is reused, so an observer sees the same identity with changed content.

These tests **pin the current frozen behaviour** (they do not change it) and assert the
successor contract `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml` that closes both defects.
v1.1.2 is never edited in place (AGENTS.md: a behaviour-changing correction lands in a new
candidate version). No registry, READY, demo, live or broker surface is touched, and the
successor is registered nowhere and changes no runtime authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from strategy_engine.session import Candle  # noqa: E402
from strategy_engine.session.classifier import Regime  # noqa: E402
from strategy_engine.session.reference_box import build_reference_box  # noqa: E402
from strategy_engine.session.router import route_completed_session  # noqa: E402
from strategy_engine.session.setups import entry_2_sweep, entry_3_range  # noqa: E402

CONTRACT_V112 = ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
CONTRACT_V113 = ROOT / "strategies" / "ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml"
DAY = dt.date(2026, 7, 31)
UTC = dt.timezone.utc

# v1.1.2's recorded identity (registry S1 + C16 run). Must not move: a correction lands in a
# new candidate version, never as an in-place edit of the frozen candidate.
V112_CANONICAL_CONTRACT_HASH = "941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69"
V112_RAW_SHA256 = "4f936bbe17f4aa4fd3cd9fc85640bed57b6786f43c52e8e2d69aabb7234b14cf"

BOX_HIGH, BOX_LOW, BOX_MID = 1.1515, 1.1505, 1.1510


def _flat_reference_session() -> list[Candle]:
    """A completed 24-bar Asian range. Its exact shape does not matter: every case below
    supplies an explicit `regime_override` or calls the detector directly."""
    return [Candle(time=dt.datetime(2026, 7, 31, h, 0, tzinfo=UTC),
                   open=BOX_MID - 0.0005, high=BOX_HIGH, low=BOX_LOW, close=BOX_MID + 0.0002)
            for h in range(24)]


def _box():
    return build_reference_box("Asian", _flat_reference_session(), 24)


# The 2026-07-31 mechanism, reduced to two bars (values from the committed reproducer).
TOUCH_BAR = Candle(time=dt.datetime(2026, 7, 31, 8, 30, tzinfo=UTC),
                   open=1.15075, high=BOX_LOW + 0.001, low=BOX_LOW, close=BOX_LOW + 0.0005)
OPEN_AT_LOW_BAR = Candle(time=dt.datetime(2026, 7, 31, 9, 45, tzinfo=UTC),
                         open=BOX_LOW - 0.0001, high=BOX_LOW + 0.005, low=BOX_LOW - 0.0001,
                         close=BOX_LOW + 0.002)


def _route(window):
    return route_completed_session("ST_ASIAN_SWEEP_5R_V1", "EURUSD", "Asian", DAY,
                                   _flat_reference_session(), 24,
                                   post_session_candles=window, regime_override=Regime.RANGE)[2]


# --------------------------------------------------------------- D-ASW-1 pinned (current)


def test_entry_3_inclusive_boundary_touch_yields_zero_risk_but_valid():
    """D-ASW-1 (pins frozen behaviour): `low <= box_low` is inclusive, so an exact touch sets
    entry == stop == box_low and `risk_distance == 0.0` — yet the decision is VALID."""
    d = entry_3_range("ST_ASIAN_SWEEP_5R_V1", "EURUSD", _box(), DAY, [TOUCH_BAR])
    assert d.decision_status.value == "VALID"
    assert d.reason_code == "LOWER_BOUNDARY_REJECTION"
    assert d.entry_reference == BOX_LOW == d.stop_reference
    assert d.risk_distance == 0.0


def test_entry_2_bar_opening_at_its_low_yields_zero_risk_but_valid():
    """D-ASW-1: a sweep candle that opens at its own low sets `entry == stop == min(open, close)`
    == candle.low, so `risk_distance == 0.0` — yet the decision is VALID."""
    d = entry_2_sweep("ST_ASIAN_SWEEP_5R_V1", "EURUSD", _box(), DAY, [OPEN_AT_LOW_BAR])
    assert d.decision_status.value == "VALID"
    assert d.reason_code == "LOWER_SWEEP_STRICT_PENETRATION"
    assert d.entry_reference == OPEN_AT_LOW_BAR.low == d.stop_reference
    assert d.risk_distance == 0.0


def test_negative_risk_is_also_unreachable_in_the_frozen_detectors():
    """The detectors cannot produce a negative distance either, so `<= 0` is the exact rule
    surface that v1.1.2 declares and the engine does not enforce."""
    d2 = entry_2_sweep("ST_ASIAN_SWEEP_5R_V1", "EURUSD", _box(), DAY, [OPEN_AT_LOW_BAR])
    d3 = entry_3_range("ST_ASIAN_SWEEP_5R_V1", "EURUSD", _box(), DAY, [TOUCH_BAR])
    assert d2.risk_distance >= 0 and d3.risk_distance >= 0
    assert min(d2.risk_distance, d3.risk_distance) == 0.0


# --------------------------------------------------------------- D-ASW-2 pinned (current)


def test_later_qualifying_sweep_supersedes_an_earlier_valid_emission():
    """D-ASW-2 (pins frozen behaviour): growing the window by one bar re-runs the same day's
    routing and replaces the earlier VALID RANGE emission with a VALID SWEEP emission."""
    early = _route([TOUCH_BAR])
    late = _route([TOUCH_BAR, OPEN_AT_LOW_BAR])

    assert early.setup_type.value == "RANGE" and early.decision_status.value == "VALID"
    assert late.setup_type.value == "SWEEP" and late.decision_status.value == "VALID"

    changed = {f for f in ("setup_type", "reason_code", "signal_timestamp",
                           "entry_reference", "stop_reference", "risk_distance")
               if getattr(early, f) != getattr(late, f)}
    assert changed == {"setup_type", "reason_code", "signal_timestamp",
                       "entry_reference", "stop_reference"}

    # The earlier emission is not preserved anywhere: `route_completed_session` is one-shot
    # and returns exactly one SetupDecision, so there is no append-only stream to compare.
    assert late.signal_timestamp != early.signal_timestamp
    assert late.signal_timestamp == OPEN_AT_LOW_BAR.time


def test_routing_is_deterministic_for_a_fixed_window():
    """The defect is ordering, not nondeterminism: a fixed window always gives one answer."""
    assert _route([TOUCH_BAR, OPEN_AT_LOW_BAR]) == _route([TOUCH_BAR, OPEN_AT_LOW_BAR])


# --------------------------------------------------------------- frozen v1.1.2 is untouched


def test_v112_contract_and_candidate_are_unmodified():
    """A correction must never be an in-place edit of the frozen v1.1.2 candidate."""
    raw = hashlib.sha256(CONTRACT_V112.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert raw == V112_RAW_SHA256, "v1.1.2 YAML content changed — forbidden"

    from v1_tickets.authority import CANDIDATE_CONTRACTS, logic_identity
    assert CANDIDATE_CONTRACTS[("ST_ASIAN_SWEEP_5R_V1", "1.1.2")] == \
        "strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml"
    ident = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.2", ROOT)
    assert ident["contract_hash"] == V112_CANONICAL_CONTRACT_HASH

    spec = yaml.safe_load(CONTRACT_V112.read_text(encoding="utf-8"))
    assert spec["version"] == "1.1.2"
    assert spec["status"] == "CANDIDATE_PENDING_OWNER_CONFIRM"


def test_v112_already_declares_the_positive_risk_rule_it_does_not_enforce():
    """The L2 divergence: the declaration exists in v1.1.2; only the engine lags it."""
    spec = yaml.safe_load(CONTRACT_V112.read_text(encoding="utf-8"))
    risk = spec["risk_and_money_management"]
    assert risk["min_risk_distance"] == "POSITIVE"
    assert risk["stop_loss_mode"] == "SWEEP_CANDLE_WICK_EXTREME"
    # And the changelog records the intended fail-closed resolution (B-STOP / B-MINRANGE).
    text = CONTRACT_V112.read_text(encoding="utf-8")
    assert "Zero/negative risk distance is undefined -> FAIL_CLOSED." in text
    assert "risk_distance must be > 0" in text


# --------------------------------------------------------------- the successor proposal


def test_successor_contract_exists_and_is_authority_free():
    assert CONTRACT_V113.exists(), "v1.1.3 proposal missing"
    spec = yaml.safe_load(CONTRACT_V113.read_text(encoding="utf-8"))
    assert spec["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1"
    assert spec["version"] == "1.1.3"
    assert spec["status"] == "CANDIDATE_PENDING_OWNER_CONFIRM"
    assert spec["authority"]["demo_authorized"] is False
    assert spec["authority"]["live_authorized"] is False
    assert spec["authority"]["edge_verified"] is False
    assert spec["authority"]["registered_in_registry_yaml"] is False
    assert spec["authority"]["changes_runtime_binding"] is False


def test_successor_declares_both_closed_rules():
    spec = yaml.safe_load(CONTRACT_V113.read_text(encoding="utf-8"))
    corr = spec["corrections"]
    assert corr["D-ASW-1"]["rule"] == "REJECT_ZERO_OR_NEGATIVE_RISK"
    assert corr["D-ASW-1"]["action"] == "FAIL_CLOSED"
    assert corr["D-ASW-2"]["rule"] == "APPEND_ONLY_PER_QUALIFYING_BAR"
    assert corr["D-ASW-2"]["action"] == "APPEND_NEW_EMISSION"
    # The risk boundary is expressed exactly, not as prose.
    assert spec["risk_and_money_management"]["min_risk_distance"] == "STRICTLY_POSITIVE"
    assert spec["risk_and_money_management"]["non_positive_risk_action"] == "FAIL_CLOSED"


def test_successor_differs_from_v112_only_in_the_declared_corrections():
    """The proposal must not smuggle unrelated rule, threshold or friction changes."""
    old = yaml.safe_load(CONTRACT_V112.read_text(encoding="utf-8"))
    new = yaml.safe_load(CONTRACT_V113.read_text(encoding="utf-8"))

    changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    assert changed <= {"version", "updated_utc", "risk_and_money_management", "signal_stream",
                       "corrections", "successor_of", "evidence_policy", "authority"}, changed
    # Every rule surface outside the two declared corrections is carried over unchanged.
    assert old["entry_rules"] == new["entry_rules"]
    assert old["status"] == new["status"] == "CANDIDATE_PENDING_OWNER_CONFIRM"
    assert old["instruments"] == new["instruments"]
    assert old["session_pairs"] == new["session_pairs"]
    assert old["regime_classification"] == new["regime_classification"]
    assert old["position_split_and_targets"] == new["position_split_and_targets"]
    assert old["invalidation_rules"] == new["invalidation_rules"]
    assert old["semantic_safety_contract"] == new["semantic_safety_contract"]
    # The corrected risk block keeps every v1.1.2 threshold untouched.
    for key in ("max_spread_allowed_pips", "max_spread_fraction_of_stop",
                "spread_not_measurable", "slippage_limit_points", "signal_expiry_minutes",
                "stop_loss_mode"):
        assert new["risk_and_money_management"][key] == old["risk_and_money_management"][key]
    assert old["timeframe"] == new["timeframe"] and old["magic_number"] == new["magic_number"]


def test_successor_is_inert_in_every_authority_surface():
    """No adapter, no candidate registration, no registry entry, no READY/demo/live path."""
    from v1_tickets.authority import CANDIDATE_CONTRACTS, logic_identity
    assert ("ST_ASIAN_SWEEP_5R_V1", "1.1.3") not in CANDIDATE_CONTRACTS
    assert "ST_ASIAN_SWEEP_5R_V1_1_1_3" not in \
        (ROOT / "strategies" / "registry.yaml").read_text(encoding="utf-8")
    # identity is derivable for the record, but is deliberately not registered anywhere
    ident = logic_identity("ST_ASIAN_SWEEP_5R_V1", "1.1.3", ROOT)
    assert ident is not None and ident["contract_hash"] != V112_CANONICAL_CONTRACT_HASH


def test_successor_evidence_instructions_forbid_transferring_v112_passes():
    spec = yaml.safe_load(CONTRACT_V113.read_text(encoding="utf-8"))
    note = spec["evidence_policy"]
    assert note["v112_pass_scopes_remain_not_verified"] is True
    assert note["reverification_required_before_any_pass"] is True
    assert note["inherits_identity_from"] is None
