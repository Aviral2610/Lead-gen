"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch


class TestConfig:
    def test_optional_fields_default_to_empty_string(self):
        required_env = {
            "APIFY_API_TOKEN": "tok",
            "OPENAI_API_KEY": "okey",
            "ANTHROPIC_API_KEY": "akey",
            "PROSPEO_API_KEY": "pkey",
            "HUNTER_API_KEY": "hkey",
            "INSTANTLY_API_KEY": "ikey",
            "INSTANTLY_CAMPAIGN_ID": "cid",
        }
        with patch.dict(os.environ, required_env, clear=True):
            from src.utils.config import Config
            cfg = Config()
            assert cfg.apollo_key == ""
            assert cfg.firecrawl_key == ""
            assert cfg.slack_webhook_url == ""
            assert cfg.sheets_spreadsheet_id == ""

    def test_optional_apollo_key_loaded_from_env(self):
        required_env = {
            "APIFY_API_TOKEN": "tok",
            "OPENAI_API_KEY": "okey",
            "ANTHROPIC_API_KEY": "akey",
            "PROSPEO_API_KEY": "pkey",
            "HUNTER_API_KEY": "hkey",
            "INSTANTLY_API_KEY": "ikey",
            "INSTANTLY_CAMPAIGN_ID": "cid",
            "APOLLO_API_KEY": "my_apollo_key",
        }
        with patch.dict(os.environ, required_env, clear=True):
            from src.utils.config import Config
            cfg = Config()
            assert cfg.apollo_key == "my_apollo_key"

    def test_missing_required_env_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            from src.utils.config import Config
            with pytest.raises(EnvironmentError, match="APIFY_API_TOKEN"):
                Config()

    def test_tuning_defaults(self):
        required_env = {
            "APIFY_API_TOKEN": "tok",
            "OPENAI_API_KEY": "okey",
            "ANTHROPIC_API_KEY": "akey",
            "PROSPEO_API_KEY": "pkey",
            "HUNTER_API_KEY": "hkey",
            "INSTANTLY_API_KEY": "ikey",
            "INSTANTLY_CAMPAIGN_ID": "cid",
        }
        with patch.dict(os.environ, required_env, clear=True):
            from src.utils.config import Config
            cfg = Config()
            assert cfg.max_leads_per_search == 100
            assert cfg.api_rate_limit_delay == 1.0
            assert cfg.enrichment_batch_size == 20
            assert cfg.max_emails_per_inbox_per_day == 50
