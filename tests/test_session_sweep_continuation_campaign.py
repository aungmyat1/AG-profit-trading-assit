from datetime import date, datetime, timezone

from session_sweep_continuation.campaign import (
    allocate_risk,
    apply_entry,
    build_campaign_id,
    invalidate_campaign,
    new_campaign,
)
from session_sweep_continuation.setups import SetupModel
from session_sweep_continuation.state_machine import Event, State

CONFIG = {
    "campaign": {
        "max_entries": 3,
        "maximum_total_risk_pct": 1.0,
        "min_meaningful_risk_pct": 0.05,
        "block_new_entries_after_realized_r_enabled": False,
        "block_new_entries_after_realized_r_lte": -1.0,
    },
    "setup_limits": {"S1_max_per_campaign": 1, "S2_max_per_campaign": 1, "S3_max_per_campaign": 2},
    "risk_allocation": {"S1": 0.40, "S2": 0.30, "S3": 0.30},
}

NOW = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)


def _campaign():
    c = new_campaign("EURUSD", "ASIAN_LONDON", date(2026, 9, 10), "LONG", "RANGE", NOW)
    c.state = State.CAMPAIGN_ACTIVE
    return c


def test_campaign_id_format():
    assert build_campaign_id("EURUSD", "ASIAN_LONDON", date(2026, 9, 10), "LONG") == "EURUSD-ASIAN_LONDON-20260910-LONG"


def test_campaign_max_total_risk_pct_1_percent_cap_enforced():
    c = _campaign()
    # S1 allocates 0.40, S2 allocates 0.30 -> 0.70 used, 0.30 room left.
    r1 = allocate_risk(c, SetupModel.S1, CONFIG)
    assert r1.accepted and abs(r1.risk_pct - 0.40) < 1e-9
    apply_entry(c, SetupModel.S1, r1.risk_pct, NOW, 1.1, 1.09)

    r2 = allocate_risk(c, SetupModel.S2, CONFIG)
    assert r2.accepted and abs(r2.risk_pct - 0.30) < 1e-9
    apply_entry(c, SetupModel.S2, r2.risk_pct, NOW, 1.1, 1.09)

    # A first S3 wants 0.30 but only 0.30 room remains -- exactly fits (clamped == target).
    r3 = allocate_risk(c, SetupModel.S3, CONFIG)
    assert r3.accepted and abs(r3.risk_pct - 0.30) < 1e-9
    apply_entry(c, SetupModel.S3, r3.risk_pct, NOW, 1.1, 1.09)

    assert abs(c.open_risk_pct - 1.0) < 1e-9
    # cap now exhausted -- but campaign is also at max_entries (3) already, so this
    # would be rejected for MAX_TOTAL_ENTRIES first; verified separately below.


def test_max_total_entries_per_campaign_is_authoritative_not_sum_of_setup_maxima():
    c = _campaign()
    r1 = allocate_risk(c, SetupModel.S1, CONFIG)
    apply_entry(c, SetupModel.S1, r1.risk_pct, NOW, 1.1, 1.09)
    r2 = allocate_risk(c, SetupModel.S2, CONFIG)
    apply_entry(c, SetupModel.S2, r2.risk_pct, NOW, 1.1, 1.09)
    r3a = allocate_risk(c, SetupModel.S3, CONFIG)
    apply_entry(c, SetupModel.S3, r3a.risk_pct, NOW, 1.1, 1.09)

    # A second S3 is individually still within its own per-setup max (2), but the
    # campaign is already at 3 total entries -- must be rejected on entry count, not
    # on risk (S1+S2+S3+S3 = 4 entries must be rejected).
    r3b = allocate_risk(c, SetupModel.S3, CONFIG)
    assert r3b.accepted is False
    assert r3b.reason == "MAX_TOTAL_ENTRIES_PER_CAMPAIGN_REACHED"


def test_remaining_risk_clamping_rejects_below_min_meaningful():
    c = _campaign()
    # Manually consume risk down to just under min_meaningful (0.05) remaining.
    r1 = allocate_risk(c, SetupModel.S1, CONFIG)  # 0.40
    apply_entry(c, SetupModel.S1, r1.risk_pct, NOW, 1.1, 1.09)
    r2 = allocate_risk(c, SetupModel.S2, CONFIG)  # 0.30 -> 0.70 used
    apply_entry(c, SetupModel.S2, r2.risk_pct, NOW, 1.1, 1.09)
    # simulate an already-large open risk leaving < min_meaningful room by adding a
    # synthetic entry directly (bypassing allocate_risk) that consumes remaining room.
    apply_entry(c, SetupModel.S3, 0.29, NOW, 1.1, 1.09)  # 0.70+0.29=0.99, 0.01 remaining
    # this pushed entry_count to 3 already -- construct a fresh campaign for a clean
    # remaining-risk-only check instead:
    c2 = _campaign()
    apply_entry(c2, SetupModel.S1, 0.98, NOW, 1.1, 1.09)  # leaves 0.02 remaining < min_meaningful 0.05
    result = allocate_risk(c2, SetupModel.S2, CONFIG)
    assert result.accepted is False
    assert result.reason == "MIN_MEANINGFUL_RISK_UNAVAILABLE"


def test_no_add_after_invalidation():
    c = _campaign()
    invalidate_campaign(c, Event.STRUCTURE_INVALIDATED, NOW)
    result = allocate_risk(c, SetupModel.S1, CONFIG)
    assert result.accepted is False
    assert result.reason == "CAMPAIGN_NOT_ACCEPTING_ENTRIES"


def test_session_expiry_blocks_entries():
    c = _campaign()
    invalidate_campaign(c, Event.SESSION_WINDOW_EXPIRED, NOW)
    result = allocate_risk(c, SetupModel.S1, CONFIG)
    assert result.accepted is False
    assert result.reason == "CAMPAIGN_NOT_ACCEPTING_ENTRIES"


def test_per_setup_max_occurrences_enforced():
    c = _campaign()
    r1 = allocate_risk(c, SetupModel.S1, CONFIG)
    apply_entry(c, SetupModel.S1, r1.risk_pct, NOW, 1.1, 1.09)
    # a second S1 must be rejected (S1_max_per_campaign=1) even though risk/entry room remain
    result = allocate_risk(c, SetupModel.S1, CONFIG)
    assert result.accepted is False
    assert result.reason == "SETUP_MAX_OCCURRENCES_REACHED"
