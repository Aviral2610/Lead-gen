#!/usr/bin/env python3
"""Main pipeline orchestrator — runs the full lead generation pipeline
end-to-end: scrape → enrich → personalize → push to outreach.

This is the standalone Python alternative to running the n8n workflows.
Use this for testing, one-off runs, or environments without n8n.

Usage:
    python scripts/run_pipeline.py --queries "barbers in Toronto" "dentists in Austin"
    python scripts/run_pipeline.py --queries "plumbers in NYC" --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraping.apify_google_maps import GoogleMapsScraper
from src.enrichment.waterfall import EmailEnricher
from src.personalization.website_researcher import WebsiteResearcher
from src.personalization.email_writer import EmailWriter
from src.outreach.instantly_client import InstantlyClient
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("pipeline", log_file="logs/pipeline.log")


def run_pipeline(
    search_queries: list[str],
    dry_run: bool = False,
    skip_outreach: bool = False,
    output_file: str | None = None,
):
    """Execute the full lead generation pipeline."""
    config = get_config()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # --- Stage 1: Scraping ---
    logger.info("=== Stage 1: Scraping (%d queries) ===", len(search_queries))
    scraper = GoogleMapsScraper(config)
    leads = scraper.scrape(search_queries)
    logger.info("Scraped %d unique leads with emails.", len(leads))

    if not leads:
        logger.warning("No leads found. Exiting.")
        return []

    # --- Stage 2: Enrichment & Verification ---
    logger.info("=== Stage 2: Enrichment & Verification ===")
    enricher = EmailEnricher(config)
    verified_leads = enricher.process_batch(leads)
    logger.info("%d leads verified after enrichment.", len(verified_leads))

    if not verified_leads:
        logger.warning("No verified leads. Exiting.")
        return []

    # --- Stage 3: Website Research + AI Personalization ---
    logger.info("=== Stage 3: AI Personalization ===")
    researcher = WebsiteResearcher(config)
    writer = EmailWriter(config)

    for lead in verified_leads:
        website = lead.get("website", "")
        if website:
            try:
                research = researcher.research(website)
                lead.update(research)
            except Exception as e:
                logger.warning("Research failed for %s: %s", website, e)

        lead = writer.personalize_lead(lead)

    personalized_count = sum(
        1 for l in verified_leads if l.get("ai_first_line")
    )
    logger.info(
        "%d/%d leads personalized.", personalized_count, len(verified_leads)
    )

    # --- Save intermediate results ---
    if output_file:
        out_path = output_file
    else:
        out_path = f"output/pipeline_results_{timestamp}.json"
        Path("output").mkdir(exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(verified_leads, f, indent=2, default=str)
    logger.info("Results saved to %s", out_path)

    # --- Stage 4: Push to Outreach ---
    if dry_run:
        logger.info("DRY RUN — skipping outreach push.")
        return verified_leads

    if skip_outreach:
        logger.info("Outreach push skipped by flag.")
        return verified_leads

    logger.info("=== Stage 4: Pushing to Instantly ===")
    instantly = InstantlyClient(config)
    try:
        instantly.add_leads_batch(verified_leads)
        logger.info("Pushed %d leads to Instantly.", len(verified_leads))
    except Exception as e:
        logger.error("Failed to push to Instantly: %s", e)

    # --- Summary ---
    logger.info("=== Pipeline Complete ===")
    logger.info("  Scraped:       %d", len(leads))
    logger.info("  Verified:      %d", len(verified_leads))
    logger.info("  Personalized:  %d", personalized_count)
    logger.info("  Output file:   %s", out_path)

    return verified_leads


def main():
    parser = argparse.ArgumentParser(
        description="Run the full AI lead generation pipeline."
    )
    parser.add_argument(
        "--queries", "-q", nargs="+", required=True,
        help='Search queries (e.g., "barbers in Toronto" "dentists in Austin")',
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run pipeline but don't push to outreach platform.",
    )
    parser.add_argument(
        "--skip-outreach", action="store_true",
        help="Skip the Instantly push step.",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output file path for results JSON.",
    )
    args = parser.parse_args()

    run_pipeline(
        search_queries=args.queries,
        dry_run=args.dry_run,
        skip_outreach=args.skip_outreach,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
