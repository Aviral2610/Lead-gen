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
    # --- API Keys ---
    apify_token: str = field(default_factory=lambda: _require("APIFY_API_TOKEN"))
    openai_key: str = field(default_factory=lambda: _require("OPENAI_API_KEY"))
    anthropic_key: str = field(default_factory=lambda: _require("ANTHROPIC_API_KEY"))
    prospeo_key: str = field(default_factory=lambda: _require("PROSPEO_API_KEY"))
    hunter_key: str = field(default_factory=lambda: _require("HUNTER_API_KEY"))
    instantly_key: str = field(default_factory=lambda: _require("INSTANTLY_API_KEY"))
    instantly_campaign_id: str = field(
        default_factory=lambda: _require("INSTANTLY_CAMPAIGN_ID")
    )
    sheets_spreadsheet_id: str = field(
        default_factory=lambda: _optional("GOOGLE_SHEETS_SPREADSHEET_ID")
    )
    firecrawl_key: str = field(
        default_factory=lambda: _optional("FIRECRAWL_API_KEY")
    )
    slack_webhook_url: str = field(
        default_factory=lambda: _optional("SLACK_WEBHOOK_URL")
    )

    # --- AI Model Configuration (centralized, no more hardcoded model names) ---
    claude_model: str = field(
        default_factory=lambda: _optional("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    )
    openai_model: str = field(
        default_factory=lambda: _optional("OPENAI_MODEL", "gpt-4o")
    )

    # --- API Base URLs (overridable for testing/migration) ---
    apify_base_url: str = field(
        default_factory=lambda: _optional("APIFY_BASE_URL", "https://api.apify.com/v2")
    )
    apify_actor_id: str = field(
        default_factory=lambda: _optional("APIFY_ACTOR_ID", "compass~crawler-google-places")
    )
    instantly_base_url: str = field(
        default_factory=lambda: _optional("INSTANTLY_BASE_URL", "https://api.instantly.ai/api/v1")
    )

    # --- Timeouts (seconds) ---
    api_timeout_short: int = field(
        default_factory=lambda: int(_optional("API_TIMEOUT_SHORT", "15"))
    )
    api_timeout_long: int = field(
        default_factory=lambda: int(_optional("API_TIMEOUT_LONG", "60"))
    )

    # --- Pipeline Tuning ---
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
    async_concurrency: int = field(
        default_factory=lambda: int(_optional("ASYNC_CONCURRENCY", "10"))
    )

    # --- Suppression ---
    suppression_file: str = field(
        default_factory=lambda: _optional("SUPPRESSION_FILE", "")
    )


# Singleton to avoid re-reading env on every call
_config_instance: Config | None = None


def get_config() -> Config:
    """Create and return a validated Config instance (cached)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def reset_config():
    """Reset cached config (for testing)."""
    global _config_instance
    _config_instance = None
