"""Apify Google Maps scraper — triggers the Compass Google Places actor
and retrieves cleaned lead data."""

import time
from urllib.parse import urlparse

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import retry_with_backoff

logger = setup_logger(__name__)

ACTOR_ID = "compass~crawler-google-places"
APIFY_BASE = "https://api.apify.com/v2"


def _normalize_website(url: str) -> str:
    """Normalize a website URL to HTTPS with no www. prefix or trailing path.

    Examples:
        http://www.example.com/about  →  https://example.com
        https://www.shop.co.uk/      →  https://shop.co.uk
        example.com                  →  https://example.com
    """
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return f"https://{host}" if host else ""


class GoogleMapsScraper:
    """Triggers Apify's Google Places actor and fetches results."""

    def __init__(self, config=None):
        self.cfg = config or get_config()
        self.headers = {"Authorization": f"Bearer {self.cfg.apify_token}"}

    def start_run(self, search_queries: list[str]) -> str:
        """Start an Apify actor run and return the run ID."""
        url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs"
        payload = {
            "searchStringsArray": search_queries,
            "maxCrawledPlacesPerSearch": self.cfg.max_leads_per_search,
            "language": "en",
            "includeWebResults": False,
            "scrapeContacts": True,
            "scrapeReviews": False,
        }
        resp = requests.post(url, json=payload, headers=self.headers, timeout=30)
        resp.raise_for_status()
        run_id = resp.json()["data"]["id"]
        logger.info("Apify run started: %s", run_id)
        return run_id

    def wait_for_completion(self, run_id: str, poll_interval: int = 30,
                            max_wait: int = 600) -> bool:
        """Poll until the Apify run finishes. Returns True if succeeded."""
        url = f"{APIFY_BASE}/actor-runs/{run_id}"
        elapsed = 0
        while elapsed < max_wait:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.raise_for_status()
            status = resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                logger.info("Apify run %s completed successfully.", run_id)
                return True
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                logger.error("Apify run %s ended with status: %s", run_id, status)
                return False
            time.sleep(poll_interval)
            elapsed += poll_interval
        logger.error("Apify run %s timed out after %ds.", run_id, max_wait)
        return False

    @retry_with_backoff(max_retries=3)
    def fetch_results(self, run_id: str | None = None) -> list[dict]:
        """Fetch dataset items from the last (or specified) run."""
        if run_id:
            url = f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items"
        else:
            url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs/last/dataset/items"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _clean_lead(self, raw: dict) -> dict:
        """Normalize a raw Apify result into a clean lead dict."""
        email = raw.get("email") or ""
        if not email and isinstance(raw.get("contactInfo"), dict):
            email = raw["contactInfo"].get("email", "")

        return {
            "business_name": raw.get("title", ""),
            "email": email,
            "phone": raw.get("phone", ""),
            "website": _normalize_website(raw.get("website", "")),
            "address": raw.get("address", ""),
            "rating": raw.get("totalScore") or 0.0,
            "review_count": raw.get("reviewsCount") or 0,
            "category": raw.get("categoryName", ""),
            "city": raw.get("city", ""),
        }

    # Keep old name as an alias for backwards compatibility with any external callers
    clean_lead = _clean_lead

    def _deduplicate(self, leads: list[dict]) -> list[dict]:
        """Remove leads with duplicate emails (case-insensitive).

        Leads with an empty email are kept as-is (not de-duplicated against
        each other) since the email enrichment step may recover their address.
        """
        seen: set[str] = set()
        unique: list[dict] = []
        for lead in leads:
            email = lead.get("email", "").lower()
            if not email:
                unique.append(lead)
                continue
            if email not in seen:
                seen.add(email)
                unique.append(lead)
        return unique

    def scrape(self, search_queries: list[str]) -> list[dict]:
        """Full pipeline: start run, wait, fetch, clean, deduplicate."""
        run_id = self.start_run(search_queries)
        if not self.wait_for_completion(run_id):
            return []

        raw_items = self.fetch_results(run_id)
        logger.info("Fetched %d raw items from Apify.", len(raw_items))

        leads = [self._clean_lead(item) for item in raw_items]

        # Filter: must have email
        leads = [l for l in leads if l["email"]]
        logger.info("%d leads have emails.", len(leads))

        leads = self._deduplicate(leads)
        logger.info("%d unique leads after dedup.", len(leads))
        return leads
