#!/usr/bin/env python3
"""Initialize a Google Spreadsheet with the required tabs and headers
for the lead generation CRM.

Run this once before using the pipeline with --sheets-credentials.

Usage:
    python scripts/setup_sheets.py --credentials path/to/service_account.json
    python scripts/setup_sheets.py --credentials creds.json --spreadsheet-id SHEET_ID
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.oauth2 import service_account
from googleapiclient.discovery import build

from src.crm.sheets_crm import (
    RAW_LEADS_COLUMNS,
    ENRICHED_LEADS_COLUMNS,
    CAMPAIGN_TRACKER_COLUMNS,
)
from src.utils.config import get_config
from src.utils.logger import setup_logger

logger = setup_logger("setup_sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# (tab title, column headers)
TABS = [
    ("Raw Leads", RAW_LEADS_COLUMNS),
    ("Enriched Leads", ENRICHED_LEADS_COLUMNS),
    ("Campaign Tracker", CAMPAIGN_TRACKER_COLUMNS),
]


def _get_existing_sheet_titles(sheets_service, spreadsheet_id: str) -> list[str]:
    meta = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def setup_spreadsheet(credentials_file: str, spreadsheet_id: str):
    """Create missing tabs and write headers to a Google Spreadsheet."""
    creds = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets()

    existing_titles = _get_existing_sheet_titles(service, spreadsheet_id)
    logger.info("Existing tabs: %s", existing_titles)

    # Build requests: add missing sheets
    add_requests = []
    for title, _ in TABS:
        if title not in existing_titles:
            add_requests.append(
                {"addSheet": {"properties": {"title": title}}}
            )

    if add_requests:
        sheets.batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": add_requests},
        ).execute()
        logger.info("Created %d new tab(s).", len(add_requests))

    # Write headers to each tab (row 1)
    data = []
    for title, columns in TABS:
        range_name = f"{title}!A1"
        data.append({"range": range_name, "values": [columns]})

    sheets.values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    logger.info("Headers written to all tabs.")
    logger.info("Spreadsheet is ready: https://docs.google.com/spreadsheets/d/%s", spreadsheet_id)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Google Sheets CRM tabs and headers."
    )
    parser.add_argument(
        "--credentials", "-c", required=True,
        help="Path to Google service account JSON credentials file.",
    )
    parser.add_argument(
        "--spreadsheet-id", "-s", default=None,
        help=(
            "Google Spreadsheet ID. Defaults to GOOGLE_SHEETS_SPREADSHEET_ID "
            "from your .env file."
        ),
    )
    args = parser.parse_args()

    spreadsheet_id = args.spreadsheet_id
    if not spreadsheet_id:
        config = get_config()
        spreadsheet_id = config.sheets_spreadsheet_id
    if not spreadsheet_id:
        parser.error(
            "Provide --spreadsheet-id or set GOOGLE_SHEETS_SPREADSHEET_ID in .env"
        )

    setup_spreadsheet(args.credentials, spreadsheet_id)


if __name__ == "__main__":
    main()
