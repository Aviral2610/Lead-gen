"""Tests for src/personalization/email_writer.py"""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_config


@pytest.fixture
def writer():
    from src.personalization.email_writer import EmailWriter
    w = EmailWriter(config=make_config())
    # Replace with a fresh mock per test — the shared anthropic module mock
    # means all EmailWriter instances share the same client object, so a
    # side_effect set in one test would bleed into the next without this.
    w.client = MagicMock()
    return w


def _set_response(writer, text: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    writer.client.messages.create.return_value = mock_msg


# ---------------------------------------------------------------------------
# generate_first_line
# ---------------------------------------------------------------------------

class TestGenerateFirstLine:
    def test_returns_stripped_text(self, writer):
        _set_response(writer, "  Noticed your team just launched a new product.  ")
        result = writer.generate_first_line("Acme", "product launch", "scaling")
        assert result == "Noticed your team just launched a new product."

    def test_uses_correct_model(self, writer):
        _set_response(writer, "A first line.")
        writer.generate_first_line("Shop", "detail", "pain")
        call_kwargs = writer.client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_includes_business_name_in_prompt(self, writer):
        _set_response(writer, "A line.")
        writer.generate_first_line("ACME Corp", "award", "growth")
        prompt = writer.client.messages.create.call_args[1]["messages"][0]["content"]
        assert "ACME Corp" in prompt


# ---------------------------------------------------------------------------
# personalize_lead
# ---------------------------------------------------------------------------

class TestPersonalizeLead:
    def test_adds_ai_first_line_to_lead(self, writer):
        _set_response(writer, "Great opening line.")
        lead = {"business_name": "Acme", "specific_detail": "d", "pain_point": "p"}
        result = writer.personalize_lead(lead)
        assert result["ai_first_line"] == "Great opening line."

    def test_api_error_sets_empty_first_line(self, writer):
        writer.client.messages.create.side_effect = Exception("API error")
        lead = {"business_name": "Acme", "specific_detail": "d", "pain_point": "p"}
        result = writer.personalize_lead(lead)
        assert result["ai_first_line"] == ""

    def test_does_not_raise_on_api_error(self, writer):
        writer.client.messages.create.side_effect = RuntimeError("timeout")
        result = writer.personalize_lead({"business_name": "Shop"})
        assert "ai_first_line" in result  # key present, just empty

    def test_modifies_and_returns_same_dict(self, writer):
        _set_response(writer, "A line.")
        lead = {"business_name": "Biz"}
        result = writer.personalize_lead(lead)
        assert result is lead  # same dict object


# ---------------------------------------------------------------------------
# personalize_batch
# ---------------------------------------------------------------------------

class TestPersonalizeBatch:
    def test_processes_all_leads(self, writer):
        _set_response(writer, "A first line.")
        leads = [{"business_name": f"Biz{i}"} for i in range(4)]
        results = writer.personalize_batch(leads)
        assert len(results) == 4
        assert all(r["ai_first_line"] == "A first line." for r in results)

    def test_empty_batch_returns_empty(self, writer):
        assert writer.personalize_batch([]) == []
