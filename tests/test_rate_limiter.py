"""Tests for rate limiting and retry utilities."""

import time
import pytest

from src.utils.rate_limiter import rate_limit, retry_with_backoff


def test_rate_limit_enforces_interval():
    call_times = []

    @rate_limit(min_interval=0.1)
    def fn():
        call_times.append(time.time())

    fn()
    fn()
    fn()

    assert len(call_times) == 3
    # Gap between consecutive calls must be >= 0.1 seconds
    assert call_times[1] - call_times[0] >= 0.09
    assert call_times[2] - call_times[1] >= 0.09


def test_rate_limit_passes_return_value():
    @rate_limit(min_interval=0.0)
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_retry_succeeds_on_first_try():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def fn():
        calls.append(1)
        return "ok"

    result = fn()
    assert result == "ok"
    assert len(calls) == 1


def test_retry_retries_on_exception():
    attempts = []

    @retry_with_backoff(max_retries=2, base_delay=0.01)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not ready")
        return "done"

    result = flaky()
    assert result == "done"
    assert len(attempts) == 3


def test_retry_raises_after_max_retries():
    @retry_with_backoff(max_retries=2, base_delay=0.01)
    def always_fails():
        raise RuntimeError("always bad")

    with pytest.raises(RuntimeError, match="always bad"):
        always_fails()


def test_retry_preserves_function_name():
    @retry_with_backoff(max_retries=1)
    def my_function():
        pass

    assert my_function.__name__ == "my_function"
