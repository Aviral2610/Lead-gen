"""Tests for src/reply_handling/classifier.py"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config


@pytest.fixture
def classifier():
    from src.reply_handling.classifier import ReplyClassifier
    c = ReplyClassifier(config=make_config())
    # Fresh mock per test to prevent side_effect bleed across tests.
    c.client = MagicMock()
    return c


def _set_classify_response(classifier, text: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    classifier.client.messages.create.return_value = mock_msg


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

class TestClassify:
    @pytest.mark.parametrize("category", [
        "INTERESTED", "NOT_INTERESTED", "MEETING_REQUEST",
        "OUT_OF_OFFICE", "UNSUBSCRIBE", "QUESTION",
    ])
    def test_all_valid_categories_pass_through(self, classifier, category):
        _set_classify_response(classifier, category)
        assert classifier.classify("some reply") == category

    def test_invalid_category_defaults_to_question(self, classifier):
        _set_classify_response(classifier, "MAYBE")
        assert classifier.classify("Hmm, I'll think about it.") == "QUESTION"

    def test_lowercase_response_normalized(self, classifier):
        _set_classify_response(classifier, "not_interested")
        # .upper() on "not_interested" → "NOT_INTERESTED" which is valid
        assert classifier.classify("No thanks.") == "NOT_INTERESTED"

    def test_extra_whitespace_stripped(self, classifier):
        _set_classify_response(classifier, "  INTERESTED  ")
        assert classifier.classify("Yes!") == "INTERESTED"


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------

class TestRoute:
    def test_interested_sends_slack_alert(self, classifier):
        with patch.object(classifier, "_send_slack_alert") as mock_slack:
            action = classifier.route("a@b.com", "Interested!", "INTERESTED")
        assert action["action"] == "slack_alert"
        mock_slack.assert_called_once()

    def test_meeting_request_sends_slack_alert(self, classifier):
        with patch.object(classifier, "_send_slack_alert") as mock_slack:
            action = classifier.route("a@b.com", "Let's schedule", "MEETING_REQUEST")
        assert action["action"] == "slack_alert"
        mock_slack.assert_called_once()

    def test_not_interested_logs_and_removes(self, classifier):
        action = classifier.route("a@b.com", "Not interested", "NOT_INTERESTED")
        assert action["action"] == "log_and_remove"

    def test_question_drafts_response(self, classifier):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Here is my reply.")]
        classifier.client.messages.create.return_value = mock_msg
        action = classifier.route("a@b.com", "What is the price?", "QUESTION")
        assert action["action"] == "draft_response"
        assert action.get("draft") == "Here is my reply."

    def test_out_of_office_reschedules(self, classifier):
        action = classifier.route("a@b.com", "I'm OOO until Monday", "OUT_OF_OFFICE")
        assert action["action"] == "reschedule"

    def test_unsubscribe_suppresses(self, classifier):
        action = classifier.route("a@b.com", "Remove me please", "UNSUBSCRIBE")
        assert action["action"] == "suppress"

    def test_action_dict_always_contains_email_and_category(self, classifier):
        action = classifier.route("x@y.com", "bye", "NOT_INTERESTED")
        assert action["email"] == "x@y.com"
        assert action["category"] == "NOT_INTERESTED"


# ---------------------------------------------------------------------------
# _send_slack_alert
# ---------------------------------------------------------------------------

class TestSlackAlert:
    def test_no_webhook_configured_skips_without_error(self):
        from src.reply_handling.classifier import ReplyClassifier
        c = ReplyClassifier(config=make_config(slack_webhook_url=""))
        with patch("requests.post") as mock_post:
            c._send_slack_alert("a@b.com", "hello", "INTERESTED")
        mock_post.assert_not_called()

    def test_sends_post_to_webhook(self, classifier):
        mock_resp = MagicMock()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            classifier._send_slack_alert("a@b.com", "hello", "INTERESTED")
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert call_url == classifier.cfg.slack_webhook_url

    def test_webhook_failure_does_not_raise(self, classifier):
        with patch("requests.post", side_effect=Exception("network error")):
            # Must not propagate the exception
            classifier._send_slack_alert("a@b.com", "hello", "INTERESTED")


# ---------------------------------------------------------------------------
# process_reply (full pipeline)
# ---------------------------------------------------------------------------

class TestProcessReply:
    def test_classify_and_route_called(self, classifier):
        with patch.object(classifier, "classify", return_value="NOT_INTERESTED") as mock_cls, \
             patch.object(classifier, "route", return_value={"action": "log_and_remove"}) as mock_route:
            result = classifier.process_reply("x@y.com", "No thanks")
        mock_cls.assert_called_once_with("No thanks")
        mock_route.assert_called_once_with("x@y.com", "No thanks", "NOT_INTERESTED")
        assert result["action"] == "log_and_remove"
