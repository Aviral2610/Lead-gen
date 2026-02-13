"""Cost tracker — estimates and logs API spend per service."""

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# Approximate cost per API call (USD) — update as pricing changes
DEFAULT_COSTS = {
    "apify_gmaps": 0.0041,         # ~$0.41 per 100 leads
    "prospeo_search": 0.01,         # ~$0.01 per lookup
    "prospeo_verify": 0.005,        # ~$0.005 per verification
    "hunter_search": 0.015,         # ~$0.015 per lookup
    "firecrawl_scrape": 0.01,       # ~$0.01 per page
    "openai_gpt4o": 0.005,          # ~$0.005 per call (short prompts)
    "claude_sonnet": 0.003,         # ~$0.003 per first-line generation
    "claude_classify": 0.001,       # ~$0.001 per classification
    "instantly_add": 0.0,           # included in subscription
}

COST_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "cost_log.json"


class CostTracker:
    """Track API call counts and estimated costs per service."""

    def __init__(self, cost_overrides: dict[str, float] | None = None):
        self.costs = {**DEFAULT_COSTS, **(cost_overrides or {})}
        self._calls: dict[str, int] = defaultdict(int)
        self._spend: dict[str, float] = defaultdict(float)
        self._session_start = time.time()

    def log_call(self, service: str, count: int = 1):
        """Record an API call to a service."""
        self._calls[service] += count
        unit_cost = self.costs.get(service, 0.0)
        self._spend[service] += unit_cost * count

    @property
    def total_spend(self) -> float:
        return sum(self._spend.values())

    @property
    def total_calls(self) -> int:
        return sum(self._calls.values())

    def summary(self) -> dict:
        """Return a summary of costs and call counts."""
        return {
            "session_duration_s": round(time.time() - self._session_start, 1),
            "total_api_calls": self.total_calls,
            "estimated_total_cost_usd": round(self.total_spend, 4),
            "by_service": {
                svc: {
                    "calls": self._calls[svc],
                    "estimated_cost_usd": round(self._spend[svc], 4),
                }
                for svc in sorted(self._calls.keys())
            },
        }

    def log_summary(self):
        """Log the cost summary."""
        s = self.summary()
        logger.info(
            "Cost summary: %d calls, $%.4f estimated total.",
            s["total_api_calls"], s["estimated_total_cost_usd"],
        )
        for svc, data in s["by_service"].items():
            logger.info("  %s: %d calls, $%.4f", svc, data["calls"], data["estimated_cost_usd"])

    def save(self):
        """Append session costs to persistent log."""
        COST_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **self.summary(),
        }

        # Append to log file
        existing = []
        if COST_LOG_FILE.exists():
            try:
                with open(COST_LOG_FILE) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []

        existing.append(entry)

        with open(COST_LOG_FILE, "w") as f:
            json.dump(existing, f, indent=2, default=str)
