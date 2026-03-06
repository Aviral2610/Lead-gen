"""Integration-level tests for scripts/run_pipeline.py

All external classes and get_config are mocked, so no real API calls are made.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from tests.conftest import make_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_lead(email: str = "a@acme.com", name: str = "Acme"):
    return {"email": email, "business_name": name, "website": "https://acme.com"}


def _run_with_mocks(
    scraper_leads,
    enricher_leads,
    *,
    dry_run=False,
    skip_outreach=False,
    output_file="/tmp/test_pipeline.json",
    fail_outreach=False,
):
    """Run run_pipeline() with all external dependencies mocked."""
    with patch("scripts.run_pipeline.get_config", return_value=make_config()), \
         patch("scripts.run_pipeline.GoogleMapsScraper") as MockScraper, \
         patch("scripts.run_pipeline.EmailEnricher") as MockEnricher, \
         patch("scripts.run_pipeline.WebsiteResearcher") as MockResearcher, \
         patch("scripts.run_pipeline.EmailWriter") as MockWriter, \
         patch("scripts.run_pipeline.InstantlyClient") as MockInstantly:

        MockScraper.return_value.scrape.return_value = scraper_leads
        MockEnricher.return_value.process_batch.return_value = enricher_leads
        MockResearcher.return_value.research.return_value = {
            "main_service": "SaaS", "specific_detail": "award",
            "pain_point": "churn", "tech_stack": "React",
        }
        MockWriter.return_value.personalize_lead.side_effect = lambda l: {**l, "ai_first_line": "Hi."}

        if fail_outreach:
            MockInstantly.return_value.add_leads_batch.side_effect = Exception("API down")

        from scripts.run_pipeline import run_pipeline
        result = run_pipeline(
            search_queries=["barbers in Toronto"],
            dry_run=dry_run,
            skip_outreach=skip_outreach,
            output_file=output_file,
        )
        return result, MockInstantly


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_dry_run_skips_outreach(self, tmp_path):
        out = str(tmp_path / "out.json")
        leads = [_mock_lead()]
        _, MockInstantly = _run_with_mocks(leads, leads, dry_run=True, output_file=out)
        MockInstantly.return_value.add_leads_batch.assert_not_called()

    def test_skip_outreach_flag_skips_outreach(self, tmp_path):
        out = str(tmp_path / "out.json")
        leads = [_mock_lead()]
        _, MockInstantly = _run_with_mocks(leads, leads, skip_outreach=True, output_file=out)
        MockInstantly.return_value.add_leads_batch.assert_not_called()

    def test_normal_run_calls_outreach(self, tmp_path):
        out = str(tmp_path / "out.json")
        leads = [_mock_lead()]
        _, MockInstantly = _run_with_mocks(leads, leads, output_file=out)
        MockInstantly.return_value.add_leads_batch.assert_called_once()

    def test_no_scraped_leads_returns_empty(self, tmp_path):
        out = str(tmp_path / "out.json")
        result, MockInstantly = _run_with_mocks([], [], dry_run=True, output_file=out)
        assert result == []
        MockInstantly.return_value.add_leads_batch.assert_not_called()

    def test_no_verified_leads_returns_empty(self, tmp_path):
        out = str(tmp_path / "out.json")
        scraped = [_mock_lead()]
        result, MockInstantly = _run_with_mocks(scraped, [], dry_run=True, output_file=out)
        assert result == []

    def test_output_file_is_written(self, tmp_path):
        out = str(tmp_path / "results.json")
        leads = [_mock_lead()]
        _run_with_mocks(leads, leads, dry_run=True, output_file=out)
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert isinstance(data, list)
        assert len(data) == 1

    def test_output_directory_created_if_missing(self, tmp_path):
        out = str(tmp_path / "deep" / "nested" / "results.json")
        leads = [_mock_lead()]
        _run_with_mocks(leads, leads, dry_run=True, output_file=out)
        assert Path(out).exists()

    def test_outreach_failure_does_not_raise(self, tmp_path):
        """If Instantly push fails, pipeline should log the error, not crash."""
        out = str(tmp_path / "out.json")
        leads = [_mock_lead()]
        # Should not raise even if outreach fails
        _run_with_mocks(leads, leads, fail_outreach=True, output_file=out)

    def test_returns_verified_leads(self, tmp_path):
        out = str(tmp_path / "out.json")
        leads = [_mock_lead("a@acme.com"), _mock_lead("b@corp.com", "Corp")]
        result, _ = _run_with_mocks(leads, leads, dry_run=True, output_file=out)
        assert len(result) == 2
