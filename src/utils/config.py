"""Configuration management - loads environment variables with validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _load_env():
    """Load .env file from project root."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)


_load_env()


def _require(key: str) -> str:
    """Return env var or raise with a helpful message."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and fill in your keys."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass(frozen=True)
class Config:
    # Apify
    apify_token: str = field(default_factory=lambda: _require("APIFY_API_TOKEN"))

    # AI APIs
    openai_key: str = field(default_factory=lambda: _require("OPENAI_API_KEY"))
    anthropic_key: str = field(default_factory=lambda: _require("ANTHROPIC_API_KEY"))

    # Email Enrichment
    prospeo_key: str = field(default_factory=lambda: _require("PROSPEO_API_KEY"))
    hunter_key: str = field(default_factory=lambda: _require("HUNTER_API_KEY"))

    # Outreach
    instantly_key: str = field(default_factory=lambda: _require("INSTANTLY_API_KEY"))
    instantly_campaign_id: str = field(
        default_factory=lambda: _require("INSTANTLY_CAMPAIGN_ID")
    )

    # Google Sheets
    sheets_spreadsheet_id: str = field(
        default_factory=lambda: _optional("GOOGLE_SHEETS_SPREADSHEET_ID")
    )

    # Firecrawl
    firecrawl_key: str = field(
        default_factory=lambda: _optional("FIRECRAWL_API_KEY")
    )

    # Slack
    slack_webhook_url: str = field(
        default_factory=lambda: _optional("SLACK_WEBHOOK_URL")
    )

    # Tuning
    max_leads_per_search: int = field(
        default_factory=lambda: int(_optional("MAX_LEADS_PER_SEARCH", "100"))
    )
    api_rate_limit_delay: float = field(
        default_factory=lambda: float(_optional("API_RATE_LIMIT_DELAY", "1"))
    )
    enrichment_batch_size: int = field(
        default_factory=lambda: int(_optional("ENRICHMENT_BATCH_SIZE", "20"))
    )
    max_emails_per_inbox_per_day: int = field(
        default_factory=lambda: int(_optional("MAX_EMAILS_PER_INBOX_PER_DAY", "50"))
    )


def get_config() -> Config:
    """Create and return a validated Config instance."""
    return Config()
