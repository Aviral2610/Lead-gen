"""Tests for the Instantly.ai outreach client."""

import pytest
from unittest.mock import MagicMock, patch

from src.outreach.instantly_client import InstantlyClient


def _mock_config():
    cfg = MagicMock()
    cfg.instantly_key = "test_key"
    cfg.instantly_campaign_id = "camp_123"
    return cfg


class TestInstantlyClient:
    def setup_method(self):
        self.client = InstantlyClient(config=_mock_config())

    def _make_lead(self, email="test@example.com", **kwargs):
        return {
            "email": email,
            "first_name": "Jane",
            "last_name": "Doe",
            "business_name": "Acme Corp",
            "ai_first_line": "Love what you're doing with remote onboarding.",
            "website": "https://acme.com",
            "pain_point": "high churn",
            "category": "SaaS",
            "specific_detail": "launched enterprise tier",
            **kwargs,
        }

    @patch("src.outreach.instantly_client.requests.post")
    def test_add_lead_uses_configured_campaign(self, mock_post):
        mock_post.return_value.json.return_value = {"status": "success"}
        mock_post.return_value.raise_for_status = MagicMock()

        self.client.add_lead(self._make_lead())

        payload = mock_post.call_args.kwargs["json"]
        assert payload["campaign_id"] == "camp_123"
        assert payload["api_key"] == "test_key"

    @patch("src.outreach.instantly_client.requests.post")
    def test_add_lead_overrides_campaign_id(self, mock_post):
        mock_post.return_value.json.return_value = {}
        mock_post.return_value.raise_for_status = MagicMock()

        self.client.add_lead(self._make_lead(), campaign_id="other_camp")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["campaign_id"] == "other_camp"

    @patch("src.outreach.instantly_client.requests.post")
    def test_add_lead_maps_fields_correctly(self, mock_post):
        mock_post.return_value.json.return_value = {}
        mock_post.return_value.raise_for_status = MagicMock()

        lead = self._make_lead()
        self.client.add_lead(lead)

        payload = mock_post.call_args.kwargs["json"]
        sent_lead = payload["leads"][0]
        assert sent_lead["email"] == "test@example.com"
        assert sent_lead["first_name"] == "Jane"
        assert sent_lead["company_name"] == "Acme Corp"
        assert sent_lead["personalization"] == "Love what you're doing with remote onboarding."
        assert sent_lead["custom_variables"]["pain_point"] == "high churn"
        assert sent_lead["custom_variables"]["industry"] == "SaaS"
        assert sent_lead["custom_variables"]["specific_detail"] == "launched enterprise tier"

    @patch("src.outreach.instantly_client.requests.post")
    def test_add_leads_batch_sends_all(self, mock_post):
        mock_post.return_value.json.return_value = {}
        mock_post.return_value.raise_for_status = MagicMock()

        leads = [self._make_lead(email=f"lead{i}@co.com") for i in range(5)]
        self.client.add_leads_batch(leads)

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["leads"]) == 5

    @patch("src.outreach.instantly_client.requests.post")
    def test_add_leads_batch_skips_workspace_duplicates(self, mock_post):
        mock_post.return_value.json.return_value = {}
        mock_post.return_value.raise_for_status = MagicMock()

        self.client.add_leads_batch([self._make_lead()])

        payload = mock_post.call_args.kwargs["json"]
        assert payload["skip_if_in_workspace"] is True

    @patch("src.outreach.instantly_client.requests.get")
    def test_list_campaigns(self, mock_get):
        mock_get.return_value.json.return_value = [{"id": "c1", "name": "Test"}]
        mock_get.return_value.raise_for_status = MagicMock()

        result = self.client.list_campaigns()
        assert isinstance(result, list)
        assert result[0]["name"] == "Test"

    @patch("src.outreach.instantly_client.requests.get")
    def test_get_campaign_summary(self, mock_get):
        mock_get.return_value.json.return_value = {
            "open_rate": 0.45, "reply_rate": 0.12
        }
        mock_get.return_value.raise_for_status = MagicMock()

        result = self.client.get_campaign_summary()
        assert result["open_rate"] == 0.45

    @patch("src.outreach.instantly_client.requests.get")
    def test_get_campaign_summary_uses_override_id(self, mock_get):
        mock_get.return_value.json.return_value = {}
        mock_get.return_value.raise_for_status = MagicMock()

        self.client.get_campaign_summary(campaign_id="other_id")

        params = mock_get.call_args.kwargs["params"]
        assert params["campaign_id"] == "other_id"
