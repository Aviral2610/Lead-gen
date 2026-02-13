"""Input validators for email, URL, and phone data."""

import re
from urllib.parse import urlparse

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)

# Private/reserved IP ranges to block (SSRF prevention)
_PRIVATE_IP_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.", "192.168.", "127.", "0.",
)

_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


def is_valid_email(email: str) -> bool:
    """Validate email format using regex.

    Returns True only for properly formatted email addresses like
    'user@domain.tld'. Rejects partial addresses like 'name@' or '@domain'.
    """
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def sanitize_email(email: str) -> str:
    """Clean and validate an email. Returns empty string if invalid."""
    if not email:
        return ""
    email = email.strip().lower()
    return email if is_valid_email(email) else ""


def is_valid_url(url: str, require_https: bool = False) -> bool:
    """Validate a URL for safe external fetching.

    Rejects private IPs, localhost, non-http(s) schemes, and
    other potentially dangerous URLs (SSRF prevention).
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False

    # Require http or https scheme
    allowed_schemes = ("https",) if require_https else ("http", "https")
    if parsed.scheme not in allowed_schemes:
        return False

    hostname = parsed.hostname or ""
    if not hostname:
        return False

    # Block private/reserved IPs
    if any(hostname.startswith(prefix) for prefix in _PRIVATE_IP_PREFIXES):
        return False

    # Block known internal hostnames
    if hostname.lower() in _BLOCKED_HOSTS:
        return False

    # Must have a valid TLD (at least one dot)
    if "." not in hostname:
        return False

    return True


def sanitize_url(url: str) -> str:
    """Clean and validate a URL. Returns empty string if invalid."""
    if not url:
        return ""
    url = url.strip()
    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url if is_valid_url(url) else ""


def sanitize_phone(phone: str) -> str:
    """Normalize a phone number by keeping only digits and leading +."""
    if not phone:
        return ""
    phone = phone.strip()
    if phone.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", phone[1:])
    return re.sub(r"[^\d]", "", phone)
