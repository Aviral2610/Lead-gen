"""Tests for src/enrichment/waterfall.py"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config
from src.enrichment.waterfall import EmailEnricher


@pytest.fixture
def enricher():
    return EmailEnricher(config=make_config())


# ---------------------------------------------------------------------------
# enrich — waterfall layers
# ---------------------------------------------------------------------------

class TestEnrich:
    def test_returns_immediately_if_valid_email_present(self, enricher):
        lead = {"email": "owner@shop.com", "website": "https://shop.com"}
        result = enricher.enrich(lead)
        assert result["email"] == "owner@shop.com"
        assert result["enrichment_source"] == "scraped"

    def test_returns_none_source_if_no_website(self, enricher):
        lead = {"email": "", "website": ""}
        result = enricher.enrich(lead)
        assert result["enrichment_source"] == "none"

    def test_returns_none_source_if_invalid_domain(self, enricher):
        lead = {"email": "", "website": "notadomain"}
        result = enricher.enrich(lead)
        assert result["enrichment_source"] == "none"

    def test_uses_prospeo_when_no_email(self, enricher):
        lead = {"email": "", "website": "https://example.com"}
        with patch.object(enricher, "_prospeo_search", return_value="found@example.com"):
            result = enricher.enrich(lead)
        assert result["email"] == "found@example.com"
        assert result["enrichment_source"] == "prospeo"

    def test_falls_through_to_hunter_when_prospeo_returns_none(self, enricher):
        lead = {"email": "", "website": "https://example.com"}
        with patch.object(enricher, "_prospeo_search", return_value=None), \
             patch.object(enricher, "_hunter_search", return_value="found@example.com"):
            result = enricher.enrich(lead)
        assert result["email"] == "found@example.com"
        assert result["enrichment_source"] == "hunter"

    def test_prospeo_exception_falls_through_to_hunter(self, enricher):
        lead = {"email": "", "website": "https://example.com"}
        with patch.object(enricher, "_prospeo_search", side_effect=Exception("timeout")), \
             patch.object(enricher, "_hunter_search", return_value="found@example.com"):
            result = enricher.enrich(lead)
        assert result["email"] == "found@example.com"
        assert result["enrichment_source"] == "hunter"

    def test_both_fail_returns_empty_email(self, enricher):
        lead = {"email": "", "website": "https://example.com"}
        with patch.object(enricher, "_prospeo_search", return_value=None), \
             patch.object(enricher, "_hunter_search", return_value=None):
            result = enricher.enrich(lead)
        assert result["email"] == ""

    def test_hunter_not_called_when_prospeo_succeeds(self, enricher):
        lead = {"email": "", "website": "https://example.com"}
        hunter_mock = MagicMock(return_value="hunter@example.com")
        with patch.object(enricher, "_prospeo_search", return_value="prospeo@example.com"), \
             patch.object(enricher, "_hunter_search", hunter_mock):
            enricher.enrich(lead)
        hunter_mock.assert_not_called()

    def test_extracts_domain_correctly(self, enricher):
        lead = {"email": "", "website": "https://www.example.com/about?ref=123"}
        prospeo_mock = MagicMock(return_value="info@example.com")
        with patch.object(enricher, "_prospeo_search", prospeo_mock):
            enricher.enrich(lead)
        prospeo_mock.assert_called_once_with("www.example.com")

    def test_website_without_scheme(self, enricher):
        lead = {"email": "", "website": "example.com"}
        with patch.object(enricher, "_prospeo_search", return_value="a@example.com"):
            result = enricher.enrich(lead)
        assert result["email"] == "a@example.com"


# ---------------------------------------------------------------------------
# verify_email
# ---------------------------------------------------------------------------

class TestVerifyEmail:
    def test_valid_email_returns_true(self, enricher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": {"result": "valid"}}
        with patch("requests.get", return_value=mock_resp):
            assert enricher.verify_email("owner@shop.com") is True

    def test_invalid_email_result_returns_false(self, enricher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": {"result": "invalid"}}
        with patch("requests.get", return_value=mock_resp):
            assert enricher.verify_email("bad@shop.com") is False

    def test_empty_string_returns_false_without_api_call(self, enricher):
        with patch("requests.get") as mock_get:
            assert enricher.verify_email("") is False
        mock_get.assert_not_called()

    def test_no_at_sign_returns_false_without_api_call(self, enricher):
        with patch("requests.get") as mock_get:
            assert enricher.verify_email("notanemail") is False
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# process_batch
# ---------------------------------------------------------------------------

class TestProcessBatch:
    def test_returns_only_verified_leads(self, enricher):
        leads = [
            {"email": "a@a.com", "business_name": "A"},
            {"email": "b@b.com", "business_name": "B"},
        ]

        def mock_enrich(lead):
            return lead

        def mock_verify(email):
            return email == "a@a.com"

        with patch.object(enricher, "enrich", side_effect=mock_enrich), \
             patch.object(enricher, "verify_email", side_effect=mock_verify):
            result = enricher.process_batch(leads)

        assert len(result) == 1
        assert result[0]["email"] == "a@a.com"

    def test_empty_batch_returns_empty(self, enricher):
        assert enricher.process_batch([]) == []
