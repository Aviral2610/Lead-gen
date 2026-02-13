"""Website research agent — scrapes a prospect's website via Firecrawl,
then uses GPT-4o to extract personalization hooks (specific details,
pain points, technology stack)."""

import json

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff

logger = setup_logger(__name__)


class WebsiteResearcher:
    """Scrape and analyze prospect websites for personalization data."""

    def __init__(self, config=None):
        self.cfg = config or get_config()

    @rate_limit(min_interval=1.0)
    @retry_with_backoff(max_retries=2)
    def scrape_website(self, url: str) -> str:
        """Scrape website content via Firecrawl. Returns markdown text."""
        if not self.cfg.firecrawl_key:
            logger.warning("No Firecrawl key configured; skipping scrape.")
            return ""

        resp = requests.post(
            "https://api.firecrawl.dev/v0/scrape",
            headers={
                "Authorization": f"Bearer {self.cfg.firecrawl_key}",
                "Content-Type": "application/json",
            },
            json={"url": url, "pageOptions": {"onlyMainContent": True}},
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json().get("data", {}).get("markdown", "")
        logger.info("Scraped %d chars from %s", len(content), url)
        return content

    @rate_limit(min_interval=1.0)
    @retry_with_backoff(max_retries=2)
    def analyze_with_gpt(self, website_content: str) -> dict:
        """Send website content to GPT-4o for structured analysis.

        Returns a dict with keys:
          - main_service: str
          - specific_detail: str
          - pain_point: str
          - tech_stack: str
        """
        if not website_content.strip():
            return {
                "main_service": "",
                "specific_detail": "",
                "pain_point": "",
                "tech_stack": "",
            }

        system_prompt = (
            "Analyze this company website and extract:\n"
            "1. Main product/service offered\n"
            "2. One specific, non-obvious detail (recent blog post, team expansion, "
            "product launch, award, case study)\n"
            "3. Primary pain point the business likely faces\n"
            "4. Technology stack if visible\n"
            "Respond ONLY in JSON format with keys: "
            "main_service, specific_detail, pain_point, tech_stack"
        )

        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.cfg.openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": website_content[:4000]},
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from the response (handle markdown code blocks)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse GPT analysis JSON: %s", raw[:200])
            return {
                "main_service": "",
                "specific_detail": "",
                "pain_point": "",
                "tech_stack": "",
            }

    def research(self, website_url: str) -> dict:
        """Full pipeline: scrape website, analyze with GPT-4o."""
        content = self.scrape_website(website_url)
        return self.analyze_with_gpt(content)
