"""Tests for src/utils/rate_limiter.py"""

import time
import pytest
from unittest.mock import patch, MagicMock

from src.utils.rate_limiter import rate_limit, retry_with_backoff


# ---------------------------------------------------------------------------
# rate_limit
# ---------------------------------------------------------------------------

def test_rate_limit_returns_correct_value():
    @rate_limit(min_interval=0.0)
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_rate_limit_preserves_function_name():
    @rate_limit(min_interval=0.0)
    def my_function():
        pass

    assert my_function.__name__ == "my_function"


def test_rate_limit_enforces_minimum_interval():
    """Second call must be delayed by at least min_interval."""
    call_times = []

    @rate_limit(min_interval=0.05)
    def record():
        call_times.append(time.monotonic())

    record()
    record()
    assert call_times[1] - call_times[0] >= 0.04  # tiny margin for CI jitter


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------

def test_retry_returns_value_on_first_success():
    @retry_with_backoff(max_retries=3, base_delay=0.0)
    def always_ok():
        return "success"

    with patch("time.sleep"):
        assert always_ok() == "success"


def test_retry_preserves_function_name():
    @retry_with_backoff(max_retries=2, base_delay=0.0)
    def my_func():
        pass

    assert my_func.__name__ == "my_func"


def test_retry_retries_on_transient_exception():
    attempts = [0]

    @retry_with_backoff(max_retries=3, base_delay=0.0)
    def flaky():
        attempts[0] += 1
        if attempts[0] < 3:
            raise ValueError("transient")
        return "ok"

    with patch("time.sleep"):
        result = flaky()

    assert result == "ok"
    assert attempts[0] == 3


def test_retry_raises_after_max_retries_exhausted():
    @retry_with_backoff(max_retries=2, base_delay=0.0)
    def always_fails():
        raise RuntimeError("permanent failure")

    with patch("time.sleep"), pytest.raises(RuntimeError, match="permanent failure"):
        always_fails()


def test_retry_total_call_count_equals_max_retries_plus_one():
    call_count = [0]

    @retry_with_backoff(max_retries=2, base_delay=0.0)
    def counter():
        call_count[0] += 1
        raise ValueError("error")

    with patch("time.sleep"):
        with pytest.raises(ValueError):
            counter()

    assert call_count[0] == 3  # 1 initial + 2 retries


def test_retry_sleeps_between_attempts():
    """Verify exponential backoff sleep is called."""

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    def always_fails():
        raise ValueError("boom")

    with patch("time.sleep") as mock_sleep, pytest.raises(ValueError):
        always_fails()

    # Should sleep twice (after attempt 0 and attempt 1)
    assert mock_sleep.call_count == 2
    # First sleep: 2.0 * 2^0 = 2.0s, second: 2.0 * 2^1 = 4.0s
    sleep_args = [c[0][0] for c in mock_sleep.call_args_list]
    assert sleep_args[0] == pytest.approx(2.0)
    assert sleep_args[1] == pytest.approx(4.0)
