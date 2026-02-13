"""Email personalization engine — uses Claude Sonnet to generate
natural, human-sounding personalized first lines for cold emails.

Design principle: AI should RESEARCH, not WRITE full emails.
Use LLMs to extract specific prospect details, then inject
into human-crafted templates."""

import anthropic

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit, retry_with_backoff

logger = setup_logger(__name__)


class EmailWriter:
    """Generate personalized email first lines using Claude."""

    def __init__(self, config=None):
        self.cfg = config or get_config()
        self.client = anthropic.Anthropic(api_key=self.cfg.anthropic_key)

    @rate_limit(min_interval=0.5)
    @retry_with_backoff(max_retries=2)
    def generate_first_line(
        self,
        business_name: str,
        specific_detail: str,
        pain_point: str,
    ) -> str:
        """Generate a personalized opening line for a cold email.

        Returns a single sentence (under 20 words) that references
        a specific detail about the prospect naturally.
        """
        prompt = (
            "You are writing a cold email first line.\n\n"
            f"Prospect: {business_name}\n"
            f"Website detail: {specific_detail}\n"
            f"Pain point: {pain_point}\n\n"
            "Write ONLY a personalized opening line (1 sentence, under 20 words) "
            "that references the specific detail naturally. Do NOT use generic "
            "compliments. Do NOT mention AI. Sound like a real person who "
            "actually visited their website."
        )

        msg = self.client.messages.create(
            model=self.cfg.claude_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        first_line = msg.content[0].text.strip()
        logger.info(
            "Generated first line for %s: %s", business_name, first_line[:60]
        )
        return first_line

    def personalize_lead(self, lead: dict) -> dict:
        """Add an AI-generated first line to a lead dict.

        Expects the lead to have 'business_name', 'specific_detail',
        and 'pain_point' keys (from the website research step).
        """
        try:
            first_line = self.generate_first_line(
                business_name=lead.get("business_name", ""),
                specific_detail=lead.get("specific_detail", ""),
                pain_point=lead.get("pain_point", ""),
            )
            lead["ai_first_line"] = first_line
        except anthropic.APIStatusError as e:
            logger.error(
                "Claude API error personalizing %s: HTTP %d",
                lead.get("business_name", "unknown"),
                e.status_code,
            )
            lead["ai_first_line"] = ""
        except anthropic.APIConnectionError as e:
            logger.error(
                "Claude connection error personalizing %s: %s",
                lead.get("business_name", "unknown"),
                type(e).__name__,
            )
            lead["ai_first_line"] = ""
        return lead

    def personalize_batch(self, leads: list[dict]) -> list[dict]:
        """Generate personalized first lines for a batch of leads."""
        results = []
        for lead in leads:
            results.append(self.personalize_lead(lead))
        logger.info(
            "Personalized %d/%d leads.",
            sum(1 for r in results if r.get("ai_first_line")),
            len(leads),
        )
        return results
