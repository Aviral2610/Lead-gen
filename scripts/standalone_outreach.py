#!/usr/bin/env python3
"""Standalone outreach pipeline — no paid third-party APIs required.

This script:
  1. Scrapes the web (Google → company websites) to find prospect emails.
  2. Optionally generates AI-personalised first lines via Claude.
  3. Sends cold emails directly through your Hostinger mailbox via SMTP.

Usage:
    python scripts/standalone_outreach.py --queries "hedge fund New York" "fintech London"
    python scripts/standalone_outreach.py --queries "asset manager" --limit 20 --no-ai
    python scripts/standalone_outreach.py --test-smtp          # just verify SMTP works

Required .env keys:
    HOSTINGER_EMAIL        your full Hostinger email address
    HOSTINGER_PASSWORD     your Hostinger email password
    HOSTINGER_SENDER_NAME  display name (e.g. "John from Fincept")

Optional .env keys:
    HOSTINGER_SMTP_HOST    default: smtp.hostinger.com
    HOSTINGER_SMTP_PORT    default: 587
    ANTHROPIC_API_KEY      needed only if --no-ai is NOT passed
    MAX_EMAILS_PER_INBOX_PER_DAY  safety cap (default 50)

Edit SUBJECT_TEMPLATE and BODY_TEMPLATE below to customise your email copy.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Make sure src/ is importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from src.scraping.web_scraper import WebScraper
from src.outreach.hostinger_mailer import HostingerMailer
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Email templates — edit these to match your pitch
# ---------------------------------------------------------------------------

SUBJECT_TEMPLATE = "Quick question about {{business_name}}"

BODY_TEMPLATE = """\
{{ai_first_line}}

I noticed {{business_name}} and thought there might be a fit.

Fincept Terminal is a free Bloomberg alternative — real-time data across 150+ markets, portfolio analytics, and AI-powered research tools at zero cost.

Would it be worth a 15-minute call this week to see if it's useful for your team?

{{sender_name}}

--
Unsubscribe: reply with "unsubscribe" and I'll remove you immediately.
"""

# Fallback first line when AI is disabled or fails
_FALLBACK_FIRST_LINE = "I came across your firm while researching the space."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_ai_first_lines(leads: list[dict]) -> list[dict]:
    """Enrich leads with Claude-generated personalised opening lines."""
    try:
        from src.personalization.email_writer import EmailWriter
        writer = EmailWriter()
    except Exception as e:
        logger.warning("Could not load EmailWriter (%s) — using fallback first line.", e)
        for lead in leads:
            lead.setdefault("ai_first_line", _FALLBACK_FIRST_LINE)
        return leads

    for lead in leads:
        if lead.get("ai_first_line"):
            continue
        # Use page description as the "specific detail" if no research was done
        specific_detail = lead.get("page_description") or lead.get("page_title") or ""
        try:
            line = writer.generate_first_line(
                business_name=lead.get("business_name", ""),
                specific_detail=specific_detail,
                pain_point="high data costs and fragmented financial tools",
            )
            lead["ai_first_line"] = line
        except Exception as e:
            logger.warning("AI first line failed for %s: %s", lead.get("business_name"), e)
            lead["ai_first_line"] = _FALLBACK_FIRST_LINE

    return leads


def _save_leads(leads: list[dict], out_dir: Path) -> Path:
    """Save scraped leads to a CSV for review."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"leads_{stamp}.csv"
    if not leads:
        return path
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(leads[0].keys()))
        writer.writeheader()
        writer.writerows(leads)
    logger.info("Leads saved to %s", path)
    return path


def _load_leads_from_csv(path: str) -> list[dict]:
    """Load leads from a previously saved CSV instead of scraping."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Standalone outreach: scrape emails from the web + send via Hostinger SMTP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--queries", nargs="+", metavar="QUERY",
        help='Search queries to find prospects, e.g. "hedge fund New York"',
    )
    p.add_argument(
        "--results-per-query", type=int, default=10,
        help="Max websites to check per search query (default: 10).",
    )
    p.add_argument(
        "--limit", type=int, default=50,
        help="Max emails to send in this run (default: 50).",
    )
    p.add_argument(
        "--delay", type=float, default=60.0,
        help="Seconds to wait between each send (default: 60). Lower = more risk of blocks.",
    )
    p.add_argument(
        "--no-ai", action="store_true",
        help="Skip Claude personalisation and use a generic first line.",
    )
    p.add_argument(
        "--from-csv", metavar="PATH",
        help="Skip scraping and load leads from a previously saved CSV.",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Scrape and prepare emails but do NOT actually send. Saves leads to CSV.",
    )
    p.add_argument(
        "--test-smtp", action="store_true",
        help="Just test the SMTP connection and exit.",
    )
    p.add_argument(
        "--out-dir", default="logs/outreach",
        help="Directory to save leads CSV (default: logs/outreach).",
    )
    return p


def main():
    parser = _build_parser()
    args = parser.parse_args()

    # ── SMTP test ─────────────────────────────────────────────────────────
    if args.test_smtp:
        mailer = HostingerMailer()
        ok = mailer.test_connection()
        sys.exit(0 if ok else 1)

    # ── Validate inputs ───────────────────────────────────────────────────
    if not args.from_csv and not args.queries:
        parser.error("Provide --queries or --from-csv.")

    # ── Load or scrape leads ──────────────────────────────────────────────
    if args.from_csv:
        logger.info("Loading leads from CSV: %s", args.from_csv)
        leads = _load_leads_from_csv(args.from_csv)
    else:
        scraper = WebScraper()
        leads = scraper.scrape(
            queries=args.queries,
            results_per_query=args.results_per_query,
        )

    if not leads:
        logger.warning("No leads found. Exiting.")
        sys.exit(0)

    logger.info("Leads found: %d", len(leads))

    # ── AI personalisation ────────────────────────────────────────────────
    if not args.no_ai:
        logger.info("Generating AI first lines with Claude…")
        leads = _add_ai_first_lines(leads)
    else:
        for lead in leads:
            lead.setdefault("ai_first_line", _FALLBACK_FIRST_LINE)

    # Add sender_name placeholder for template rendering
    sender_name = os.getenv("HOSTINGER_SENDER_NAME", "")
    for lead in leads:
        lead["sender_name"] = sender_name

    # ── Save leads ────────────────────────────────────────────────────────
    out_dir = Path(args.out_dir)
    csv_path = _save_leads(leads, out_dir)
    print(f"\nLeads CSV: {csv_path}")
    print(f"Total leads: {len(leads)}")

    # ── Dry run ───────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY RUN] No emails sent. Review the CSV above and re-run without --dry-run.")
        _preview_email(leads[0], sender_name)
        sys.exit(0)

    # ── Confirm before sending ────────────────────────────────────────────
    _preview_email(leads[0], sender_name)
    print(f"\nReady to send to {min(args.limit, len(leads))} recipients via {os.getenv('HOSTINGER_EMAIL', '?')}.")
    answer = input("Proceed? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    # ── Send ──────────────────────────────────────────────────────────────
    mailer = HostingerMailer(daily_limit=args.limit, delay=args.delay)
    stats = mailer.send_bulk(
        leads=leads[:args.limit],
        subject_template=SUBJECT_TEMPLATE,
        body_template=BODY_TEMPLATE,
    )

    print(f"\nDone — sent: {stats['sent']}, failed: {stats['failed']}, skipped: {stats['skipped']}")


def _preview_email(lead: dict, sender_name: str):
    """Print a rendered preview of the first email."""
    from src.outreach.hostinger_mailer import _fill_template
    subject = _fill_template(SUBJECT_TEMPLATE, lead)
    body = _fill_template(BODY_TEMPLATE, lead)
    print("\n" + "─" * 60)
    print("PREVIEW (first lead)")
    print("─" * 60)
    print(f"To:      {lead.get('email', '?')}")
    print(f"Subject: {subject}")
    print("Body:")
    print(body)
    print("─" * 60)


if __name__ == "__main__":
    main()
