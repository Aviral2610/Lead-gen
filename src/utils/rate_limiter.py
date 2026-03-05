"""Simple rate limiter for API calls."""

import logging
import time
import threading
from functools import wraps

logger = logging.getLogger(__name__)


def rate_limit(min_interval: float = 1.0):
    """Decorator that enforces a minimum interval between successive calls.

    Thread-safe: uses a Lock so concurrent callers don't race past the check.
    """

    def decorator(func):
        last_called = [0.0]
        lock = threading.Lock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                elapsed = time.time() - last_called[0]
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper

    return decorator


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator that retries on exception with exponential backoff."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        func.__qualname__, attempt + 1, max_retries, exc, delay,
                    )
                    time.sleep(delay)

        return wrapper

    return decorator
