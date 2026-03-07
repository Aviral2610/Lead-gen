#!/usr/bin/env python3
"""Fincept Terminal — targeted outreach campaign.

Scrapes universities and financial firms from Google + LinkedIn,
selects the correct email template per segment, applies the right
salutation, and sends via Hostinger SMTP.

Segments targeted:
  1. University finance departments / MBA colleges  → Education template
  2. Hedge funds / asset managers                  → Bloomberg Cost template
  3. RIAs / family offices                         → Bloomberg Cost template
  4. Fintech startups                              → Data Engineering template
  5. Quant / research teams                        → AI Differentiation template

Usage:
    # Test SMTP credentials
    python scripts/fincept_outreach.py --test-smtp

    # Dry run — scrape + build emails, save CSV, NO sends
    python scripts/fincept_outreach.py --dry-run

    # Full run — scrape, personalise, send
    python scripts/fincept_outreach.py --limit 30 --delay 90

    # Re-send from a previously saved CSV
    python scripts/fincept_outreach.py --from-csv logs/outreach/fincept_YYYYMMDD.csv

Required .env:
    HOSTINGER_EMAIL        your Hostinger email
    HOSTINGER_PASSWORD     your Hostinger password
    HOSTINGER_SENDER_NAME  e.g. "Aviral from Fincept"

Optional .env:
    ANTHROPIC_API_KEY      for AI-personalised first lines
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.scraping.web_scraper import WebScraper
from src.scraping.linkedin_scraper import LinkedInScraper, build_salutation
from src.outreach.hostinger_mailer import HostingerMailer, _fill_template
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

SENDER_NAME = os.getenv("HOSTINGER_SENDER_NAME", "Aviral from Fincept")

# ===========================================================================
# Target segments
# ===========================================================================

SEGMENTS = [
    # ── Universities & Business Schools ─────────────────────────────────────
    {
        "name": "universities",
        "template": "education",
        "web_queries": [
            "finance department university India contact email",
            "MBA college finance faculty contact India",
            "business school finance professor email IIM",
            "CFA institute finance department email India",
            "finance department university Singapore contact",
            "business school finance Dubai UAE contact email",
        ],
        "linkedin_queries": [
            '"professor" OR "dean" "finance" "MBA" India',
            '"head of finance" OR "director finance" university India',
            '"professor finance" OR "faculty finance" IIM OR IIT OR ISB',
            '"director" "business school" India OR Singapore',
        ],
        "results_per_query": 8,
    },

    # ── Hedge Funds & Asset Managers ─────────────────────────────────────────
    {
        "name": "hedge_funds",
        "template": "bloomberg_cost",
        "web_queries": [
            "hedge fund Mumbai contact email",
            "hedge fund Delhi Bangalore contact",
            "asset management company India contact email",
            "portfolio management services India email",
            "boutique asset management Singapore contact",
            "investment management firm Dubai email",
            "hedge fund Kuala Lumpur contact email",
        ],
        "linkedin_queries": [
            '"portfolio manager" OR "fund manager" "hedge fund" India',
            '"chief investment officer" "asset management" India OR Singapore',
            '"managing partner" "investment" India OR Dubai',
            '"head of research" "asset manager" India OR Singapore',
        ],
        "results_per_query": 8,
    },

    # ── RIAs & Family Offices ────────────────────────────────────────────────
    {
        "name": "ria_family_office",
        "template": "bloomberg_cost",
        "web_queries": [
            "registered investment advisor India contact email",
            "family office India investment contact",
            "wealth management firm India email contact",
            "RIA firm Mumbai Delhi contact email",
        ],
        "linkedin_queries": [
            '"investment advisor" OR "wealth manager" India',
            '"family office" "director" OR "CIO" India OR Singapore',
        ],
        "results_per_query": 6,
    },

    # ── Fintech Startups ─────────────────────────────────────────────────────
    {
        "name": "fintech",
        "template": "data_engineering",
        "web_queries": [
            "fintech startup India market data contact email",
            "wealthtech company India contact",
            "trading platform startup India email",
            "investment platform fintech Singapore contact",
        ],
        "linkedin_queries": [
            '"CTO" OR "co-founder" fintech India market data',
            '"head of data" OR "VP engineering" fintech India',
        ],
        "results_per_query": 6,
    },

    # ── Quant / Research Teams ───────────────────────────────────────────────
    {
        "name": "quant_research",
        "template": "ai_differentiation",
        "web_queries": [
            "quantitative research firm India contact email",
            "quant fund India contact",
            "algorithmic trading firm India email",
        ],
        "linkedin_queries": [
            '"quantitative analyst" OR "quant researcher" India',
            '"head of research" "quant" OR "algorithmic" India',
        ],
        "results_per_query": 5,
    },
]

# ===========================================================================
# Email templates (keyed by angle name)
# ===========================================================================

TEMPLATES = {
    "education": {
        "subject": "Free Bloomberg alternative for your students — {{business_name}}",
        "body": """\
{{salutation}},

{{ai_first_line}}

Bloomberg academic licences typically cost institutions $10,000–$30,000 per year. Fincept Terminal is a free, open-source alternative that gives students the same depth — real-time global markets, portfolio analytics tools, and a full CFA Level 1/2/3 curriculum built in Python — at zero cost.

It runs on any student laptop (4 GB RAM, Windows/Mac/Linux) with no procurement process.

Would a 15-minute call make sense to see whether it fits your finance programme?

Best regards,
{{sender_name}}

--
You're receiving this because your institution appears on our outreach list for finance education tools.
Reply "unsubscribe" to be removed immediately.""",
    },

    "bloomberg_cost": {
        "subject": "Bloomberg alternative for {{business_name}} — zero cost",
        "body": """\
{{salutation}},

{{ai_first_line}}

Your team is likely spending $24,000+ per seat on Bloomberg Terminal. Fincept Terminal gives you the same institutional-grade coverage — real-time data across 150+ global markets, portfolio analytics, and GenAI-powered insights — at no cost.

It's open-source and already used by finance professionals in India, Singapore, and the Middle East.

Would it be worth a 15-minute call to see how it compares to what you're using today?

Best regards,
{{sender_name}}

--
Reply "unsubscribe" to be removed from further outreach.""",
    },

    "data_engineering": {
        "subject": "Unified financial data pipeline for {{business_name}}",
        "body": """\
{{salutation}},

{{ai_first_line}}

If your team is stitching together Polygon, Quandl, and DBnomics for your data pipeline, Fincept Terminal ships with 100+ pre-built connectors — including Kraken, PostgreSQL, and Kafka — plus a custom API mapper, all in one install.

It's open-source and free. No vendor lock-in, no per-seat fees.

Worth 15 minutes to walk through the connector architecture?

Best regards,
{{sender_name}}

--
Reply "unsubscribe" to be removed from further outreach.""",
    },

    "ai_differentiation": {
        "subject": "AI-powered research terminal — {{business_name}}",
        "body": """\
{{salutation}},

{{ai_first_line}}

Bloomberg still doesn't have a built-in AI that models Bridgewater's macro strategy or generates DCF models from natural language. Fincept Terminal does — for free.

It also integrates supply chain, geopolitics, and maritime data directly into portfolio analysis — something Bloomberg keeps siloed. Local LLM support is available for on-prem deployments.

Open to a 15-minute demo?

Best regards,
{{sender_name}}

--
Reply "unsubscribe" to be removed from further outreach.""",
    },
}

# ===========================================================================
# AI first-line generator (graceful fallback)
# ===========================================================================

_FALLBACKS = {
    "education": "I came across your institution while researching finance programmes that could benefit from modern data tools.",
    "bloomberg_cost": "I noticed your firm while researching asset managers who rely on Bloomberg for institutional-grade data.",
    "data_engineering": "I came across your company while looking at fintech teams building financial data pipelines.",
    "ai_differentiation": "I found your team while researching quantitative research firms in the region.",
}


def _generate_first_line(lead: dict, template_key: str) -> str:
    """Try Claude; fall back to a segment-specific generic line."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        return _FALLBACKS[template_key]
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        detail = (
            lead.get("page_description")
            or lead.get("page_title")
            or lead.get("business_name", "")
        )
        prompt = (
            f"Write a single cold-email opening sentence (under 20 words) "
            f"for a prospect named {lead.get('full_name') or lead.get('business_name')} "
            f"({lead.get('title', '')}) at {lead.get('business_name', '')}.\n"
            f"Website detail: {detail}\n"
            f"Sound like a real person. Don't mention AI. Don't use compliments."
        )
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.warning("Claude first-line failed for %s: %s", lead.get("business_name"), e)
        return _FALLBACKS[template_key]


# ===========================================================================
# Scraping orchestrator
# ===========================================================================

def scrape_segment(segment: dict, delay: float = 2.0) -> list[dict]:
    """Scrape both web and LinkedIn for a segment; tag each lead with template."""
    template_key = segment["template"]
    all_leads: list[dict] = []
    seen_emails: set[str] = set()

    def _add(leads: list[dict]):
        for lead in leads:
            email = lead.get("email", "").strip().lower()
            if email and email not in seen_emails:
                seen_emails.add(email)
                lead["template"] = template_key
                lead["segment"] = segment["name"]
                all_leads.append(lead)

    # Web scrape
    logger.info("[%s] Web scraping…", segment["name"])
    web = WebScraper()
    web_leads = web.scrape(
        queries=segment["web_queries"],
        results_per_query=segment["results_per_query"],
        delay_between_sites=delay,
    )
    _add(web_leads)

    # LinkedIn-via-Google
    logger.info("[%s] LinkedIn search…", segment["name"])
    li = LinkedInScraper(delay_between_lookups=delay)
    li_leads = li.scrape(
        queries=segment["linkedin_queries"],
        results_per_query=segment["results_per_query"],
    )
    _add(li_leads)

    logger.info("[%s] Total leads: %d", segment["name"], len(all_leads))
    return all_leads


# ===========================================================================
# Email builder
# ===========================================================================

def build_email(lead: dict, use_ai: bool = True) -> dict:
    """Fill in salutation, first line, and render subject + body."""
    template_key = lead.get("template", "bloomberg_cost")
    tmpl = TEMPLATES[template_key]

    # Salutation
    salutation = lead.get("salutation") or build_salutation(
        lead.get("title", ""),
        lead.get("first_name", ""),
        lead.get("last_name", ""),
    )
    lead["salutation"] = salutation

    # AI / fallback first line
    if use_ai:
        lead["ai_first_line"] = _generate_first_line(lead, template_key)
    else:
        lead["ai_first_line"] = _FALLBACKS[template_key]

    lead["sender_name"] = SENDER_NAME

    subject = _fill_template(tmpl["subject"], lead)
    body = _fill_template(tmpl["body"], lead)
    lead["rendered_subject"] = subject
    lead["rendered_body"] = body
    return lead


# ===========================================================================
# CSV helpers
# ===========================================================================

def save_leads(leads: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"fincept_{stamp}.csv"
    if not leads:
        return path
    fieldnames = list(leads[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(leads)
    logger.info("Leads saved → %s", path)
    return path


def load_leads(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ===========================================================================
# Preview
# ===========================================================================

def print_preview(lead: dict):
    print("\n" + "─" * 65)
    print("EMAIL PREVIEW")
    print("─" * 65)
    print(f"Segment  : {lead.get('segment', '?')}")
    print(f"Template : {lead.get('template', '?')}")
    print(f"To       : {lead.get('full_name') or lead.get('business_name')} <{lead.get('email')}>")
    print(f"Subject  : {lead.get('rendered_subject', '?')}")
    print(f"Body:\n{lead.get('rendered_body', '?')}")
    print("─" * 65)


# ===========================================================================
# CLI
# ===========================================================================

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fincept targeted outreach — universities + financial firms.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Scrape and build emails but do NOT send.")
    p.add_argument("--test-smtp", action="store_true",
                   help="Only test SMTP connection and exit.")
    p.add_argument("--from-csv", metavar="PATH",
                   help="Skip scraping; load from an existing leads CSV.")
    p.add_argument("--segments", nargs="+",
                   choices=[s["name"] for s in SEGMENTS],
                   help="Only run these segments (default: all).")
    p.add_argument("--limit", type=int, default=50,
                   help="Max emails to send per run (default: 50).")
    p.add_argument("--delay", type=float, default=90.0,
                   help="Seconds between sends (default: 90).")
    p.add_argument("--no-ai", action="store_true",
                   help="Skip Claude first-line generation.")
    p.add_argument("--out-dir", default="logs/outreach",
                   help="Directory for lead CSVs (default: logs/outreach).")
    return p


def main():
    args = _parser().parse_args()

    # ── SMTP test ────────────────────────────────────────────────────────────
    if args.test_smtp:
        ok = HostingerMailer().test_connection()
        sys.exit(0 if ok else 1)

    # ── Load or scrape ───────────────────────────────────────────────────────
    if args.from_csv:
        print(f"Loading from CSV: {args.from_csv}")
        leads = load_leads(args.from_csv)
    else:
        active_segments = [
            s for s in SEGMENTS
            if not args.segments or s["name"] in args.segments
        ]
        leads = []
        for seg in active_segments:
            leads.extend(scrape_segment(seg))

    if not leads:
        print("No leads found. Exiting.")
        sys.exit(0)

    print(f"\nLeads found: {len(leads)}")

    # ── Build emails ─────────────────────────────────────────────────────────
    print("Building emails…")
    built: list[dict] = []
    for lead in leads:
        try:
            built.append(build_email(lead, use_ai=not args.no_ai))
        except Exception as e:
            logger.error("Failed to build email for %s: %s", lead.get("email"), e)

    # ── Save CSV ─────────────────────────────────────────────────────────────
    csv_path = save_leads(built, Path(args.out_dir))
    print(f"CSV saved : {csv_path}")

    # ── Preview ──────────────────────────────────────────────────────────────
    if built:
        print_preview(built[0])

    # ── Summary by segment ───────────────────────────────────────────────────
    print("\nSummary by segment:")
    seg_counts: dict[str, int] = {}
    for lead in built:
        seg_counts[lead.get("segment", "?")] = seg_counts.get(lead.get("segment", "?"), 0) + 1
    for seg, count in seg_counts.items():
        print(f"  {seg:20s} {count} leads")

    # ── Dry run ──────────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY RUN] No emails sent. Review CSV and re-run without --dry-run.")
        sys.exit(0)

    # ── Confirm ──────────────────────────────────────────────────────────────
    send_count = min(args.limit, len(built))
    print(f"\nReady to send {send_count} emails via {os.getenv('HOSTINGER_EMAIL', '?')}.")
    print(f"Delay between sends: {args.delay}s  (estimated time: {send_count * args.delay / 60:.0f} min)")
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    # ── Send ─────────────────────────────────────────────────────────────────
    mailer = HostingerMailer(daily_limit=args.limit, delay=args.delay)
    stats = mailer.send_bulk(
        leads=built[:send_count],
        subject_template="{{rendered_subject}}",
        body_template="{{rendered_body}}",
    )

    print(f"\nDone — sent: {stats['sent']}, failed: {stats['failed']}, skipped: {stats['skipped']}")
    print(f"Full log: logs/")


if __name__ == "__main__":
    main()
