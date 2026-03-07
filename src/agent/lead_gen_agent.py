"""Lead Generation Agent — orchestrates the full pipeline using the
Anthropic Agent SDK with custom MCP tools wrapping each pipeline stage.

Architecture:
  Claude Opus 4.6 (Agent)
      |
      |-- scrape_leads       → GoogleMapsScraper
      |-- enrich_leads       → EmailEnricher (Prospeo + Hunter waterfall)
      |-- personalize_leads  → WebsiteResearcher + EmailWriter
      |-- push_to_outreach   → InstantlyClient
      |-- classify_reply     → ReplyClassifier
      `-- save_results       → local JSON file

The agent decides the order and branching logic autonomously based on
the prompt you give it.
"""

import json
import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from src.enrichment.waterfall import EmailEnricher
from src.outreach.instantly_client import InstantlyClient
from src.personalization.email_writer import EmailWriter
from src.personalization.website_researcher import WebsiteResearcher
from src.reply_handling.classifier import ReplyClassifier
from src.scraping.apify_google_maps import GoogleMapsScraper
from src.utils.config import get_config
from src.utils.logger import setup_logger

Path("logs").mkdir(exist_ok=True)
logger = setup_logger("lead_gen_agent", log_file="logs/agent.log")

# Lazy singleton — config is validated once on first tool call
_config = None


def _cfg():
    global _config
    if _config is None:
        _config = get_config()
    return _config


# ---------------------------------------------------------------------------
# Tool definitions
# All complex data (lead lists) is passed as JSON strings so the schema
# stays simple — Claude serialises/deserialises automatically.
# ---------------------------------------------------------------------------

@tool(
    "scrape_leads",
    (
        "Scrape leads from Google Maps using Apify. "
        "Pass 'queries' as a JSON array string, e.g. "
        '\'["barbers in Toronto","dentists in Austin"]\'. '
        "Returns JSON with 'leads' (list) and 'count' (int). "
        "Only leads that have an email are returned."
    ),
    {"queries": str},
)
async def scrape_leads(args):
    queries = json.loads(args["queries"])
    scraper = GoogleMapsScraper(_cfg())
    leads = scraper.scrape(queries)
    logger.info("scrape_leads: returned %d leads", len(leads))
    return {"content": [{"type": "text", "text": json.dumps({"leads": leads, "count": len(leads)})}]}


@tool(
    "enrich_leads",
    (
        "Enrich leads with verified email addresses using a Prospeo → Hunter.io "
        "waterfall. Only leads whose email passes Prospeo verification are kept. "
        "Pass 'leads' as a JSON array string (output from scrape_leads). "
        "Returns JSON with 'leads' and 'count'."
    ),
    {"leads": str},
)
async def enrich_leads(args):
    leads = json.loads(args["leads"])
    enricher = EmailEnricher(_cfg())
    verified = enricher.process_batch(leads)
    logger.info("enrich_leads: %d/%d leads verified", len(verified), len(leads))
    return {"content": [{"type": "text", "text": json.dumps({"leads": verified, "count": len(verified)})}]}


@tool(
    "personalize_leads",
    (
        "Research each lead's website (via Firecrawl + GPT-4o) and generate a "
        "personalised cold-email opening line (via Claude Sonnet). "
        "Adds 'ai_first_line', 'pain_point', 'specific_detail', and 'tech_stack' "
        "to each lead dict. "
        "Pass 'leads' as a JSON array string. "
        "Returns JSON with 'leads', 'personalized_count', and 'total'."
    ),
    {"leads": str},
)
async def personalize_leads(args):
    leads = json.loads(args["leads"])
    researcher = WebsiteResearcher(_cfg())
    writer = EmailWriter(_cfg())

    for lead in leads:
        website = lead.get("website", "")
        if website:
            try:
                research = researcher.research(website)
                lead.update(research)
            except Exception as exc:
                logger.warning(
                    "Website research failed for %s (%s): %s",
                    lead.get("business_name", "unknown"), website, exc,
                )
        writer.personalize_lead(lead)

    personalized_count = sum(1 for l in leads if l.get("ai_first_line"))
    logger.info("personalize_leads: %d/%d leads personalized", personalized_count, len(leads))
    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "leads": leads,
                "personalized_count": personalized_count,
                "total": len(leads),
            }),
        }]
    }


@tool(
    "push_to_outreach",
    (
        "Push personalized leads to an Instantly.ai campaign in batches of 100. "
        "Pass 'leads' as a JSON array string and 'campaign_id' as a string "
        "(leave empty to use the campaign from .env). "
        "Returns JSON with 'success', 'pushed' count, and the API response."
    ),
    {"leads": str, "campaign_id": str},
)
async def push_to_outreach(args):
    leads = json.loads(args["leads"])
    campaign_id = args.get("campaign_id", "").strip() or None
    instantly = InstantlyClient(_cfg())
    try:
        result = instantly.add_leads_batch(leads, campaign_id=campaign_id)
        logger.info("push_to_outreach: pushed %d leads", len(leads))
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"success": True, "pushed": len(leads), "result": result}),
            }]
        }
    except Exception as exc:
        logger.error("push_to_outreach failed: %s", exc)
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({"success": False, "error": str(exc)}),
            }]
        }


@tool(
    "classify_reply",
    (
        "Classify a prospect's reply email using Claude and route it to the "
        "right action. Categories: INTERESTED, NOT_INTERESTED, MEETING_REQUEST, "
        "QUESTION, OUT_OF_OFFICE, UNSUBSCRIBE. "
        "Returns JSON with 'email', 'category', 'action', and (for QUESTION) 'draft'."
    ),
    {"email": str, "reply_text": str},
)
async def classify_reply(args):
    email = args["email"]
    reply_text = args["reply_text"]
    classifier = ReplyClassifier(_cfg())
    result = classifier.process_reply(email, reply_text)
    logger.info("classify_reply: %s → %s", email, result.get("category"))
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


@tool(
    "save_results",
    (
        "Save a list of leads to a JSON file. "
        "Pass 'leads' as a JSON array string and 'output_path' as the file path "
        "(e.g. 'output/run_2026.json'). Creates parent directories automatically."
    ),
    {"leads": str, "output_path": str},
)
async def save_results(args):
    leads = json.loads(args["leads"])
    output_path = args.get("output_path", "output/agent_results.json").strip()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2, default=str)
    logger.info("save_results: saved %d leads to %s", len(leads), output_path)
    return {"content": [{"type": "text", "text": f"Saved {len(leads)} leads to {output_path}"}]}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI Lead Generation Agent. You orchestrate a cold-outreach
pipeline by calling tools in the right order and making smart decisions at each stage.

PIPELINE ORDER:
  1. scrape_leads        — Google Maps → raw leads with emails
  2. enrich_leads        — verify emails via Prospeo + Hunter.io
  3. personalize_leads   — research websites + write AI first lines
  4. push_to_outreach    — push to Instantly.ai (skip for dry runs)
  5. save_results        — always save final leads to a file

DATA PASSING RULES:
- Lead lists are passed as JSON-serialised strings between tools.
- Always extract the "leads" key from each tool response before passing to the next.
- Example: result = scrape_leads(queries='[...]') → pass result["leads"] as
  JSON string to enrich_leads(leads='[...]').

DECISION RULES:
- If scrape_leads returns 0 leads: stop, explain why, suggest different queries.
- If enrich_leads returns 0 verified leads: stop, report the drop-off rate.
- Report the count at every stage (scraped → verified → personalized → pushed).
- For DRY RUN requests: complete all stages EXCEPT push_to_outreach.
- Always call save_results at the end, even on dry runs.
- Use the output path "output/<timestamp_or_descriptive_name>.json" unless told otherwise.

REPLY CLASSIFICATION:
- For classify_reply tasks, always report the category and recommended action.
- For INTERESTED or MEETING_REQUEST: note that a Slack alert was sent.
- For QUESTION: include the AI-drafted response in your summary.
"""


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def _build_server():
    return create_sdk_mcp_server(
        "lead-gen-tools",
        tools=[
            scrape_leads,
            enrich_leads,
            personalize_leads,
            push_to_outreach,
            classify_reply,
            save_results,
        ],
    )


async def run_agent(
    prompt: str,
    dry_run: bool = False,
    max_turns: int = 25,
    verbose: bool = True,
) -> str | None:
    """Run the Lead Generation Agent and return its final result text."""
    server = _build_server()

    full_prompt = prompt
    if dry_run:
        full_prompt += (
            "\n\n[DRY RUN] Do NOT call push_to_outreach. "
            "Complete all other stages and save results."
        )

    options = ClaudeAgentOptions(
        mcp_servers={"lead-gen": server},
        system_prompt=SYSTEM_PROMPT,
        max_turns=max_turns,
        permission_mode="dontAsk",
        model="claude-opus-4-6",
    )

    result_text = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(full_prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and verbose:
                        print(block.text, end="", flush=True)
            elif isinstance(message, ResultMessage):
                result_text = message.result
                if verbose:
                    print("\n")

    return result_text


# ---------------------------------------------------------------------------
# Convenience entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Lead Gen Agent interactively.")
    parser.add_argument("prompt", help="Natural language instruction for the agent")
    parser.add_argument("--dry-run", action="store_true", help="Skip Instantly push")
    parser.add_argument("--max-turns", type=int, default=25)
    args = parser.parse_args()

    anyio.run(run_agent, args.prompt, args.dry_run, args.max_turns, True)
