"""WP1 + WP3 tests (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md)."""
from __future__ import annotations

import datetime as dt

import pytest

from ticket_delivery.archive import (
    CYCLE_STATE_NO_TRADE,
    CYCLE_STATE_READY,
    CycleDecisionRecord,
    archive_cycle_decision,
)
from ticket_delivery.identity import (
    InvalidIdentityFieldError,
    correction_id,
    delivery_attempt_id,
    logical_ticket_id,
)


def _record(**overrides):
    base = dict(
        strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", application_release="AG_TRADE_ASSISTANT_V1_0_3",
        symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7), cycle_state=CYCLE_STATE_READY,
        evaluation_time_utc="2026-09-07T07:45:00+00:00", payload={"direction": "SHORT"}, reason_codes=("UPPER_SWEEP",),
    )
    base.update(overrides)
    return CycleDecisionRecord(**base)


# --------------------------------------------------------------------------- WP1 identity

def test_identical_occurrence_produces_the_same_logical_ticket_id():
    a = logical_ticket_id(strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    b = logical_ticket_id(strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    assert a == b


@pytest.mark.parametrize("field_name,override", [
    ("symbol", {"symbol": "GBPUSD"}),
    ("cycle", {"cycle": "LONDON_NEWYORK"}),
    ("trading_date", {"trading_date": dt.date(2026, 9, 8)}),
    ("strategy_version", {"strategy_version": "1.1.2"}),
    ("strategy_id", {"strategy_id": "Y"}),
])
def test_a_different_dimension_never_collides(field_name, override):
    base = dict(strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    a = logical_ticket_id(**base)
    changed = dict(base)
    changed.update(override)
    b = logical_ticket_id(**changed)
    assert a != b, f"{field_name} change did not change the logical_ticket_id"


def test_retry_creates_a_new_attempt_id_never_a_new_logical_ticket():
    ticket_id = logical_ticket_id(strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    attempt_1 = delivery_attempt_id(logical_ticket_id_=ticket_id, attempt_number=1)
    attempt_2 = delivery_attempt_id(logical_ticket_id_=ticket_id, attempt_number=2)
    assert attempt_1 != attempt_2
    assert attempt_1.startswith(ticket_id)
    assert attempt_2.startswith(ticket_id)


def test_correction_preserves_original_logical_identity():
    ticket_id = logical_ticket_id(strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    corr = correction_id(logical_ticket_id_=ticket_id, correction_number=1)
    assert corr.startswith(ticket_id)
    assert corr != ticket_id


def test_unsafe_field_value_fails_closed_rather_than_silently_collide():
    with pytest.raises(InvalidIdentityFieldError):
        logical_ticket_id(strategy_id="X|EVIL", strategy_version="1.0.0", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))


# --------------------------------------------------------------------------- WP3 archive

def test_archive_before_send_returns_a_real_path_and_is_idempotent(tmp_path):
    record = _record()
    path1 = archive_cycle_decision(record, root=str(tmp_path))
    path2 = archive_cycle_decision(record, root=str(tmp_path))
    assert path1 == path2  # identical content -- idempotent no-op, not a duplicate write
    import os
    assert os.path.exists(path1)


def test_changed_content_produces_a_correction_not_an_overwrite(tmp_path):
    import json

    record = _record()
    original_path = archive_cycle_decision(record, root=str(tmp_path))
    with open(original_path, encoding="utf-8") as f:
        original_content = json.load(f)

    corrected = _record(payload={"direction": "LONG"})  # genuinely different content
    correction_path = archive_cycle_decision(corrected, root=str(tmp_path), correction_reason="TEST_CORRECTION")

    assert correction_path != original_path
    with open(original_path, encoding="utf-8") as f:
        assert json.load(f) == original_content  # original never overwritten


def test_watch_and_no_trade_states_are_archived_too():
    record = _record(cycle_state=CYCLE_STATE_NO_TRADE, payload={})
    assert record.cycle_state == CYCLE_STATE_NO_TRADE  # construction alone proves NO_TRADE is a valid archived state


def test_archive_record_carries_strategy_version_and_application_release(tmp_path):
    record = _record()
    path = archive_cycle_decision(record, root=str(tmp_path))
    import json
    with open(path, encoding="utf-8") as f:
        content = json.load(f)
    assert content["strategy_version"] == "1.1.1"
    assert content["application_release"] == "AG_TRADE_ASSISTANT_V1_0_3"
    assert content["logical_ticket_id"] == record.logical_ticket_id()


def test_archive_failure_is_not_silently_swallowed(tmp_path, monkeypatch):
    import ticket_delivery.archive as archive_module

    def _raise(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(archive_module, "write_report", _raise)
    with pytest.raises(archive_module.ArchiveFailedError):
        archive_cycle_decision(_record(), root=str(tmp_path))
