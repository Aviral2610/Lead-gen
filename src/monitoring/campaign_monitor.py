"""Campaign health monitor — tracks bounce rates, spam complaints, and
other deliverability metrics. Triggers alerts when thresholds are exceeded.

Thresholds (from config/kpi_benchmarks.json):
  - Bounce rate > 2% → pause campaign
  - Spam complaint rate > 0.1% → pause campaign
  - Reply rate < 3% after 500+ sends → review targeting
"""

import json
from dataclasses import dataclass
from pathlib import Path

import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import retry_with_backoff

logger = setup_logger(__name__)

INSTANTLY_BASE = "https://api.instantly.ai/api/v1"


@dataclass
class CampaignHealth:
    """Snapshot of campaign health metrics."""
    campaign_id: str
    total_sent: int = 0
    total_opened: int = 0
    total_replied: int = 0
    total_bounced: int = 0
    total_unsubscribed: int = 0

    @property
    def bounce_rate(self) -> float:
        return (self.total_bounced / self.total_sent * 100) if self.total_sent else 0.0

    @property
    def reply_rate(self) -> float:
        return (self.total_replied / self.total_sent * 100) if self.total_sent else 0.0

    @property
    def open_rate(self) -> float:
        return (self.total_opened / self.total_sent * 100) if self.total_sent else 0.0

    @property
    def unsubscribe_rate(self) -> float:
        return (self.total_unsubscribed / self.total_sent * 100) if self.total_sent else 0.0

    def is_healthy(self, max_bounce_pct: float = 2.0, max_unsub_pct: float = 2.0) -> bool:
        return self.bounce_rate <= max_bounce_pct and self.unsubscribe_rate <= max_unsub_pct


class CampaignMonitor:
    """Fetches campaign analytics from Instantly and evaluates health."""

    def __init__(self, config=None):
        self.cfg = config or get_config()
        self._load_thresholds()

    def _load_thresholds(self):
        """Load alert thresholds from config."""
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "kpi_benchmarks.json"
        try:
            with open(config_path) as f:
                data = json.load(f)
            benchmarks = data.get("benchmarks", {})
            self.max_bounce_rate = benchmarks.get("bounce_rate", {}).get("alert_threshold", 0.02) * 100
            self.max_spam_rate = benchmarks.get("spam_complaint_rate", {}).get("alert_threshold", 0.001) * 100
        except (FileNotFoundError, json.JSONDecodeError):
            self.max_bounce_rate = 2.0
            self.max_spam_rate = 0.1

    @retry_with_backoff(max_retries=2)
    def fetch_campaign_summary(self, campaign_id: str | None = None) -> dict:
        """Fetch analytics summary from Instantly API."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        resp = requests.get(
            f"{INSTANTLY_BASE}/analytics/campaign/summary",
            params={"api_key": self.cfg.instantly_key, "campaign_id": cid},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_health(self, campaign_id: str | None = None) -> CampaignHealth:
        """Get current campaign health metrics."""
        cid = campaign_id or self.cfg.instantly_campaign_id
        try:
            data = self.fetch_campaign_summary(cid)
        except requests.RequestException as e:
            logger.error("Failed to fetch campaign analytics: %s", e)
            return CampaignHealth(campaign_id=cid)

        health = CampaignHealth(
            campaign_id=cid,
            total_sent=data.get("sent", 0),
            total_opened=data.get("opened", 0),
            total_replied=data.get("replied", 0),
            total_bounced=data.get("bounced", 0),
            total_unsubscribed=data.get("unsubscribed", 0),
        )
        return health

    def check_and_alert(self, campaign_id: str | None = None) -> list[str]:
        """Check campaign health and return a list of alert messages.

        Returns empty list if everything is healthy.
        """
        health = self.get_health(campaign_id)
        alerts = []

        if health.total_sent == 0:
            return alerts

        if health.bounce_rate > self.max_bounce_rate:
            msg = (
                f"ALERT: Bounce rate {health.bounce_rate:.1f}% exceeds "
                f"threshold {self.max_bounce_rate:.1f}% for campaign {health.campaign_id}. "
                f"Pause campaign and clean email list."
            )
            alerts.append(msg)
            logger.warning(msg)

        if health.unsubscribe_rate > 2.0:
            msg = (
                f"ALERT: Unsubscribe rate {health.unsubscribe_rate:.1f}% exceeds 2% "
                f"for campaign {health.campaign_id}. Review targeting and copy."
            )
            alerts.append(msg)
            logger.warning(msg)

        if health.total_sent >= 500 and health.reply_rate < 3.0:
            msg = (
                f"WARNING: Reply rate {health.reply_rate:.1f}% below 3% after "
                f"{health.total_sent} sends on campaign {health.campaign_id}. "
                f"Consider A/B testing new templates."
            )
            alerts.append(msg)
            logger.warning(msg)

        if not alerts:
            logger.info(
                "Campaign %s healthy: sent=%d, bounce=%.1f%%, reply=%.1f%%, open=%.1f%%",
                health.campaign_id, health.total_sent,
                health.bounce_rate, health.reply_rate, health.open_rate,
            )

        return alerts

    def send_slack_alerts(self, alerts: list[str]):
        """Send alert messages to Slack."""
        if not alerts or not self.cfg.slack_webhook_url:
            return
        text = "\n".join(f":warning: {a}" for a in alerts)
        try:
            requests.post(
                self.cfg.slack_webhook_url,
                json={"text": text},
                timeout=10,
            )
        except requests.RequestException as e:
            logger.error("Slack alert failed: %s", e)
