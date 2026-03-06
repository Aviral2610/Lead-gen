"""Shared test configuration and helpers.

All sys.modules mocks are installed here BEFORE any source module is
imported, so external packages (google, anthropic, dotenv) are never
actually required to run the test suite.
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out packages that aren't installed / must be isolated
# ---------------------------------------------------------------------------
for _mod in [
    "dotenv",
    "google",
    "google.oauth2",
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
    "anthropic",
]:
    sys.modules.setdefault(_mod, MagicMock())

# dotenv.load_dotenv must be a no-op
sys.modules["dotenv"].load_dotenv = MagicMock()


# ---------------------------------------------------------------------------
# Fake config factory – use instead of get_config() in every test
# ---------------------------------------------------------------------------
def make_config(**overrides):
    """Return a SimpleNamespace that looks like a Config for tests."""
    defaults = {
        "apify_token": "test-apify-token",
        "openai_key": "test-openai-key",
        "anthropic_key": "test-anthropic-key",
        "prospeo_key": "test-prospeo-key",
        "hunter_key": "test-hunter-key",
        "instantly_key": "test-instantly-key",
        "instantly_campaign_id": "campaign-123",
        "sheets_spreadsheet_id": "spreadsheet-123",
        "firecrawl_key": "test-firecrawl-key",
        "slack_webhook_url": "https://hooks.slack.com/test",
        "max_leads_per_search": 100,
        "max_emails_per_inbox_per_day": 50,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)
