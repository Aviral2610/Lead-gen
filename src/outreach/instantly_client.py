"""Instantly.ai API client — pushes enriched, personalized leads
into Instantly campaigns for automated email sequences."""

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff

logger = setup_logger(__name__)

INSTANTLY_BASE = "https://api.instantly.ai/api/v1"


class InstantlyClient:
    """Manage leads and campaigns in Instantly.ai."""

    def __init__(self, config=None):
        self.cfg = config or get_config()

    def _format_lead(self, lead: dict) -> dict | None:
        """Format a lead dict for the Instantly API. Returns None if email is missing."""
        email = lead.get("email", "").strip()
        if not email or "@" not in email:
            logger.warning(
                "Skipping lead '%s' — missing or invalid email.",
                lead.get("business_name", "unknown"),
            )
            return None
        return {
            "email": email,
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "company_name": lead.get("business_name", ""),
            "personalization": lead.get("ai_first_line", ""),
            "website": lead.get("website", ""),
            "custom_variables": {
                "pain_point": lead.get("pain_point", ""),
                "industry": lead.get("category", ""),
                "specific_detail": lead.get("specific_detail", ""),
            },
        }

    @rate_limit(min_interval=1.0)
    @retry_with_backoff(max_retries=3)
    def add_lead(self, lead: dict, campaign_id: str | None = None) -> dict:
        """Add a single lead to an Instantly campaign."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        formatted = self._format_lead(lead)
        if not formatted:
            return {}

        payload = {
            "api_key": self.cfg.instantly_key,
            "campaign_id": cid,
            "skip_if_in_workspace": True,
            "leads": [formatted],
        }

        resp = requests.post(
            f"{INSTANTLY_BASE}/lead/add",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Added lead %s to campaign %s.", formatted["email"], cid)
        return resp.json()

    def add_leads_batch(
        self, leads: list[dict], campaign_id: str | None = None
    ) -> dict:
        """Add multiple leads to an Instantly campaign in a single request."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        formatted = [self._format_lead(lead) for lead in leads]
        formatted = [f for f in formatted if f is not None]

        if not formatted:
            logger.warning("No valid leads to push to Instantly.")
            return {}

        payload = {
            "api_key": self.cfg.instantly_key,
            "campaign_id": cid,
            "skip_if_in_workspace": True,
            "leads": formatted,
        }

        resp = requests.post(
            f"{INSTANTLY_BASE}/lead/add",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("Added %d leads to campaign %s.", len(formatted), cid)
        return resp.json()

    @retry_with_backoff(max_retries=2)
    def list_campaigns(self) -> list[dict]:
        """List all campaigns in the Instantly workspace."""
        resp = requests.get(
            f"{INSTANTLY_BASE}/campaign/list",
            params={"api_key": self.cfg.instantly_key},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_retries=2)
    def get_campaign_summary(self, campaign_id: str | None = None) -> dict:
        """Get summary statistics for a campaign."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        resp = requests.get(
            f"{INSTANTLY_BASE}/analytics/campaign/summary",
            params={"api_key": self.cfg.instantly_key, "campaign_id": cid},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
