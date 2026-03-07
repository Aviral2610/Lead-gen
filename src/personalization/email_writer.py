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

    # Angle-specific instructions injected into the prompt so the first
    # line naturally sets up the right pitch hook.
    _ANGLE_HINTS: dict[str, str] = {
        "bloomberg_cost": (
            "The email will pitch a free Bloomberg Terminal alternative. "
            "Reference the detail in a way that leads naturally into a "
            "conversation about data costs or tool limitations."
        ),
        "ai_differentiation": (
            "The email will pitch AI-powered financial research features "
            "(GenAI insights, investor personas, cross-domain analysis). "
            "Reference the detail in a way that opens to an AI/analytics angle."
        ),
        "data_engineering": (
            "The email will pitch a unified financial data pipeline with 100+ "
            "connectors. Reference the detail in a way that opens to a "
            "data-stack or API conversation."
        ),
        "education": (
            "The email will pitch a free Bloomberg alternative for students. "
            "Reference the detail in a way that connects to teaching, "
            "student access, or curriculum."
        ),
    }

    @rate_limit(min_interval=0.5)
    @retry_with_backoff(max_retries=2)
    def generate_first_line(
        self,
        business_name: str,
        specific_detail: str,
        pain_point: str,
        product_context: str = "",
        email_angle: str = "",
    ) -> str:
        """Generate a personalized opening line for a cold email.

        Returns a single sentence (under 20 words) that references
        a specific detail about the prospect naturally.

        Optional args:
            product_context: Short description of the product being pitched
                             (e.g. "Fincept Terminal — free Bloomberg alternative").
            email_angle:     One of the keys in _ANGLE_HINTS that steers the
                             tone toward the right pitch hook.
        """
        prompt = (
            "You are writing a cold email first line.\n\n"
            f"Prospect: {business_name}\n"
            f"Website detail: {specific_detail}\n"
            f"Pain point: {pain_point}\n"
        )

        if product_context:
            prompt += f"Product being pitched: {product_context}\n"

        angle_hint = self._ANGLE_HINTS.get(email_angle, "")
        if angle_hint:
            prompt += f"Angle context: {angle_hint}\n"

        prompt += (
            "\nWrite ONLY a personalized opening line (1 sentence, under 20 words) "
            "that references the specific detail naturally. Do NOT use generic "
            "compliments. Do NOT mention AI. Sound like a real person who "
            "actually visited their website."
        )

        msg = self.client.messages.create(
            model="claude-sonnet-4-6",
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

        Optional lead keys:
            product_context: Passed through to generate_first_line.
            email_angle:     Passed through to generate_first_line.
        """
        try:
            first_line = self.generate_first_line(
                business_name=lead.get("business_name", ""),
                specific_detail=lead.get("specific_detail", ""),
                pain_point=lead.get("pain_point", ""),
                product_context=lead.get("product_context", ""),
                email_angle=lead.get("email_angle", ""),
            )
            lead["ai_first_line"] = first_line
        except Exception as e:
            logger.error(
                "Failed to personalize lead %s: %s",
                lead.get("business_name", "unknown"),
                e,
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
            sum(1 for l in results if l.get("ai_first_line")),
            len(leads),
        )
        return results
