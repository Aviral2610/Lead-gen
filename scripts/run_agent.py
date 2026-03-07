#!/usr/bin/env python3
"""CLI for the Lead Generation Agent.

The agent uses Claude Opus 4.6 to autonomously orchestrate:
  scrape → enrich → personalize → push to Instantly

Usage examples:
    # Full pipeline (dry run — no emails sent)
    python scripts/run_agent.py \\
        "Scrape 50 barbers in Toronto and dentists in Austin, enrich and personalize them" \\
        --dry-run

    # Full pipeline with outreach push
    python scripts/run_agent.py \\
        "Find 100 plumbers in NYC, enrich emails, write personalized first lines, then push to campaign"

    # Classify a reply
    python scripts/run_agent.py \\
        "Classify this reply from john@plumbing.com: 'Sounds interesting, let's chat next week'"

    # Custom output path
    python scripts/run_agent.py \\
        "Scrape auto repair shops in Chicago and save to output/chicago_auto.json" \\
        --dry-run
"""

import argparse
import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.lead_gen_agent import run_agent


def main():
    parser = argparse.ArgumentParser(
        description="AI Lead Generation Agent — natural language pipeline orchestration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "prompt",
        help="Natural language instruction (e.g. 'Scrape barbers in Toronto and push to Instantly')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all stages except the Instantly push (safe for testing).",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=25,
        help="Maximum agent reasoning turns (default: 25).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress streaming output; only print the final result.",
    )
    args = parser.parse_args()

    result = anyio.run(
        run_agent,
        args.prompt,
        args.dry_run,
        args.max_turns,
        not args.quiet,
    )

    if args.quiet and result:
        print(result)


if __name__ == "__main__":
    main()
