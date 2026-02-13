"""Apify Google Maps scraper — triggers the Compass Google Places actor
and retrieves cleaned lead data."""

import time

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import retry_with_backoff

logger = setup_logger(__name__)

ACTOR_ID = "compass~crawler-google-places"
APIFY_BASE = "https://api.apify.com/v2"


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

    def clean_lead(self, raw: dict) -> dict:
        """Normalize a raw Apify result into a clean lead dict."""
        email = raw.get("email") or ""
        if not email and isinstance(raw.get("contactInfo"), dict):
            email = raw["contactInfo"].get("email", "")

        return {
            "business_name": raw.get("title", ""),
            "email": email,
            "phone": raw.get("phone", ""),
            "website": raw.get("website", ""),
            "address": raw.get("address", ""),
            "rating": raw.get("totalScore"),
            "review_count": raw.get("reviewsCount"),
            "category": raw.get("categoryName", ""),
            "city": raw.get("city", ""),
        }

    def scrape(self, search_queries: list[str]) -> list[dict]:
        """Full pipeline: start run, wait, fetch, clean, deduplicate."""
        run_id = self.start_run(search_queries)
        if not self.wait_for_completion(run_id):
            return []

        raw_items = self.fetch_results(run_id)
        logger.info("Fetched %d raw items from Apify.", len(raw_items))

        # Clean
        leads = [self.clean_lead(item) for item in raw_items]

        # Filter: must have email
        leads = [l for l in leads if l["email"]]
        logger.info("%d leads have emails.", len(leads))

        # Deduplicate by email
        seen = set()
        unique = []
        for lead in leads:
            if lead["email"].lower() not in seen:
                seen.add(lead["email"].lower())
                unique.append(lead)

        logger.info("%d unique leads after dedup.", len(unique))
        return unique
