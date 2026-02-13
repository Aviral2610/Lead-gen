#!/usr/bin/env python3
"""Health check script — validates API keys and connectivity.

Run this before starting a pipeline to catch configuration issues early.

Usage:
    python scripts/health_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("health_check")


def check_apify(config) -> bool:
    """Verify Apify API key is valid."""
    try:
        resp = requests.get(
            f"{config.apify_base_url}/users/me",
            headers={"Authorization": f"Bearer {config.apify_token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[OK] Apify: authenticated successfully.")
            return True
        logger.error("[FAIL] Apify: HTTP %d", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.error("[FAIL] Apify: %s", type(e).__name__)
        return False


def check_openai(config) -> bool:
    """Verify OpenAI API key is valid."""
    try:
        resp = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {config.openai_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[OK] OpenAI: authenticated successfully.")
            return True
        logger.error("[FAIL] OpenAI: HTTP %d", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.error("[FAIL] OpenAI: %s", type(e).__name__)
        return False


def check_anthropic(config) -> bool:
    """Verify Anthropic API key format (starts with sk-ant-)."""
    key = config.anthropic_key
    if key and (key.startswith("sk-ant-") or key.startswith("sk-")):
        logger.info("[OK] Anthropic: key format valid.")
        return True
    logger.error("[FAIL] Anthropic: key format invalid.")
    return False


def check_prospeo(config) -> bool:
    """Verify Prospeo API key."""
    try:
        resp = requests.get(
            "https://api.prospeo.io/email-verifier",
            params={"email": "test@example.com"},
            headers={"X-KEY": config.prospeo_key},
            timeout=10,
        )
        if resp.status_code in (200, 400):
            logger.info("[OK] Prospeo: API key accepted.")
            return True
        logger.error("[FAIL] Prospeo: HTTP %d", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.error("[FAIL] Prospeo: %s", type(e).__name__)
        return False


def check_hunter(config) -> bool:
    """Verify Hunter.io API key."""
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/account",
            params={"api_key": config.hunter_key},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[OK] Hunter.io: authenticated successfully.")
            return True
        logger.error("[FAIL] Hunter.io: HTTP %d", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.error("[FAIL] Hunter.io: %s", type(e).__name__)
        return False


def check_instantly(config) -> bool:
    """Verify Instantly API key."""
    try:
        resp = requests.get(
            f"{config.instantly_base_url}/campaign/list",
            params={"api_key": config.instantly_key},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[OK] Instantly: authenticated successfully.")
            return True
        logger.error("[FAIL] Instantly: HTTP %d", resp.status_code)
        return False
    except requests.RequestException as e:
        logger.error("[FAIL] Instantly: %s", type(e).__name__)
        return False


def main():
    logger.info("=== API Health Check ===")
    try:
        config = get_config()
    except EnvironmentError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    checks = [
        ("Apify", check_apify),
        ("OpenAI", check_openai),
        ("Anthropic", check_anthropic),
        ("Prospeo", check_prospeo),
        ("Hunter.io", check_hunter),
        ("Instantly", check_instantly),
    ]

    results = {}
    for name, check_fn in checks:
        results[name] = check_fn(config)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info("=== Results: %d/%d checks passed ===", passed, total)

    if passed < total:
        failed = [name for name, ok in results.items() if not ok]
        logger.warning("Failed checks: %s", ", ".join(failed))
        sys.exit(1)
    else:
        logger.info("All API keys validated successfully.")


if __name__ == "__main__":
    main()
