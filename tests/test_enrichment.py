"""Tests for the waterfall email enrichment module."""

import pytest
from unittest.mock import MagicMock, patch

from src.enrichment.waterfall import EmailEnricher


def _mock_config():
    cfg = MagicMock()
    cfg.prospeo_key = "test_prospeo"
    cfg.hunter_key = "test_hunter"
    return cfg


class TestEmailEnricher:
    def setup_method(self):
        self.enricher = EmailEnricher(config=_mock_config())

    def test_enrich_keeps_existing_valid_email(self):
        lead = {"email": "existing@example.com", "website": "https://example.com"}
        result = self.enricher.enrich(lead)
        assert result["email"] == "existing@example.com"
        assert result["enrichment_source"] == "scraped"

    def test_enrich_returns_none_source_when_no_website(self):
        lead = {"email": "", "website": ""}
        result = self.enricher.enrich(lead)
        assert result["enrichment_source"] == "none"

    @patch.object(EmailEnricher, "_prospeo_search", return_value="found@example.com")
    def test_enrich_uses_prospeo_when_no_email(self, mock_prospeo):
        lead = {"email": "", "website": "https://example.com"}
        result = self.enricher.enrich(lead)
        assert result["email"] == "found@example.com"
        assert result["enrichment_source"] == "prospeo"

    @patch.object(EmailEnricher, "_prospeo_search", return_value=None)
    @patch.object(EmailEnricher, "_hunter_search", return_value="hunter@example.com")
    def test_enrich_falls_back_to_hunter(self, mock_hunter, mock_prospeo):
        lead = {"email": "", "website": "https://example.com"}
        result = self.enricher.enrich(lead)
        assert result["email"] == "hunter@example.com"
        assert result["enrichment_source"] == "hunter"

    @patch.object(EmailEnricher, "_prospeo_search", side_effect=Exception("network error"))
    @patch.object(EmailEnricher, "_hunter_search", return_value="hunter@example.com")
    def test_enrich_skips_to_hunter_on_prospeo_failure(self, mock_hunter, mock_prospeo):
        lead = {"email": "", "website": "https://example.com"}
        result = self.enricher.enrich(lead)
        assert result["email"] == "hunter@example.com"
        assert result["enrichment_source"] == "hunter"

    @patch.object(EmailEnricher, "verify_email", return_value=True)
    @patch.object(EmailEnricher, "enrich", side_effect=lambda l: {**l, "email": "a@b.com", "enrichment_source": "prospeo"})
    def test_enrich_and_verify_sets_email_verified(self, mock_enrich, mock_verify):
        lead = {"email": "", "website": "https://example.com"}
        result = self.enricher.enrich_and_verify(lead)
        assert result["email_verified"] is True

    @patch.object(EmailEnricher, "verify_email", return_value=False)
    @patch.object(EmailEnricher, "enrich", side_effect=lambda l: {**l, "email": "bad@b.com", "enrichment_source": "hunter"})
    def test_process_batch_drops_unverified(self, mock_enrich, mock_verify):
        leads = [{"email": "", "website": "https://example.com"}]
        result = self.enricher.process_batch(leads)
        assert result == []

    @patch.object(EmailEnricher, "verify_email", return_value=True)
    @patch.object(EmailEnricher, "enrich", side_effect=lambda l: {**l, "email": "good@b.com", "enrichment_source": "prospeo"})
    def test_process_batch_keeps_verified(self, mock_enrich, mock_verify):
        leads = [{"email": "", "website": "https://example.com"}]
        result = self.enricher.process_batch(leads)
        assert len(result) == 1
        assert result[0]["email_verified"] is True
