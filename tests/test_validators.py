"""Unit tests for input validators."""

import pytest
from src.utils.validators import (
    is_valid_email,
    sanitize_email,
    is_valid_url,
    sanitize_url,
    sanitize_phone,
)


class TestEmailValidation:
    def test_valid_emails(self):
        assert is_valid_email("user@example.com")
        assert is_valid_email("first.last@company.co.uk")
        assert is_valid_email("name+tag@domain.org")
        assert is_valid_email("user123@test.io")

    def test_invalid_emails(self):
        assert not is_valid_email("")
        assert not is_valid_email("not-an-email")
        assert not is_valid_email("@domain.com")
        assert not is_valid_email("user@")
        assert not is_valid_email("user@.com")
        assert not is_valid_email(None)
        assert not is_valid_email("user @example.com")

    def test_sanitize_email(self):
        assert sanitize_email("  User@Example.COM  ") == "user@example.com"
        assert sanitize_email("") == ""
        assert sanitize_email("invalid") == ""
        assert sanitize_email("valid@test.com") == "valid@test.com"


class TestURLValidation:
    def test_valid_urls(self):
        assert is_valid_url("https://example.com")
        assert is_valid_url("http://example.com")
        assert is_valid_url("https://sub.domain.example.com/path")

    def test_invalid_urls(self):
        assert not is_valid_url("")
        assert not is_valid_url("not-a-url")
        assert not is_valid_url("ftp://example.com")
        assert not is_valid_url(None)

    def test_ssrf_prevention(self):
        assert not is_valid_url("http://127.0.0.1")
        assert not is_valid_url("http://localhost")
        assert not is_valid_url("http://192.168.1.1")
        assert not is_valid_url("http://10.0.0.1")
        assert not is_valid_url("http://metadata.google.internal")

    def test_require_https(self):
        assert is_valid_url("https://example.com", require_https=True)
        assert not is_valid_url("http://example.com", require_https=True)

    def test_sanitize_url(self):
        assert sanitize_url("example.com") == "https://example.com"
        assert sanitize_url("https://example.com") == "https://example.com"
        assert sanitize_url("") == ""
        assert sanitize_url("localhost") == ""


class TestPhoneSanitization:
    def test_sanitize_phone(self):
        assert sanitize_phone("+1 (555) 123-4567") == "+15551234567"
        assert sanitize_phone("555.123.4567") == "5551234567"
        assert sanitize_phone("") == ""
        assert sanitize_phone("+44 20 7946 0958") == "+442079460958"
