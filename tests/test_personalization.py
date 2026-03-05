"""Tests for the personalization modules."""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.personalization.email_writer import EmailWriter
from src.personalization.website_researcher import WebsiteResearcher


# ---------------------------------------------------------------------------
# EmailWriter tests
# ---------------------------------------------------------------------------

def _mock_config():
    cfg = MagicMock()
    cfg.anthropic_key = "test_key"
    cfg.firecrawl_key = "test_firecrawl"
    cfg.openai_key = "test_openai"
    return cfg


class TestEmailWriter:
    def setup_method(self):
        self.writer = EmailWriter(config=_mock_config())
        self.writer.client = MagicMock()

    def _set_claude_response(self, text: str):
        self.writer.client.messages.create.return_value = MagicMock(
            content=[MagicMock(text=text)]
        )

    def test_generate_first_line_returns_string(self):
        self._set_claude_response("Loved your recent blog post about scaling ops.")
        result = self.writer.generate_first_line(
            business_name="Acme Corp",
            specific_detail="recent blog post about scaling",
            pain_point="hiring bottleneck",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_first_line_strips_whitespace(self):
        self._set_claude_response("  Great work on your product launch.  ")
        result = self.writer.generate_first_line("Co", "product launch", "growth")
        assert result == "Great work on your product launch."

    def test_personalize_lead_adds_ai_first_line(self):
        self._set_claude_response("Noticed your expansion to five new cities.")
        lead = {
            "business_name": "Fast Pizza",
            "specific_detail": "expansion to five new cities",
            "pain_point": "managing delivery ops",
        }
        result = self.writer.personalize_lead(lead)
        assert "ai_first_line" in result
        assert result["ai_first_line"] == "Noticed your expansion to five new cities."

    def test_personalize_lead_sets_empty_string_on_error(self):
        self.writer.client.messages.create.side_effect = Exception("API down")
        lead = {"business_name": "Shop", "specific_detail": "x", "pain_point": "y"}
        result = self.writer.personalize_lead(lead)
        assert result["ai_first_line"] == ""

    def test_personalize_batch_processes_all_leads(self):
        self.writer.client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Custom line.")]
        )
        leads = [
            {"business_name": f"Co{i}", "specific_detail": "d", "pain_point": "p"}
            for i in range(3)
        ]
        results = self.writer.personalize_batch(leads)
        assert len(results) == 3
        assert all(r["ai_first_line"] == "Custom line." for r in results)


# ---------------------------------------------------------------------------
# WebsiteResearcher tests
# ---------------------------------------------------------------------------

class TestWebsiteResearcher:
    def setup_method(self):
        self.researcher = WebsiteResearcher(config=_mock_config())

    @patch("src.personalization.website_researcher.requests.post")
    def test_scrape_website_returns_markdown(self, mock_post):
        mock_post.return_value.json.return_value = {
            "data": {"markdown": "# Acme Corp\nWe build cloud software."}
        }
        mock_post.return_value.raise_for_status = MagicMock()

        content = self.researcher.scrape_website("https://acme.com")
        assert "Acme Corp" in content

    def test_scrape_website_returns_empty_without_firecrawl_key(self):
        cfg = MagicMock()
        cfg.firecrawl_key = ""
        researcher = WebsiteResearcher(config=cfg)
        result = researcher.scrape_website("https://example.com")
        assert result == ""

    @patch("src.personalization.website_researcher.requests.post")
    def test_analyze_with_gpt_parses_json(self, mock_post):
        payload = {
            "main_service": "Cloud CRM",
            "specific_detail": "launched SOC-2 compliance in Q4",
            "pain_point": "manual data entry",
            "tech_stack": "React, Django",
        }
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload)}}]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = self.researcher.analyze_with_gpt("some website content")
        assert result["main_service"] == "Cloud CRM"
        assert result["specific_detail"] == "launched SOC-2 compliance in Q4"

    @patch("src.personalization.website_researcher.requests.post")
    def test_analyze_with_gpt_handles_markdown_fences(self, mock_post):
        raw = '```json\n{"main_service":"SaaS","specific_detail":"x","pain_point":"y","tech_stack":"z"}\n```'
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": raw}}]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = self.researcher.analyze_with_gpt("content")
        assert result["main_service"] == "SaaS"

    def test_analyze_with_gpt_returns_empty_for_blank_content(self):
        result = self.researcher.analyze_with_gpt("")
        assert result == {
            "main_service": "",
            "specific_detail": "",
            "pain_point": "",
            "tech_stack": "",
        }

    @patch("src.personalization.website_researcher.requests.post")
    def test_analyze_with_gpt_returns_empty_on_bad_json(self, mock_post):
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "not valid json at all"}}]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        result = self.researcher.analyze_with_gpt("some content")
        assert result["main_service"] == ""
