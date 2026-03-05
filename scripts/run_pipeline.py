#!/usr/bin/env python3
"""Main pipeline orchestrator — runs the full lead generation pipeline
end-to-end: scrape → enrich → personalize → push to outreach.

This is the standalone Python alternative to running the n8n workflows.
Use this for testing, one-off runs, or environments without n8n.

Usage:
    # Scrape Google Maps with custom queries
    python scripts/run_pipeline.py --queries "barbers in Toronto" "dentists in Austin"

    # Use a named ICP profile from config/icp_templates.json
    python scripts/run_pipeline.py --icp "Local Service Businesses"

    # Dry-run (no outreach push)
    python scripts/run_pipeline.py --queries "plumbers in NYC" --dry-run

    # Save results to Google Sheets CRM
    python scripts/run_pipeline.py --queries "roofers in Dallas" \\
        --sheets-credentials path/to/service_account.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraping.apify_google_maps import GoogleMapsScraper
from src.scraping.apollo_scraper import ApolloScraper
from src.enrichment.waterfall import EmailEnricher
from src.personalization.website_researcher import WebsiteResearcher
from src.personalization.email_writer import EmailWriter
from src.outreach.instantly_client import InstantlyClient
from src.crm.sheets_crm import SheetsCRM
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("pipeline", log_file="logs/pipeline.log")


def _load_icp_profiles() -> list[dict]:
    """Load ICP profiles from config/icp_templates.json."""
    profiles_path = Path(__file__).resolve().parent.parent / "config" / "icp_templates.json"
    if not profiles_path.exists():
        return []
    with open(profiles_path) as f:
        data = json.load(f)
    return data.get("profiles", [])


def _find_icp_profile(name: str) -> dict | None:
    """Find an ICP profile by name (case-insensitive)."""
    for profile in _load_icp_profiles():
        if profile["name"].lower() == name.lower():
            return profile
    return None


def _scrape_gmaps(config, search_queries: list[str]) -> list[dict]:
    """Run Google Maps scraping."""
    scraper = GoogleMapsScraper(config)
    leads = scraper.scrape(search_queries)
    logger.info("Scraped %d unique leads from Google Maps.", len(leads))
    return leads


def _scrape_apollo(config, profile: dict) -> list[dict]:
    """Run Apollo.io scraping using ICP profile parameters."""
    if not config.apollo_key:
        raise EnvironmentError(
            "APOLLO_API_KEY is required for Apollo ICP profiles. "
            "Set it in your .env file."
        )
    scraper = ApolloScraper(api_key=config.apollo_key, config=config)
    leads = []
    pages = max(1, config.max_leads_per_search // 25)
    for page in range(1, pages + 1):
        batch = scraper.search_people(
            titles=profile.get("titles", []),
            locations=profile.get("locations"),
            employee_ranges=profile.get("employee_ranges"),
            industries=profile.get("industries"),
            page=page,
        )
        leads.extend(batch)
        if len(batch) < 25:
            break  # no more results
    logger.info("Scraped %d leads from Apollo.io.", len(leads))
    return leads


def run_pipeline(
    search_queries: list[str] | None = None,
    icp_name: str | None = None,
    dry_run: bool = False,
    skip_outreach: bool = False,
    output_file: str | None = None,
    sheets_credentials: str | None = None,
):
    """Execute the full lead generation pipeline.

    Provide either ``search_queries`` (Google Maps) or ``icp_name`` (loads
    profile from config/icp_templates.json which may use Apollo or Google Maps).
    """
    config = get_config()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # --- Resolve ICP profile ---
    profile: dict | None = None
    if icp_name:
        profile = _find_icp_profile(icp_name)
        if profile is None:
            available = [p["name"] for p in _load_icp_profiles()]
            raise ValueError(
                f"ICP profile '{icp_name}' not found. "
                f"Available profiles: {available}"
            )
        logger.info(
            "Loaded ICP profile: %s (source=%s)", profile["name"], profile.get("source")
        )

    # --- Stage 1: Scraping ---
    logger.info("=== Stage 1: Scraping ===")
    if profile:
        source = profile.get("source", "google_maps")
        if source == "apollo":
            leads = _scrape_apollo(config, profile)
        else:
            queries = profile.get("search_queries", search_queries or [])
            leads = _scrape_gmaps(config, queries)
    else:
        if not search_queries:
            raise ValueError("Provide --queries or --icp.")
        leads = _scrape_gmaps(config, search_queries)

    if not leads:
        logger.warning("No leads found. Exiting.")
        return []

    # --- Save raw leads to Google Sheets (optional) ---
    crm: SheetsCRM | None = None
    if sheets_credentials:
        try:
            crm = SheetsCRM(credentials_file=sheets_credentials, config=config)
            crm.append_raw_leads(leads)
            logger.info("Saved %d raw leads to Google Sheets.", len(leads))
        except Exception as e:
            logger.warning("Failed to save raw leads to Sheets: %s", e)

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
        writer.personalize_lead(lead)

    personalized_count = sum(1 for l in verified_leads if l.get("ai_first_line"))
    logger.info("%d/%d leads personalized.", personalized_count, len(verified_leads))

    # --- Save enriched leads to Google Sheets (optional) ---
    if crm:
        try:
            crm.append_enriched_leads(verified_leads)
            logger.info("Saved %d enriched leads to Google Sheets.", len(verified_leads))
        except Exception as e:
            logger.warning("Failed to save enriched leads to Sheets: %s", e)

    # --- Save results to JSON ---
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
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--queries", "-q", nargs="+",
        help='Google Maps search queries (e.g., "barbers in Toronto")',
    )
    source_group.add_argument(
        "--icp",
        help=(
            'Named ICP profile from config/icp_templates.json '
            '(e.g., "Local Service Businesses")'
        ),
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
    parser.add_argument(
        "--sheets-credentials",
        help="Path to Google service account JSON for Sheets CRM integration.",
    )
    args = parser.parse_args()

    run_pipeline(
        search_queries=args.queries,
        icp_name=args.icp,
        dry_run=args.dry_run,
        skip_outreach=args.skip_outreach,
        output_file=args.output,
        sheets_credentials=args.sheets_credentials,
    )


if __name__ == "__main__":
    main()
