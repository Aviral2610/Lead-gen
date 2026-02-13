"""Global suppression list manager — ensures compliance with CAN-SPAM,
GDPR, and CASL by preventing emails to opted-out addresses.

Maintains a local file-based suppression list synced from Google Sheets.
Every lead MUST be checked against this list before being pushed to outreach.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_SUPPRESSION_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "suppression_list.json"


class SuppressionManager:
    """Manages a global suppression list of emails that must never be contacted.

    Sources of suppression:
      - Manual unsubscribe requests
      - Instantly unsubscribe webhook events
      - Hard bounces
      - Spam complaints
      - Previous campaign opt-outs
    """

    def __init__(self, filepath: str | Path | None = None):
        self.filepath = Path(filepath) if filepath else DEFAULT_SUPPRESSION_FILE
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}
        self._loaded_at: float = 0
        self._load()

    def _load(self):
        """Load suppression list from disk."""
        if self.filepath.exists():
            try:
                with open(self.filepath) as f:
                    data = json.load(f)
                self._cache = {k.lower(): v for k, v in data.items()}
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load suppression list: %s", e)
                self._cache = {}
        else:
            self._cache = {}
        self._loaded_at = time.time()
        logger.info("Suppression list loaded: %d entries.", len(self._cache))

    def _save(self):
        """Persist suppression list to disk."""
        try:
            with open(self.filepath, "w") as f:
                json.dump(self._cache, f, indent=2, default=str)
        except OSError as e:
            logger.error("Failed to save suppression list: %s", e)

    def is_suppressed(self, email: str) -> bool:
        """Check if an email is on the suppression list."""
        if not email:
            return False
        return email.strip().lower() in self._cache

    def add(self, email: str, reason: str, source: str = "manual"):
        """Add an email to the suppression list.

        Args:
            email: The email address to suppress.
            reason: Why this email was suppressed (unsubscribe, bounce, spam_complaint).
            source: Where the suppression originated (instantly, manual, webhook).
        """
        key = email.strip().lower()
        if key in self._cache:
            return  # Already suppressed

        self._cache[key] = {
            "reason": reason,
            "source": source,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        logger.info("Suppressed email %s (reason=%s, source=%s).", key, reason, source)

    def remove(self, email: str):
        """Remove an email from the suppression list (use with caution)."""
        key = email.strip().lower()
        if key in self._cache:
            del self._cache[key]
            self._save()
            logger.info("Removed %s from suppression list.", key)

    def filter_leads(self, leads: list[dict], email_key: str = "email") -> tuple[list[dict], list[dict]]:
        """Split leads into allowed and suppressed lists.

        Returns:
            (allowed_leads, suppressed_leads)
        """
        allowed = []
        suppressed = []
        for lead in leads:
            email = lead.get(email_key, "")
            if self.is_suppressed(email):
                suppressed.append(lead)
            else:
                allowed.append(lead)

        if suppressed:
            logger.info(
                "Suppression filter: %d allowed, %d suppressed out of %d leads.",
                len(allowed), len(suppressed), len(leads),
            )
        return allowed, suppressed

    def bulk_add(self, entries: list[dict]):
        """Add multiple entries at once.

        Each entry should have keys: email, reason, source.
        """
        count = 0
        for entry in entries:
            email = entry.get("email", "")
            if email and not self.is_suppressed(email):
                self.add(
                    email=email,
                    reason=entry.get("reason", "bulk_import"),
                    source=entry.get("source", "manual"),
                )
                count += 1
        logger.info("Bulk added %d new suppressions.", count)

    @property
    def count(self) -> int:
        return len(self._cache)

    def export(self) -> list[dict]:
        """Export the full suppression list for auditing."""
        return [
            {"email": email, **meta}
            for email, meta in sorted(self._cache.items())
        ]
