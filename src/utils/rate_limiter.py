"""Rate limiter and retry utilities for API calls."""

import logging
import time
from functools import wraps

import requests

logger = logging.getLogger(__name__)


def rate_limit(min_interval: float = 1.0):
    """Decorator that enforces a minimum interval between successive calls."""

    def decorator(func):
        last_called = [0.0]

        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper

    return decorator


# Exceptions that should trigger a retry (transient errors)
_RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

# HTTP status codes that should trigger a retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator that retries on transient errors with exponential backoff.

    Retries on:
      - Network errors (ConnectionError, Timeout)
      - Rate limiting (429)
      - Server errors (500, 502, 503, 504)

    Does NOT retry on:
      - Client errors (400, 401, 403, 404)
      - Validation errors
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code if e.response is not None else 0
                    if status not in _RETRYABLE_STATUS_CODES or attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Retrying %s (HTTP %d, attempt %d/%d, wait %.1fs)",
                        func.__name__, status, attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
                except _RETRYABLE_EXCEPTIONS as e:
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Retrying %s (%s, attempt %d/%d, wait %.1fs)",
                        func.__name__, type(e).__name__, attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
                except Exception:
                    # Non-retryable exceptions (auth errors, validation, etc.)
                    raise

        return wrapper

    return decorator
