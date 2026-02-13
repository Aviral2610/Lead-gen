"""Instantly.ai API client — pushes enriched, personalized leads
into Instantly campaigns for automated email sequences."""

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff
from src.utils.validators import is_valid_email

logger = setup_logger(__name__)


class InstantlyClient:
    """Manage leads and campaigns in Instantly.ai."""

    def __init__(self, config=None):
        self.cfg = config or get_config()

    def _base_url(self) -> str:
        return self.cfg.instantly_base_url

    def _format_lead(self, lead: dict) -> dict:
        """Format a lead dict for the Instantly API."""
        return {
            "email": lead["email"],
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
        if not is_valid_email(lead.get("email", "")):
            raise ValueError(f"Invalid email: {lead.get('email', '')}")

        cid = campaign_id or self.cfg.instantly_campaign_id
        payload = {
            "api_key": self.cfg.instantly_key,
            "campaign_id": cid,
            "skip_if_in_workspace": True,
            "leads": [self._format_lead(lead)],
        }

        resp = requests.post(
            f"{self._base_url()}/lead/add",
            json=payload,
            timeout=self.cfg.api_timeout_short,
        )
        resp.raise_for_status()
        logger.info("Added lead %s to campaign %s.", lead["email"], cid)
        return resp.json()

    def add_leads_batch(
        self, leads: list[dict], campaign_id: str | None = None
    ) -> dict:
        """Add multiple leads to an Instantly campaign in a single request.

        Filters out leads with invalid emails before sending.
        """
        cid = campaign_id or self.cfg.instantly_campaign_id

        # Only include leads with valid emails
        valid_leads = [lead for lead in leads if is_valid_email(lead.get("email", ""))]
        skipped = len(leads) - len(valid_leads)
        if skipped:
            logger.warning("Skipped %d leads with invalid emails.", skipped)

        if not valid_leads:
            logger.warning("No valid leads to add to campaign %s.", cid)
            return {}

        formatted = [self._format_lead(lead) for lead in valid_leads]

        payload = {
            "api_key": self.cfg.instantly_key,
            "campaign_id": cid,
            "skip_if_in_workspace": True,
            "leads": formatted,
        }

        resp = requests.post(
            f"{self._base_url()}/lead/add",
            json=payload,
            timeout=self.cfg.api_timeout_long,
        )
        resp.raise_for_status()
        logger.info("Added %d leads to campaign %s.", len(formatted), cid)
        return resp.json()

    @retry_with_backoff(max_retries=2)
    def list_campaigns(self) -> list[dict]:
        """List all campaigns in the Instantly workspace."""
        resp = requests.get(
            f"{self._base_url()}/campaign/list",
            params={"api_key": self.cfg.instantly_key},
            timeout=self.cfg.api_timeout_short,
        )
        resp.raise_for_status()
        return resp.json()

    @retry_with_backoff(max_retries=2)
    def get_campaign_summary(self, campaign_id: str | None = None) -> dict:
        """Get summary statistics for a campaign."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        resp = requests.get(
            f"{self._base_url()}/analytics/campaign/summary",
            params={"api_key": self.cfg.instantly_key, "campaign_id": cid},
            timeout=self.cfg.api_timeout_short,
        )
        resp.raise_for_status()
        return resp.json()
