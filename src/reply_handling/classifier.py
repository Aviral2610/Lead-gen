"""AI reply classifier — uses Claude to categorize prospect replies
and route them to the appropriate handler.

Categories:
  INTERESTED       — Prospect shows interest, wants to learn more
  NOT_INTERESTED   — Explicit rejection or disinterest
  MEETING_REQUEST  — Wants to schedule a call/meeting
  OUT_OF_OFFICE    — Auto-reply / OOO message
  UNSUBSCRIBE      — Wants to be removed from the list
  QUESTION         — Asks a question that needs a human answer
"""

import anthropic
import requests

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff

logger = setup_logger(__name__)

VALID_CATEGORIES = {
    "INTERESTED",
    "NOT_INTERESTED",
    "MEETING_REQUEST",
    "OUT_OF_OFFICE",
    "UNSUBSCRIBE",
    "QUESTION",
}


class ReplyClassifier:
    """Classify email replies using Claude and route them."""

    def __init__(self, config=None):
        self.cfg = config or get_config()
        self.client = anthropic.Anthropic(api_key=self.cfg.anthropic_key)

    @rate_limit(min_interval=0.5)
    @retry_with_backoff(max_retries=2)
    def classify(self, reply_text: str) -> str:
        """Classify a reply into one of the predefined categories."""
        msg = self.client.messages.create(
            model=self.cfg.claude_model,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify this email reply into exactly one category: "
                        "INTERESTED, NOT_INTERESTED, MEETING_REQUEST, "
                        "OUT_OF_OFFICE, UNSUBSCRIBE, QUESTION.\n"
                        "Reply with ONLY the category.\n\n"
                        f'Reply: "{reply_text}"'
                    ),
                }
            ],
        )
        category = msg.content[0].text.strip().upper()

        if category not in VALID_CATEGORIES:
            logger.warning("Unexpected category '%s', defaulting to QUESTION.", category)
            category = "QUESTION"

        logger.info("Classified reply as: %s", category)
        return category

    def route(self, email: str, reply_text: str, category: str) -> dict:
        """Route a classified reply to the appropriate action.

        Returns a dict describing the action taken.
        """
        action = {"email": email, "category": category, "action": ""}

        if category in ("INTERESTED", "MEETING_REQUEST"):
            action["action"] = "slack_alert"
            self._send_slack_alert(email, reply_text, category)

        elif category == "NOT_INTERESTED":
            action["action"] = "log_and_remove"

        elif category == "QUESTION":
            action["action"] = "draft_response"
            action["draft"] = self._draft_response(reply_text)

        elif category == "OUT_OF_OFFICE":
            action["action"] = "reschedule"

        elif category == "UNSUBSCRIBE":
            action["action"] = "suppress"

        logger.info("Routed reply from %s -> %s", email, action["action"])
        return action

    def _send_slack_alert(self, email: str, reply_text: str, category: str):
        """Send a Slack notification for high-priority replies."""
        if not self.cfg.slack_webhook_url:
            logger.info("No Slack webhook configured; skipping alert for %s.", email)
            return

        payload = {
            "text": (
                f":email: *{category}* reply from `{email}`\n"
                f"```{reply_text[:500]}```"
            )
        }
        try:
            requests.post(
                self.cfg.slack_webhook_url, json=payload, timeout=10
            )
        except requests.exceptions.RequestException as e:
            logger.warning("Slack notification failed: %s", type(e).__name__)

    @rate_limit(min_interval=0.5)
    def _draft_response(self, reply_text: str) -> str:
        """Draft a response to a prospect's question for human review."""
        msg = self.client.messages.create(
            model=self.cfg.claude_model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "A prospect replied to our cold email with a question. "
                        "Draft a helpful, concise reply (2-3 sentences max) "
                        "that a sales rep can review and send. Be professional "
                        "but conversational.\n\n"
                        f'Prospect reply: "{reply_text}"'
                    ),
                }
            ],
        )
        return msg.content[0].text.strip()

    def process_reply(self, email: str, reply_text: str) -> dict:
        """Full pipeline: classify and route a reply."""
        category = self.classify(reply_text)
        return self.route(email, reply_text, category)
