"""Google Sheets CRM — lightweight lead tracking using Google Sheets API.

Sheet structure:
  Tab 1 (Raw Leads): business_name | email | phone | website | city |
                      category | rating | review_count | source | scraped_date
  Tab 2 (Enriched Leads): [all raw] + email_verified | enrichment_source |
                           ai_first_line | pain_point | specific_detail | enriched_date
  Tab 3 (Campaign Tracker): email | campaign_id | sent_date | opened |
                            replied | reply_sentiment | meeting_booked |
                            deal_value | status
"""

from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

from src.utils.config import get_config
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit

logger = setup_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

RAW_LEADS_COLUMNS = [
    "business_name", "email", "phone", "website", "city",
    "category", "rating", "review_count", "source", "scraped_date",
]

ENRICHED_LEADS_COLUMNS = RAW_LEADS_COLUMNS + [
    "email_verified", "enrichment_source", "ai_first_line",
    "pain_point", "specific_detail", "enriched_date",
]

CAMPAIGN_TRACKER_COLUMNS = [
    "email", "campaign_id", "sent_date", "opened", "replied",
    "reply_sentiment", "meeting_booked", "deal_value", "status",
]


class SheetsCRM:
    """Read/write leads to Google Sheets as a lightweight CRM."""

    def __init__(self, credentials_file: str, config=None):
        self.cfg = config or get_config()
        self.spreadsheet_id = self.cfg.sheets_spreadsheet_id

        creds = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES
        )
        self.service = build("sheets", "v4", credentials=creds)
        self.sheets = self.service.spreadsheets()

    @rate_limit(min_interval=0.5)
    def append_raw_leads(self, leads: list[dict]) -> int:
        """Append leads to the 'Raw Leads' tab. Returns rows added."""
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for lead in leads:
            lead["scraped_date"] = now
            lead.setdefault("source", "apify_gmaps")
            rows.append([str(lead.get(col, "")) for col in RAW_LEADS_COLUMNS])

        body = {"values": rows}
        self.sheets.values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Raw Leads!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        logger.info("Appended %d raw leads to Google Sheets.", len(rows))
        return len(rows)

    @rate_limit(min_interval=0.5)
    def append_enriched_leads(self, leads: list[dict]) -> int:
        """Append leads to the 'Enriched Leads' tab."""
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        for lead in leads:
            lead["enriched_date"] = now
            rows.append([str(lead.get(col, "")) for col in ENRICHED_LEADS_COLUMNS])

        body = {"values": rows}
        self.sheets.values().append(
            spreadsheetId=self.spreadsheet_id,
            range="Enriched Leads!A:P",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        logger.info("Appended %d enriched leads to Google Sheets.", len(rows))
        return len(rows)

    @rate_limit(min_interval=0.5)
    def read_unenriched_leads(self, limit: int = 100) -> list[dict]:
        """Read leads from 'Raw Leads' that haven't been enriched yet.

        Simple approach: read all raw leads, then check which emails
        are already in 'Enriched Leads' and return the difference.
        """
        # Read raw leads
        raw_result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Raw Leads!A:J",
        ).execute()
        raw_rows = raw_result.get("values", [])
        if len(raw_rows) <= 1:  # header only
            return []

        # Read already-enriched emails
        enriched_result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Enriched Leads!B:B",
        ).execute()
        enriched_emails = {
            row[0].lower()
            for row in enriched_result.get("values", [])[1:]
            if row
        }

        # Build lead dicts for unenriched rows
        headers = RAW_LEADS_COLUMNS
        leads = []
        for row in raw_rows[1:]:
            if len(row) < 2:
                continue
            lead = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            if lead["email"].lower() not in enriched_emails:
                leads.append(lead)
            if len(leads) >= limit:
                break

        logger.info("Found %d unenriched leads.", len(leads))
        return leads

    @rate_limit(min_interval=0.5)
    def update_campaign_status(self, email: str, updates: dict):
        """Update a row in 'Campaign Tracker' for a specific email."""
        result = self.sheets.values().get(
            spreadsheetId=self.spreadsheet_id,
            range="Campaign Tracker!A:I",
        ).execute()
        rows = result.get("values", [])

        target_row = None
        for i, row in enumerate(rows):
            if row and row[0].lower() == email.lower():
                target_row = i + 1  # 1-indexed
                break

        if target_row is None:
            # Add new row
            new_row = [str(updates.get(col, "")) for col in CAMPAIGN_TRACKER_COLUMNS]
            new_row[0] = email
            self.sheets.values().append(
                spreadsheetId=self.spreadsheet_id,
                range="Campaign Tracker!A:I",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [new_row]},
            ).execute()
        else:
            # Update existing row
            existing = rows[target_row - 1]
            while len(existing) < len(CAMPAIGN_TRACKER_COLUMNS):
                existing.append("")
            for key, val in updates.items():
                if key in CAMPAIGN_TRACKER_COLUMNS:
                    idx = CAMPAIGN_TRACKER_COLUMNS.index(key)
                    existing[idx] = str(val)
            self.sheets.values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"Campaign Tracker!A{target_row}:I{target_row}",
                valueInputOption="USER_ENTERED",
                body={"values": [existing]},
            ).execute()

        logger.info("Updated campaign tracker for %s.", email)
