"""Tests for src/personalization/website_researcher.py"""

import json
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config
from src.personalization.website_researcher import WebsiteResearcher


@pytest.fixture
def researcher():
    return WebsiteResearcher(config=make_config())


# ---------------------------------------------------------------------------
# scrape_website
# ---------------------------------------------------------------------------

class TestScrapeWebsite:
    def test_returns_markdown_content(self, researcher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"markdown": "# Welcome to ACME\nWe build things."}}
        with patch("requests.post", return_value=mock_resp):
            content = researcher.scrape_website("https://acme.com")
        assert "ACME" in content

    def test_no_firecrawl_key_returns_empty_without_api_call(self):
        r = WebsiteResearcher(config=make_config(firecrawl_key=""))
        with patch("requests.post") as mock_post:
            result = r.scrape_website("https://acme.com")
        mock_post.assert_not_called()
        assert result == ""

    def test_missing_data_key_returns_empty_string(self, researcher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        with patch("requests.post", return_value=mock_resp):
            assert researcher.scrape_website("https://acme.com") == ""


# ---------------------------------------------------------------------------
# analyze_with_gpt
# ---------------------------------------------------------------------------

EMPTY_RESULT = {"main_service": "", "specific_detail": "", "pain_point": "", "tech_stack": ""}


def _make_openai_response(content: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock_resp


class TestAnalyzeWithGpt:
    def test_plain_json_response(self, researcher):
        payload = {"main_service": "SaaS", "specific_detail": "won award",
                   "pain_point": "churn", "tech_stack": "React"}
        with patch("requests.post", return_value=_make_openai_response(json.dumps(payload))):
            result = researcher.analyze_with_gpt("website content here")
        assert result["main_service"] == "SaaS"
        assert result["pain_point"] == "churn"

    def test_code_block_json_response(self, researcher):
        payload = {"main_service": "Agency", "specific_detail": "case study",
                   "pain_point": "leads", "tech_stack": "WordPress"}
        content = f"```json\n{json.dumps(payload)}\n```"
        with patch("requests.post", return_value=_make_openai_response(content)):
            result = researcher.analyze_with_gpt("website content")
        assert result["main_service"] == "Agency"

    def test_code_block_without_language_tag(self, researcher):
        payload = {"main_service": "Shop", "specific_detail": "sale",
                   "pain_point": "cart abandonment", "tech_stack": "Shopify"}
        content = f"```\n{json.dumps(payload)}\n```"
        with patch("requests.post", return_value=_make_openai_response(content)):
            result = researcher.analyze_with_gpt("content")
        assert result["main_service"] == "Shop"

    def test_bare_backtick_edge_case_does_not_raise(self, researcher):
        """Bare ``` with no newline must not raise IndexError."""
        with patch("requests.post", return_value=_make_openai_response("```")):
            result = researcher.analyze_with_gpt("content")
        # Falls through to JSONDecodeError path → returns empty dict
        assert result == EMPTY_RESULT

    def test_no_choices_returns_empty(self, researcher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": []}
        with patch("requests.post", return_value=mock_resp):
            assert researcher.analyze_with_gpt("content") == EMPTY_RESULT

    def test_empty_content_skips_api_call(self, researcher):
        with patch("requests.post") as mock_post:
            result = researcher.analyze_with_gpt("   ")
        mock_post.assert_not_called()
        assert result == EMPTY_RESULT

    def test_invalid_json_returns_empty(self, researcher):
        with patch("requests.post", return_value=_make_openai_response("not json at all")):
            result = researcher.analyze_with_gpt("content")
        assert result == EMPTY_RESULT

    def test_content_truncated_to_8000_chars(self, researcher):
        """Content is sent capped at 8000 characters."""
        long_content = "x" * 20_000
        captured = {}

        def capture_post(url, **kwargs):
            captured["body"] = kwargs.get("json", {})
            return _make_openai_response('{"main_service":"","specific_detail":"","pain_point":"","tech_stack":""}')

        with patch("requests.post", side_effect=capture_post):
            researcher.analyze_with_gpt(long_content)

        sent_content = captured["body"]["messages"][1]["content"]
        assert len(sent_content) == 8000

    def test_research_calls_both_methods(self, researcher):
        with patch.object(researcher, "scrape_website", return_value="some markdown") as mock_scrape, \
             patch.object(researcher, "analyze_with_gpt", return_value=EMPTY_RESULT) as mock_analyze:
            researcher.research("https://acme.com")
        mock_scrape.assert_called_once_with("https://acme.com")
        mock_analyze.assert_called_once_with("some markdown")
