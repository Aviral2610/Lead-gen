#!/usr/bin/env python3
"""Standalone batch lead personalizer — processes a CSV of enriched leads
through Claude to generate personalized email first lines.

Usage:
    python scripts/lead_personalizer.py --input enriched_leads.csv --output personalized_leads.csv

Cost: ~$2-5 per 1,000 leads using Claude Sonnet.
"""

import argparse
import csv
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.personalization.email_writer import EmailWriter
from src.utils.config import get_config
from src.utils.logger import setup_logger

Path("logs").mkdir(exist_ok=True)
logger = setup_logger("lead_personalizer", log_file="logs/personalizer.log")


def process_csv(input_path: str, output_path: str):
    """Read enriched leads from CSV, personalize, and write output."""
    config = get_config()
    writer = EmailWriter(config)

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fields = reader.fieldnames or []
        leads = list(reader)

    if not input_fields:
        logger.error("Input CSV '%s' has no headers or is empty.", input_path)
        raise SystemExit(1)

    logger.info("Loaded %d leads from %s", len(leads), input_path)

    # Deduplicate by email (case-insensitive), keeping first occurrence
    seen_emails: set[str] = set()
    deduped: list[dict] = []
    for lead in leads:
        email = lead.get("email", "").strip().lower()
        if email and email in seen_emails:
            logger.info("Skipping duplicate email: %s", email)
            continue
        if email:
            seen_emails.add(email)
        deduped.append(lead)
    if len(deduped) < len(leads):
        logger.info(
            "Removed %d duplicate email(s). Processing %d unique leads.",
            len(leads) - len(deduped), len(deduped),
        )
    leads = deduped

    output_fields = list(input_fields)
    if "ai_first_line" not in output_fields:
        output_fields.append("ai_first_line")

    results = []
    success = 0
    for i, lead in enumerate(leads, 1):
        try:
            lead = writer.personalize_lead(lead)
            if lead.get("ai_first_line"):
                success += 1
        except Exception as e:
            logger.error("Error personalizing lead %d: %s", i, e)
            lead["ai_first_line"] = ""

        results.append(lead)

        if i % 50 == 0:
            logger.info("Progress: %d/%d leads processed (%d successful).",
                         i, len(leads), success)

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        dict_writer = csv.DictWriter(f, fieldnames=output_fields,
                                      extrasaction="ignore")
        dict_writer.writeheader()
        dict_writer.writerows(results)

    logger.info(
        "Done. %d/%d leads personalized. Output written to %s",
        success, len(leads), output_path,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Batch personalize leads using Claude AI."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to enriched leads CSV"
    )
    parser.add_argument(
        "--output", "-o", default="personalized_leads.csv",
        help="Path to output CSV (default: personalized_leads.csv)",
    )
    args = parser.parse_args()
    process_csv(args.input, args.output)


if __name__ == "__main__":
    main()
