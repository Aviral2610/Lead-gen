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

    def scrape(
        self,
        titles: list[str],
        locations: list[str] | None = None,
        employee_ranges: list[str] | None = None,
        industry_ids: list[str] | None = None,
        max_pages: int = 5,
        per_page: int = 25,
    ) -> list[dict]:
        """Paginate through Apollo results, clean, filter, and deduplicate.

        Fetches up to max_pages pages and stops early if a page returns
        fewer results than per_page (i.e. the last page).
        Returns only leads that have a valid email address.
        """
        all_leads: list[dict] = []

        for page in range(1, max_pages + 1):
            page_leads = self.search_people(
                titles=titles,
                locations=locations,
                employee_ranges=employee_ranges,
                industry_ids=industry_ids,
                page=page,
                per_page=per_page,
            )
            all_leads.extend(page_leads)

            # Stop early if this was the last page
            if len(page_leads) < per_page:
                logger.info("Reached last Apollo page at page %d.", page)
                break

        logger.info("Fetched %d total Apollo leads across pages.", len(all_leads))

        # Filter: must have a valid email
        with_email = [l for l in all_leads if l.get("email") and "@" in l["email"]]
        logger.info("%d leads have emails.", len(with_email))

        # Deduplicate by email (case-insensitive)
        seen: set[str] = set()
        unique: list[dict] = []
        for lead in with_email:
            key = lead["email"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(lead)

        logger.info("%d unique leads after dedup.", len(unique))
        return unique
