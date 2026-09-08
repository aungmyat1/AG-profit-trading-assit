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
