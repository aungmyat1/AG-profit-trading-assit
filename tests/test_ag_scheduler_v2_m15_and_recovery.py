import datetime as dt

import pytest

from ag_scheduler_v2.cycle_identity import CATCH_UP, DUPLICATE_SKIP, LIVE_WINDOW, CompletedCycleStore, cycle_id
from ag_scheduler_v2.m15_clock import (
    DATA_STALE, BarSettlementPolicy, confirm_bar_available, next_m15_close_utc, previous_m15_close_utc,
)
from ag_scheduler_v2.recovery import expected_m15_cycles, reconcile_on_boot


def _utc(y, mo, d, h, mi, s=0):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=dt.timezone.utc)


class TestM15Events:
    @pytest.mark.parametrize("now,expected_close", [
        ((7, 0, 0), (7, 15)),
        ((7, 14, 59), (7, 15)),
        ((7, 15, 0), (7, 30)),
        ((7, 29, 0), (7, 30)),
        ((7, 44, 1), (7, 45)),
    ])
    def test_next_m15_close(self, now, expected_close):
        ts = _utc(2026, 9, 10, *now)
        result = next_m15_close_utc(ts)
        assert (result.hour, result.minute) == expected_close

    def test_previous_m15_close_on_exact_boundary(self):
        ts = _utc(2026, 9, 10, 7, 15, 0)
        assert previous_m15_close_utc(ts) == _utc(2026, 9, 10, 7, 0)

    def test_confirm_bar_available_true_once_provider_caught_up(self):
        policy = BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60)
        bar_close = _utc(2026, 9, 10, 7, 15)
        result = confirm_bar_available(
            bar_close_utc=bar_close, provider_latest_closed_bar_utc=bar_close,
            now_utc=bar_close + dt.timedelta(seconds=6), policy=policy,
        )
        assert result.available

    def test_confirm_bar_available_false_before_settlement_even_if_wallclock_passed(self):
        policy = BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60)
        bar_close = _utc(2026, 9, 10, 7, 15)
        result = confirm_bar_available(
            bar_close_utc=bar_close, provider_latest_closed_bar_utc=None,
            now_utc=bar_close + dt.timedelta(seconds=30), policy=policy,
        )
        assert not result.available
        assert result.reason_code == "AWAITING_SETTLEMENT"

    def test_confirm_bar_available_stale_after_max_wait(self):
        policy = BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60)
        bar_close = _utc(2026, 9, 10, 7, 15)
        result = confirm_bar_available(
            bar_close_utc=bar_close, provider_latest_closed_bar_utc=None,
            now_utc=bar_close + dt.timedelta(seconds=61), policy=policy,
        )
        assert not result.available
        assert result.reason_code == DATA_STALE


class TestExactlyOnce:
    def test_cycle_id_deterministic(self):
        bar_close = _utc(2026, 9, 10, 8, 15)
        a = cycle_id(strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close)
        b = cycle_id(strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close)
        assert a == b == "ST_SESSION_SWEEP_CONTINUATION_V1|EURUSD|ASIAN_LONDON|2026-09-10T08:15:00Z"

    def test_first_processing_is_live_window(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        classification = store.classify(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, is_recovered=False)
        assert classification == LIVE_WINDOW

    def test_recovered_missing_is_catch_up(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        classification = store.classify(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, is_recovered=True)
        assert classification == CATCH_UP

    def test_already_completed_is_duplicate_skip(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        store.mark_completed(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, observation_mode=LIVE_WINDOW, now_utc=bar_close)
        classification = store.classify(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, is_recovered=False)
        assert classification == DUPLICATE_SKIP

    def test_observation_mode_immutable_once_written(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        first = store.mark_completed(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, observation_mode=CATCH_UP, now_utc=bar_close)
        second = store.mark_completed(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=bar_close, observation_mode=LIVE_WINDOW, now_utc=bar_close)
        assert first.observation_mode == CATCH_UP
        assert second.observation_mode == CATCH_UP  # never overwritten, even by a "later" LIVE_WINDOW attempt

    def test_restart_before_session_no_completed_cycles(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        assert store.all_completed() == {}


class TestRecovery:
    def test_restart_during_session_reconstructs_missed_bars_as_catch_up(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        window_start = _utc(2026, 9, 10, 7, 0)
        window_end = _utc(2026, 9, 10, 8, 0)
        expected = expected_m15_cycles(strategy_id="S", symbols=("EURUSD",), session_pair="ASIAN_LONDON", window_start_utc=window_start, window_end_utc=window_end)
        assert [c.bar_close_utc.hour * 60 + c.bar_close_utc.minute for c in expected] == [7 * 60, 7 * 60 + 15, 7 * 60 + 30, 7 * 60 + 45]

        # Simulate a crash: only the first cycle was ever completed live.
        store.mark_completed(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=expected[0].bar_close_utc, observation_mode=LIVE_WINDOW, now_utc=expected[0].bar_close_utc)

        restart_now = _utc(2026, 9, 10, 7, 50)
        outcome = reconcile_on_boot(expected=expected, store=store, now_utc=restart_now)

        assert outcome.execution_allowed is False
        assert {c.bar_close_utc.minute for c in outcome.reconstructed} == {15, 30, 45}
        assert len(outcome.already_completed) == 1
        for c in outcome.reconstructed:
            record = store.get(cycle_id(strategy_id="S", symbol="EURUSD", session_pair="ASIAN_LONDON", bar_close_utc=c.bar_close_utc))
            assert record.observation_mode == CATCH_UP

    def test_restart_after_full_missed_session_reconstructs_all(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        window_start = _utc(2026, 9, 10, 7, 0)
        window_end = _utc(2026, 9, 10, 7, 30)
        expected = expected_m15_cycles(strategy_id="S", symbols=("EURUSD", "GBPUSD"), session_pair="ASIAN_LONDON", window_start_utc=window_start, window_end_utc=window_end)
        outcome = reconcile_on_boot(expected=expected, store=store, now_utc=_utc(2026, 9, 10, 8, 0))
        assert len(outcome.reconstructed) == 4  # 2 symbols x 2 bars
        assert all(not c.bar_close_utc > _utc(2026, 9, 10, 8, 0) for c in outcome.reconstructed)

    def test_future_bar_not_yet_due_is_not_manufactured_as_catch_up(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        expected = expected_m15_cycles(strategy_id="S", symbols=("EURUSD",), session_pair="ASIAN_LONDON", window_start_utc=_utc(2026, 9, 10, 7, 0), window_end_utc=_utc(2026, 9, 10, 8, 0))
        # "now" is before any of these bars have closed.
        outcome = reconcile_on_boot(expected=expected, store=store, now_utc=_utc(2026, 9, 10, 6, 55))
        assert outcome.reconstructed == tuple()
        assert outcome.already_completed == tuple()

    def test_no_stale_execution_path_exists_on_reconstructed_evidence(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        expected = expected_m15_cycles(strategy_id="S", symbols=("EURUSD",), session_pair="ASIAN_LONDON", window_start_utc=_utc(2026, 9, 10, 7, 0), window_end_utc=_utc(2026, 9, 10, 7, 15))
        outcome = reconcile_on_boot(expected=expected, store=store, now_utc=_utc(2026, 9, 10, 9, 0))
        assert outcome.execution_allowed is False
        assert not hasattr(outcome, "execute")
