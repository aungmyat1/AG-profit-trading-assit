"""WP4.4 catch-up + WP6 retry-policy tests. No real sleeping anywhere -- every time
value is an injected datetime/float, never wall-clock.
"""
from __future__ import annotations

import datetime as dt

import pytest

from ticket_delivery.policy import (
    REASON_CATCH_UP_POLICY_NOT_CONFIGURED,
    REASON_MAX_ATTEMPTS_EXHAUSTED,
    REASON_OUTSIDE_CATCH_UP_WINDOW,
    REASON_PREMATURE,
    REASON_RETRY_POLICY_NOT_CONFIGURED,
    CatchUpPolicy,
    RetryPolicy,
)

UTC = dt.timezone.utc
CHECKPOINT = dt.datetime(2026, 9, 8, 7, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- catch-up / time gates

def test_premature_run_before_checkpoint_is_refused():
    policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(hours=2))
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=CHECKPOINT - dt.timedelta(minutes=1))
    assert decision.allowed is False
    assert decision.reason_code == REASON_PREMATURE


def test_exact_checkpoint_boundary_is_allowed_when_configured():
    policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(hours=2))
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=CHECKPOINT)
    assert decision.allowed is True


def test_valid_configured_catch_up_within_bound_is_allowed():
    policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(hours=2))
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=CHECKPOINT + dt.timedelta(hours=1))
    assert decision.allowed is True


def test_catch_up_outside_configured_bound_is_refused():
    policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(hours=2))
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=CHECKPOINT + dt.timedelta(hours=3))
    assert decision.allowed is False
    assert decision.reason_code == REASON_OUTSIDE_CATCH_UP_WINDOW


def test_missing_catch_up_configuration_fails_closed():
    """No production default -- the zero-argument construction represents 'unsigned',
    and must refuse every evaluation, even one at the exact checkpoint."""
    policy = CatchUpPolicy()
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=CHECKPOINT)
    assert decision.allowed is False
    assert decision.reason_code == REASON_CATCH_UP_POLICY_NOT_CONFIGURED


def test_successful_subsequent_cycle_recovery_is_a_normal_configured_catch_up():
    """A 'missed checkpoint, next cycle recovers it' scenario is just a catch-up
    evaluation within the configured bound -- no separate mechanism needed."""
    policy = CatchUpPolicy(max_catch_up_age=dt.timedelta(hours=4))
    next_cycle_time = CHECKPOINT + dt.timedelta(hours=3, minutes=30)
    decision = policy.evaluate(checkpoint=CHECKPOINT, now=next_cycle_time)
    assert decision.allowed is True


# --------------------------------------------------------------------------- retry policy

def test_deterministic_backoff_calculation():
    policy = RetryPolicy(max_attempts=5, base_delay_seconds=2.0, max_delay_seconds=30.0)
    assert policy.next_delay(1) == pytest.approx(2.0)
    assert policy.next_delay(2) == pytest.approx(4.0)
    assert policy.next_delay(3) == pytest.approx(8.0)
    assert policy.next_delay(4) == pytest.approx(16.0)
    assert policy.next_delay(5) == pytest.approx(30.0)  # capped


def test_successful_bounded_retry_is_permitted_within_max_attempts():
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0)
    decision = policy.should_retry(attempt_number=2, classification="RETRYABLE")
    assert decision.should_retry is True
    assert decision.delay_seconds == pytest.approx(2.0)


def test_maximum_attempts_exhausted_refuses_further_retry():
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0)
    decision = policy.should_retry(attempt_number=3, classification="RETRYABLE")
    assert decision.should_retry is False
    assert decision.reason_code == REASON_MAX_ATTEMPTS_EXHAUSTED


def test_terminal_classification_is_never_retried_regardless_of_configuration():
    policy = RetryPolicy(max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=10.0)
    decision = policy.should_retry(attempt_number=1, classification="TERMINAL")
    assert decision.should_retry is False


def test_ambiguous_classification_is_never_retried_regardless_of_configuration():
    policy = RetryPolicy(max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=10.0)
    decision = policy.should_retry(attempt_number=1, classification="AMBIGUOUS")
    assert decision.should_retry is False


def test_missing_retry_configuration_fails_closed():
    policy = RetryPolicy()
    decision = policy.should_retry(attempt_number=1, classification="RETRYABLE")
    assert decision.should_retry is False
    assert decision.reason_code == REASON_RETRY_POLICY_NOT_CONFIGURED


def test_next_delay_raises_when_not_configured_rather_than_guessing():
    policy = RetryPolicy()
    with pytest.raises(ValueError):
        policy.next_delay(1)


# --------------------------------------------------------------------------- signed contract (OWNER_APPROVED 2026-09-08)

SIGNED_RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300)
SIGNED_CATCH_UP_POLICY = CatchUpPolicy(max_catch_up_age=dt.timedelta(minutes=60))


def test_signed_contract_attempt_1_is_the_initial_attempt_and_permits_retry():
    """delivery_max_attempts=3 is the TOTAL attempt count INCLUDING the initial
    attempt (documented interpretation, not a new choice -- see
    scheduler_integration._parse_policy()'s docstring)."""
    decision = SIGNED_RETRY_POLICY.should_retry(attempt_number=1, classification="RETRYABLE")
    assert decision.should_retry is True
    assert decision.delay_seconds == pytest.approx(30.0)  # first retry delay


def test_signed_contract_second_retry_delay_is_60_seconds():
    decision = SIGNED_RETRY_POLICY.should_retry(attempt_number=2, classification="RETRYABLE")
    assert decision.should_retry is True
    assert decision.delay_seconds == pytest.approx(60.0)


def test_signed_contract_third_attempt_exhausts_the_maximum_of_three_total():
    decision = SIGNED_RETRY_POLICY.should_retry(attempt_number=3, classification="RETRYABLE")
    assert decision.should_retry is False
    assert decision.reason_code == REASON_MAX_ATTEMPTS_EXHAUSTED


def test_signed_contract_delay_never_exceeds_the_300_second_cap():
    # A hypothetical further attempt (beyond the 3-attempt bound) would compute
    # 30 * 2^3 = 240s -- still under the cap; attempt 5 (30*2^4=480s) proves the cap.
    assert SIGNED_RETRY_POLICY.next_delay(5) == pytest.approx(300.0)


def test_signed_contract_terminal_failure_is_never_retried():
    decision = SIGNED_RETRY_POLICY.should_retry(attempt_number=1, classification="TERMINAL")
    assert decision.should_retry is False


def test_signed_contract_ambiguous_outcome_is_never_retried():
    decision = SIGNED_RETRY_POLICY.should_retry(attempt_number=1, classification="AMBIGUOUS")
    assert decision.should_retry is False


def test_signed_contract_expired_ticket_is_never_delivered(tmp_path):
    """Expiry is the pre-existing delivery_store.claim_for_delivery()/DeliveryRecord.is_expired()
    contract (Addendum 1, already tested at the primitive layer) -- this task's signed
    retry policy does not introduce a new expiry source. Re-proven here directly against
    the primitive to keep this file's "signed contract" section self-contained."""
    from ticket_delivery.delivery_store import TicketDeliveryStore

    store = TicketDeliveryStore(state_dir=str(tmp_path / "delivery"))
    checkpoint = dt.datetime(2026, 9, 8, 7, 45, tzinfo=UTC)
    store.ensure_ready_to_deliver(
        logical_ticket_id="ST|1.1.1|EURUSD|ASIAN_LONDON|2026-09-08", strategy_id="ST",
        strategy_version="1.1.1", application_release="REL", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-08", payload_hash="hash1",
        expires_at=checkpoint + dt.timedelta(hours=1), now=checkpoint,
    )
    claim = store.claim_for_delivery(
        "ST|1.1.1|EURUSD|ASIAN_LONDON|2026-09-08", now=checkpoint + dt.timedelta(hours=2),
    )
    assert claim.success is False


def test_no_real_sleeping_anywhere_in_this_module():
    """Every delay in this file is a pure computation over injected values -- proven by
    static source inspection that time.sleep is never imported or called anywhere in
    the policy module itself."""
    import inspect

    import ticket_delivery.policy as policy_mod
    source = inspect.getsource(policy_mod)
    assert "time.sleep" not in source
    assert "import time" not in source
