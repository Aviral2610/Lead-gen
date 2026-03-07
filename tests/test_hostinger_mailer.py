"""Tests for src/outreach/hostinger_mailer.py"""

import smtplib
import pytest
from unittest.mock import patch, MagicMock, call

from src.outreach.hostinger_mailer import HostingerMailer, _fill_template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mailer(**kwargs) -> HostingerMailer:
    defaults = dict(
        smtp_host="smtp.hostinger.com",
        smtp_port=587,
        email="sender@example.com",
        password="secret",
        sender_name="Test Sender",
        daily_limit=10,
        delay=0.0,
    )
    defaults.update(kwargs)
    return HostingerMailer(**defaults)


def _mock_smtp():
    """Return a MagicMock that behaves like smtplib.SMTP."""
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# _fill_template
# ---------------------------------------------------------------------------

class TestFillTemplate:
    def test_replaces_known_keys(self):
        result = _fill_template("Hello {{first_name}}!", {"first_name": "Alice"})
        assert result == "Hello Alice!"

    def test_unknown_keys_stay(self):
        result = _fill_template("Hi {{unknown}}!", {"first_name": "Bob"})
        assert "{{unknown}}" in result

    def test_none_value_becomes_empty_string(self):
        result = _fill_template("Dear {{name}}", {"name": None})
        assert result == "Dear "

    def test_multiple_placeholders(self):
        tpl = "{{greeting}} {{name}}, from {{company}}."
        lead = {"greeting": "Hey", "name": "Jane", "company": "Fincept"}
        assert _fill_template(tpl, lead) == "Hey Jane, from Fincept."


# ---------------------------------------------------------------------------
# HostingerMailer.__init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_raises_without_credentials(self):
        with pytest.raises(EnvironmentError, match="HOSTINGER_EMAIL"):
            HostingerMailer(smtp_host="smtp.x.com", smtp_port=587,
                            email="", password="", sender_name="X")

    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("HOSTINGER_EMAIL", "env@example.com")
        monkeypatch.setenv("HOSTINGER_PASSWORD", "envpass")
        m = HostingerMailer.__new__(HostingerMailer)
        HostingerMailer.__init__(m)
        assert m.email == "env@example.com"


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

class TestConnection:
    def test_returns_true_on_success(self):
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            assert mailer.test_connection() is True

    def test_returns_false_on_auth_error(self):
        mailer = make_mailer()
        with patch("smtplib.SMTP", side_effect=smtplib.SMTPAuthenticationError(535, b"bad")):
            assert mailer.test_connection() is False

    def test_uses_ssl_for_port_465(self):
        mailer = make_mailer(smtp_port=465)
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP_SSL", return_value=mock_conn) as mock_ssl:
            mailer.test_connection()
        mock_ssl.assert_called_once()


# ---------------------------------------------------------------------------
# send_one
# ---------------------------------------------------------------------------

class TestSendOne:
    def test_sends_email_returns_true(self):
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            result = mailer.send_one("to@example.com", "Subject", "Body")
        assert result is True
        mock_conn.sendmail.assert_called_once()

    def test_returns_false_on_smtp_error(self):
        mailer = make_mailer()
        with patch("smtplib.SMTP", side_effect=Exception("connection refused")):
            result = mailer.send_one("to@example.com", "Subject", "Body")
        assert result is False

    def test_from_header_contains_sender_name(self):
        mailer = make_mailer(sender_name="Alice")
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            mailer.send_one("to@example.com", "Sub", "Body")
        raw_msg = mock_conn.sendmail.call_args[0][2]
        assert "Alice" in raw_msg

    def test_reply_to_header_set(self):
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            mailer.send_one("to@example.com", "Sub", "Body", reply_to="reply@example.com")
        raw_msg = mock_conn.sendmail.call_args[0][2]
        assert "reply@example.com" in raw_msg


# ---------------------------------------------------------------------------
# send_bulk
# ---------------------------------------------------------------------------

class TestSendBulk:
    def _leads(self, n=3):
        return [
            {"email": f"lead{i}@example.com", "first_name": f"Lead{i}", "business_name": f"Co{i}"}
            for i in range(n)
        ]

    def test_sends_to_all_valid_leads(self):
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            stats = mailer.send_bulk(self._leads(3), "Hi {{first_name}}", "Body {{business_name}}")
        assert stats["sent"] == 3
        assert stats["failed"] == 0

    def test_skips_leads_without_email(self):
        mailer = make_mailer()
        leads = [{"email": "", "first_name": "X"}, {"email": "ok@y.com", "first_name": "Y"}]
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            stats = mailer.send_bulk(leads, "Sub", "Body")
        assert stats["sent"] == 1
        assert stats["skipped"] == 1

    def test_respects_daily_limit(self):
        mailer = make_mailer(daily_limit=2)
        mock_conn = _mock_smtp()
        with patch("smtplib.SMTP", return_value=mock_conn):
            stats = mailer.send_bulk(self._leads(5), "Sub", "Body")
        assert stats["sent"] == 2
        assert stats["skipped"] == 3

    def test_handles_smtp_connection_error(self):
        mailer = make_mailer()
        with patch("smtplib.SMTP", side_effect=Exception("connection refused")):
            stats = mailer.send_bulk(self._leads(2), "Sub", "Body")
        assert stats["sent"] == 0
        assert stats["failed"] == 2

    def test_reconnects_on_disconnect(self):
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        # First sendmail raises disconnect; second (after reconnect) succeeds
        mock_conn.sendmail.side_effect = [
            smtplib.SMTPServerDisconnected(),
            None,
            None,
        ]
        with patch("smtplib.SMTP", return_value=mock_conn):
            stats = mailer.send_bulk(self._leads(2), "Sub", "Body")
        assert stats["sent"] == 2

    def test_template_variables_filled(self):
        import email as email_lib
        mailer = make_mailer()
        mock_conn = _mock_smtp()
        leads = [{"email": "a@b.com", "first_name": "Alice", "business_name": "ACME"}]
        with patch("smtplib.SMTP", return_value=mock_conn):
            mailer.send_bulk(leads, "Hi {{first_name}}", "Dear {{business_name}}")
        raw = mock_conn.sendmail.call_args[0][2]
        # Subject is plaintext; body may be base64-encoded — parse the MIME to verify
        msg = email_lib.message_from_string(raw)
        assert "Alice" in msg["Subject"]
        body = ""
        for part in msg.walk():
            payload = part.get_payload(decode=True)
            if payload:
                body += payload.decode("utf-8", errors="replace")
        assert "ACME" in body
