#!/usr/bin/env python3
"""Standalone reply processor — classifies and routes prospect replies.

Can be triggered by a webhook, cron job, or manually.

Usage:
    python scripts/reply_processor.py --email "prospect@company.com" --reply "Sounds interesting, let's chat next week"
    python scripts/reply_processor.py --csv replies.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reply_handling.classifier import ReplyClassifier
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("reply_processor", log_file="logs/replies.log")


def process_single(email: str, reply_text: str):
    """Process a single reply."""
    config = get_config()
    classifier = ReplyClassifier(config)
    result = classifier.process_reply(email, reply_text)
    logger.info("Result: %s", json.dumps(result, indent=2))
    return result


def process_csv(csv_path: str, output_path: str | None = None):
    """Process a CSV of replies. Expected columns: email, reply_body."""
    config = get_config()
    classifier = ReplyClassifier(config)

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        replies = list(reader)

    logger.info("Processing %d replies from %s", len(replies), csv_path)

    results = []
    for reply in replies:
        email = reply.get("email", "")
        body = reply.get("reply_body", "")
        if not email or not body:
            continue
        result = classifier.process_reply(email, body)
        results.append(result)

    # Summary
    categories = {}
    for r in results:
        cat = r.get("category", "UNKNOWN")
        categories[cat] = categories.get(cat, 0) + 1

    logger.info("Classification summary: %s", json.dumps(categories))

    if output_path:
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info("Results written to %s", output_path)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Classify and route prospect replies using Claude AI."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--email", help="Prospect email for single reply processing."
    )
    group.add_argument(
        "--csv", help="Path to CSV of replies (columns: email, reply_body)."
    )
    parser.add_argument(
        "--reply", help="Reply text (required with --email)."
    )
    parser.add_argument(
        "--output", "-o", help="Output JSON file for batch results."
    )
    args = parser.parse_args()

    if args.email:
        if not args.reply:
            parser.error("--reply is required when using --email")
        process_single(args.email, args.reply)
    else:
        process_csv(args.csv, args.output)


if __name__ == "__main__":
    main()
