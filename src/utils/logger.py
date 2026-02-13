"""Centralized logging with structured context and secrets masking."""

import logging
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Patterns to mask in log output (prevents credential leakage)
_SECRET_PATTERNS = [
    (re.compile(r'(api_key["\']?\s*[:=]\s*["\']?)[^\s"\'&]+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(Authorization["\']?\s*[:=]\s*Bearer\s+)\S+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(X-KEY["\']?\s*[:=]\s*["\']?)\S+', re.IGNORECASE), r'\1***'),
    (re.compile(r'(sk-[a-zA-Z0-9]{3})[a-zA-Z0-9]+'), r'\1***'),
]


class SecretsMaskingFilter(logging.Filter):
    """Filter that redacts API keys and tokens from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, replacement in _SECRET_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        if record.args and isinstance(record.args, tuple):
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for pattern, replacement in _SECRET_PATTERNS:
                        arg = pattern.sub(replacement, arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True


def setup_logger(name: str, log_file: str | None = None) -> logging.Logger:
    """Create a logger with console and optional file output.

    Includes secrets masking filter to prevent credential leakage.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add secrets masking filter
    secrets_filter = SecretsMaskingFilter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(secrets_filter)
    logger.addHandler(console)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(secrets_filter)
        logger.addHandler(file_handler)

    return logger


@contextmanager
def log_duration(logger: logging.Logger, operation: str, **extra):
    """Context manager that logs the duration of an operation.

    Usage:
        with log_duration(logger, "enrich_lead", email=lead["email"]):
            result = enricher.enrich(lead)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        parts = [f"{operation} completed in {elapsed_ms:.0f}ms"]
        for k, v in extra.items():
            parts.append(f"{k}={v}")
        logger.info(" | ".join(parts))
