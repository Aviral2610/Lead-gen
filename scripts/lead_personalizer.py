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
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.personalization.email_writer import EmailWriter
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("lead_personalizer", log_file="logs/personalizer.log")


def process_csv(input_path: str, output_path: str, delay: float = 1.0):
    """Read enriched leads from CSV, personalize, and write output."""
    config = get_config()
    writer = EmailWriter(config)

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fields = reader.fieldnames or []
        leads = list(reader)

    logger.info("Loaded %d leads from %s", len(leads), input_path)

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

        time.sleep(delay)

    # Write output
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
    parser.add_argument(
        "--delay", "-d", type=float, default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    args = parser.parse_args()
    process_csv(args.input, args.output, args.delay)


if __name__ == "__main__":
    main()
