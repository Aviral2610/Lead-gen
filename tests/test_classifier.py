"""Tests for the AI reply classifier."""

import pytest
from unittest.mock import MagicMock, patch

from src.reply_handling.classifier import ReplyClassifier, VALID_CATEGORIES


def _mock_config():
    cfg = MagicMock()
    cfg.anthropic_key = "test_key"
    cfg.slack_webhook_url = ""
    return cfg


class TestReplyClassifier:
    def setup_method(self):
        self.classifier = ReplyClassifier(config=_mock_config())
        # Replace the Anthropic client with a mock
        self.classifier.client = MagicMock()

    def _mock_claude_response(self, text: str):
        msg = MagicMock()
        msg.content = [MagicMock(text=text)]
        self.classifier.client.messages.create.return_value = msg

    def test_classify_returns_valid_category(self):
        self._mock_claude_response("INTERESTED")
        result = self.classifier.classify("Yes, I'd love to learn more!")
        assert result == "INTERESTED"
        assert result in VALID_CATEGORIES

    def test_classify_normalizes_to_uppercase(self):
        self._mock_claude_response("interested")
        result = self.classifier.classify("sounds good")
        assert result == "INTERESTED"

    def test_classify_defaults_to_question_on_unexpected(self):
        self._mock_claude_response("CONFUSED")
        result = self.classifier.classify("what is this about?")
        assert result == "QUESTION"

    @pytest.mark.parametrize("category,expected_action", [
        ("INTERESTED", "slack_alert"),
        ("MEETING_REQUEST", "slack_alert"),
        ("NOT_INTERESTED", "log_and_remove"),
        ("QUESTION", "draft_response"),
        ("OUT_OF_OFFICE", "reschedule"),
        ("UNSUBSCRIBE", "suppress"),
    ])
    def test_route_returns_correct_action(self, category, expected_action):
        if category == "QUESTION":
            # draft_response calls Claude — mock it
            self._mock_claude_response("Here's a helpful response.")
        result = self.classifier.route("test@example.com", "some reply text", category)
        assert result["action"] == expected_action
        assert result["email"] == "test@example.com"
        assert result["category"] == category

    def test_route_question_includes_draft(self):
        self._mock_claude_response("Here is a draft response.")
        result = self.classifier.route("a@b.com", "What's your pricing?", "QUESTION")
        assert "draft" in result
        assert result["draft"] == "Here is a draft response."

    def test_process_reply_full_flow(self):
        # First call: classify, second call: draft (if QUESTION)
        self.classifier.client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(text="NOT_INTERESTED")]),
        ]
        result = self.classifier.process_reply("lead@co.com", "Please don't email me.")
        assert result["category"] == "NOT_INTERESTED"
        assert result["action"] == "log_and_remove"

    def test_valid_categories_set(self):
        assert "INTERESTED" in VALID_CATEGORIES
        assert "NOT_INTERESTED" in VALID_CATEGORIES
        assert "MEETING_REQUEST" in VALID_CATEGORIES
        assert "OUT_OF_OFFICE" in VALID_CATEGORIES
        assert "UNSUBSCRIBE" in VALID_CATEGORIES
        assert "QUESTION" in VALID_CATEGORIES
        assert len(VALID_CATEGORIES) == 6
