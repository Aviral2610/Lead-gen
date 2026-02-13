"""Apollo.io B2B lead scraper — searches for decision-maker contacts."""

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff

logger = setup_logger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"


class ApolloScraper:
    """Search Apollo.io for B2B leads matching an ICP."""

    def __init__(self, api_key: str, config=None):
        self.api_key = api_key
        self.cfg = config or get_config()

    @rate_limit(min_interval=1.0)
    @retry_with_backoff(max_retries=3)
    def search_people(
        self,
        titles: list[str],
        locations: list[str] | None = None,
        employee_ranges: list[str] | None = None,
        industry_ids: list[str] | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> list[dict]:
        """Search Apollo for people matching the given criteria."""
        payload: dict = {
            "api_key": self.api_key,
            "person_titles": titles,
            "page": page,
            "per_page": per_page,
        }
        if locations:
            payload["person_locations"] = locations
        if employee_ranges:
            payload["organization_num_employees_ranges"] = employee_ranges
        if industry_ids:
            payload["organization_industry_tag_ids"] = industry_ids

        resp = requests.post(
            f"{APOLLO_BASE}/mixed_people/search",
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        people = data.get("people", [])
        logger.info(
            "Apollo search returned %d results (page %d).", len(people), page
        )
        return [self._clean(p) for p in people]

    def _clean(self, person: dict) -> dict:
        org = person.get("organization", {}) or {}
        return {
            "first_name": person.get("first_name", ""),
            "last_name": person.get("last_name", ""),
            "email": person.get("email", ""),
            "title": person.get("title", ""),
            "business_name": org.get("name", ""),
            "website": org.get("website_url", ""),
            "phone": person.get("phone_number", ""),
            "city": person.get("city", ""),
            "category": org.get("industry", ""),
            "employee_count": org.get("estimated_num_employees"),
        }
