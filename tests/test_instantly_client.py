"""Tests for src/outreach/instantly_client.py"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config
from src.outreach.instantly_client import InstantlyClient


@pytest.fixture
def client():
    return InstantlyClient(config=make_config())


def _make_leads(n: int, prefix: str = "lead") -> list[dict]:
    return [{"email": f"{prefix}{i}@example.com"} for i in range(n)]


# ---------------------------------------------------------------------------
# _format_lead
# ---------------------------------------------------------------------------

class TestFormatLead:
    def test_valid_lead_mapped_correctly(self, client):
        lead = {
            "email": "owner@shop.com",
            "first_name": "Joe",
            "last_name": "Smith",
            "business_name": "Joe's Shop",
            "ai_first_line": "Loved your site.",
            "website": "https://joesshop.com",
            "pain_point": "growth",
            "category": "Retail",
            "specific_detail": "new location",
        }
        result = client._format_lead(lead)
        assert result is not None
        assert result["email"] == "owner@shop.com"
        assert result["company_name"] == "Joe's Shop"
        assert result["personalization"] == "Loved your site."
        assert result["custom_variables"]["pain_point"] == "growth"
        assert result["custom_variables"]["industry"] == "Retail"

    def test_missing_email_returns_none(self, client):
        assert client._format_lead({"business_name": "Ghost", "email": ""}) is None

    def test_invalid_email_no_at_returns_none(self, client):
        assert client._format_lead({"email": "notanemail"}) is None

    def test_strips_email_whitespace(self, client):
        result = client._format_lead({"email": "  owner@shop.com  "})
        assert result is not None
        assert result["email"] == "owner@shop.com"

    def test_missing_email_key_returns_none(self, client):
        assert client._format_lead({}) is None


# ---------------------------------------------------------------------------
# add_leads_batch — chunking
# ---------------------------------------------------------------------------

class TestAddLeadsBatch:
    def test_empty_list_returns_empty_dict(self, client):
        assert client.add_leads_batch([]) == {}

    def test_all_invalid_returns_empty_dict(self, client):
        leads = [{"email": ""}, {"email": "badformat"}]
        assert client.add_leads_batch(leads) == {}

    def test_250_leads_split_into_100_100_50(self, client):
        leads = _make_leads(250)
        chunk_sizes = []

        def capture(chunk, cid):
            chunk_sizes.append(len(chunk))
            return {"status": "ok"}

        with patch.object(client, "_push_chunk", side_effect=capture):
            client.add_leads_batch(leads, chunk_size=100)

        assert chunk_sizes == [100, 100, 50]

    def test_exact_chunk_boundary(self, client):
        leads = _make_leads(200)
        chunk_sizes = []

        def capture(chunk, cid):
            chunk_sizes.append(len(chunk))
            return {}

        with patch.object(client, "_push_chunk", side_effect=capture):
            client.add_leads_batch(leads, chunk_size=100)

        assert chunk_sizes == [100, 100]

    def test_single_chunk_when_leads_less_than_chunk_size(self, client):
        leads = _make_leads(10)
        chunk_sizes = []

        def capture(chunk, cid):
            chunk_sizes.append(len(chunk))
            return {}

        with patch.object(client, "_push_chunk", side_effect=capture):
            client.add_leads_batch(leads, chunk_size=100)

        assert chunk_sizes == [10]

    def test_returns_response_from_last_chunk(self, client):
        leads = _make_leads(5)
        responses = [{"chunk": 1}, {"chunk": 2}]
        call_idx = [0]

        def mock_push(chunk, cid):
            resp = responses[min(call_idx[0], len(responses) - 1)]
            call_idx[0] += 1
            return resp

        with patch.object(client, "_push_chunk", side_effect=mock_push):
            result = client.add_leads_batch(leads, chunk_size=3)

        assert result == {"chunk": 2}

    def test_default_chunk_size_is_100(self, client):
        leads = _make_leads(101)
        chunk_sizes = []

        with patch.object(client, "_push_chunk", side_effect=lambda c, _: chunk_sizes.append(len(c)) or {}):
            client.add_leads_batch(leads)

        assert chunk_sizes == [100, 1]

    def test_uses_campaign_id_from_config_when_not_specified(self, client):
        leads = _make_leads(1)
        captured_cid = []

        def capture(chunk, cid):
            captured_cid.append(cid)
            return {}

        with patch.object(client, "_push_chunk", side_effect=capture):
            client.add_leads_batch(leads)

        assert captured_cid[0] == "campaign-123"

    def test_overrides_campaign_id_when_specified(self, client):
        leads = _make_leads(1)
        captured_cid = []

        def capture(chunk, cid):
            captured_cid.append(cid)
            return {}

        with patch.object(client, "_push_chunk", side_effect=capture):
            client.add_leads_batch(leads, campaign_id="custom-campaign")

        assert captured_cid[0] == "custom-campaign"
