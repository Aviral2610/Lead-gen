"""Simple rate limiter for API calls."""

import time
from functools import wraps


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


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator that retries on exception with exponential backoff."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)

        return wrapper

    return decorator
