"""Hostinger SMTP mailer — sends cold emails directly via your Hostinger mailbox.

No third-party outreach tools needed. Uses Python's stdlib smtplib + email.

Hostinger SMTP settings:
  Host : smtp.hostinger.com
  Port : 587  (STARTTLS)  — recommended
        465  (SSL/TLS)    — alternative
  Auth : your full Hostinger email + password

Set these in your .env:
  HOSTINGER_SMTP_HOST=smtp.hostinger.com
  HOSTINGER_SMTP_PORT=587
  HOSTINGER_EMAIL=you@yourdomain.com
  HOSTINGER_PASSWORD=your_email_password
  HOSTINGER_SENDER_NAME=Your Name
"""

import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


class HostingerMailer:
    """Send emails via Hostinger SMTP.

    Args:
        smtp_host:    SMTP server (default: smtp.hostinger.com).
        smtp_port:    Port — 587 for STARTTLS, 465 for SSL (default: 587).
        email:        Your full Hostinger email address.
        password:     Your Hostinger email password.
        sender_name:  Display name in the From header.
        daily_limit:  Max emails to send per session (safety cap, default 50).
        delay:        Seconds to wait between sends (default 60 — be polite).
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        sender_name: Optional[str] = None,
        daily_limit: int = 50,
        delay: float = 60.0,
    ):
        self.smtp_host = smtp_host or _env("HOSTINGER_SMTP_HOST", "smtp.hostinger.com")
        self.smtp_port = smtp_port or int(_env("HOSTINGER_SMTP_PORT", "587"))
        self.email = email or _env("HOSTINGER_EMAIL")
        self.password = password or _env("HOSTINGER_PASSWORD")
        self.sender_name = sender_name or _env("HOSTINGER_SENDER_NAME", self.email)
        self.daily_limit = daily_limit
        self.delay = delay

        if not self.email or not self.password:
            raise EnvironmentError(
                "HOSTINGER_EMAIL and HOSTINGER_PASSWORD must be set in .env"
            )

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> smtplib.SMTP:
        """Open an authenticated SMTP connection. Caller must close it."""
        if self.smtp_port == 465:
            conn = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
        else:
            conn = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
            conn.ehlo()
            conn.starttls()
            conn.ehlo()

        conn.login(self.email, self.password)
        logger.info("SMTP connected to %s:%d as %s", self.smtp_host, self.smtp_port, self.email)
        return conn

    def test_connection(self) -> bool:
        """Verify SMTP credentials work. Returns True on success."""
        try:
            conn = self._connect()
            conn.quit()
            logger.info("SMTP connection test passed.")
            return True
        except Exception as e:
            logger.error("SMTP connection test failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Message builder
    # ------------------------------------------------------------------

    def _build_message(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
    ) -> MIMEMultipart:
        """Build a plain-text MIME message."""
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.sender_name} <{self.email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to

        # Plain-text only — much better deliverability than HTML
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return msg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_one(
        self,
        to_email: str,
        subject: str,
        body: str,
        reply_to: Optional[str] = None,
    ) -> bool:
        """Send a single email. Returns True on success."""
        msg = self._build_message(to_email, subject, body, reply_to)
        try:
            conn = self._connect()
            conn.sendmail(self.email, to_email, msg.as_string())
            conn.quit()
            logger.info("Sent to %s — subject: %s", to_email, subject)
            return True
        except Exception as e:
            logger.error("Failed to send to %s: %s", to_email, e)
            return False

    def send_bulk(
        self,
        leads: list[dict],
        subject_template: str,
        body_template: str,
        reply_to: Optional[str] = None,
    ) -> dict:
        """Send personalised emails to a list of leads.

        Templates use {{variable}} placeholders filled from each lead dict.
        Available variables: any key in the lead dict, e.g.
            {{first_name}}, {{business_name}}, {{ai_first_line}}, {{pain_point}}.

        Args:
            leads:            List of lead dicts (must have 'email' key).
            subject_template: Email subject with {{placeholders}}.
            body_template:    Email body with {{placeholders}}.
            reply_to:         Optional Reply-To address.

        Returns:
            {"sent": int, "failed": int, "skipped": int}
        """
        sent = failed = skipped = 0

        try:
            conn = self._connect()
        except Exception as e:
            logger.error("Could not open SMTP connection: %s", e)
            return {"sent": 0, "failed": len(leads), "skipped": 0}

        for i, lead in enumerate(leads):
            if sent >= self.daily_limit:
                logger.warning(
                    "Daily send limit (%d) reached. Stopping.", self.daily_limit
                )
                skipped += len(leads) - i
                break

            to_email = lead.get("email", "").strip()
            if not to_email or "@" not in to_email:
                logger.warning("Skipping lead with invalid email: %s", lead)
                skipped += 1
                continue

            subject = _fill_template(subject_template, lead)
            body = _fill_template(body_template, lead)
            msg = self._build_message(to_email, subject, body, reply_to)

            try:
                conn.sendmail(self.email, to_email, msg.as_string())
                logger.info("[%d/%d] Sent → %s", i + 1, len(leads), to_email)
                sent += 1
            except smtplib.SMTPRecipientsRefused:
                logger.warning("Recipient refused: %s", to_email)
                failed += 1
            except smtplib.SMTPServerDisconnected:
                logger.warning("SMTP disconnected, reconnecting…")
                try:
                    conn = self._connect()
                    conn.sendmail(self.email, to_email, msg.as_string())
                    sent += 1
                except Exception as e2:
                    logger.error("Reconnect-send failed for %s: %s", to_email, e2)
                    failed += 1
            except Exception as e:
                logger.error("Send failed for %s: %s", to_email, e)
                failed += 1

            if i < len(leads) - 1:
                time.sleep(self.delay)

        try:
            conn.quit()
        except Exception:
            pass

        logger.info(
            "Bulk send complete — sent: %d, failed: %d, skipped: %d",
            sent, failed, skipped,
        )
        return {"sent": sent, "failed": failed, "skipped": skipped}


def _fill_template(template: str, lead: dict) -> str:
    """Replace {{key}} placeholders in a template with lead values."""
    result = template
    for key, value in lead.items():
        result = result.replace(f"{{{{{key}}}}}", str(value) if value else "")
    return result
