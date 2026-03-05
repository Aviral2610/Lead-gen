"""Tests for the Google Sheets CRM module."""

import sys
from unittest.mock import MagicMock, patch

# Mock the entire google stack before sheets_crm is imported,
# so tests can run without the native cryptography / cffi dependencies.
_google_mocks = {
    "google": MagicMock(),
    "google.oauth2": MagicMock(),
    "google.oauth2.service_account": MagicMock(),
    "googleapiclient": MagicMock(),
    "googleapiclient.discovery": MagicMock(),
}
for mod, mock in _google_mocks.items():
    sys.modules.setdefault(mod, mock)

from src.crm.sheets_crm import (  # noqa: E402
    SheetsCRM,
    RAW_LEADS_COLUMNS,
    ENRICHED_LEADS_COLUMNS,
    CAMPAIGN_TRACKER_COLUMNS,
)


def _make_crm():
    """Build a SheetsCRM with all Google API calls mocked out."""
    crm = SheetsCRM.__new__(SheetsCRM)
    crm.cfg = MagicMock()
    crm.cfg.sheets_spreadsheet_id = "sheet_id_123"
    crm.spreadsheet_id = "sheet_id_123"
    crm.service = MagicMock()
    crm.sheets = MagicMock()
    return crm


class TestColumnDefinitions:
    def test_raw_leads_columns_count(self):
        assert len(RAW_LEADS_COLUMNS) == 10

    def test_enriched_columns_superset_of_raw(self):
        for col in RAW_LEADS_COLUMNS:
            assert col in ENRICHED_LEADS_COLUMNS

    def test_enriched_has_verification_fields(self):
        extra = set(ENRICHED_LEADS_COLUMNS) - set(RAW_LEADS_COLUMNS)
        assert "email_verified" in extra
        assert "enrichment_source" in extra
        assert "ai_first_line" in extra

    def test_campaign_tracker_columns(self):
        assert "email" in CAMPAIGN_TRACKER_COLUMNS
        assert "campaign_id" in CAMPAIGN_TRACKER_COLUMNS
        assert "reply_sentiment" in CAMPAIGN_TRACKER_COLUMNS
        assert "meeting_booked" in CAMPAIGN_TRACKER_COLUMNS


class TestSheetsCRM:
    def setup_method(self):
        self.crm = _make_crm()

    def test_append_raw_leads_calls_api(self):
        leads = [{"business_name": "Coffee Co", "email": "hi@co.com"}]
        self.crm.append_raw_leads(leads)
        self.crm.sheets.values.return_value.append.assert_called_once()

    def test_append_raw_leads_returns_count(self):
        leads = [{"business_name": f"Co{i}", "email": f"a{i}@b.com"} for i in range(3)]
        self.crm.sheets.values.return_value.append.return_value.execute.return_value = {}
        result = self.crm.append_raw_leads(leads)
        assert result == 3

    def test_append_raw_leads_sets_scraped_date(self):
        leads = [{"business_name": "Shop", "email": "s@shop.com"}]
        self.crm.append_raw_leads(leads)
        assert "scraped_date" in leads[0]

    def test_append_enriched_leads_calls_api(self):
        leads = [{"email": "a@b.com", "business_name": "B"}]
        self.crm.append_enriched_leads(leads)
        self.crm.sheets.values.return_value.append.assert_called_once()

    def test_append_enriched_leads_returns_count(self):
        leads = [{"email": f"x{i}@y.com"} for i in range(4)]
        self.crm.sheets.values.return_value.append.return_value.execute.return_value = {}
        result = self.crm.append_enriched_leads(leads)
        assert result == 4

    def test_read_unenriched_leads_excludes_enriched_emails(self):
        raw_values = [
            RAW_LEADS_COLUMNS,
            ["Shop A", "a@shop.com"] + [""] * 8,
            ["Shop B", "b@shop.com"] + [""] * 8,
        ]
        enriched_values = [["email"], ["a@shop.com"]]
        execute = self.crm.sheets.values.return_value.get.return_value.execute
        execute.side_effect = [
            {"values": raw_values},
            {"values": enriched_values},
        ]
        leads = self.crm.read_unenriched_leads()
        assert len(leads) == 1
        assert leads[0]["email"] == "b@shop.com"

    def test_read_unenriched_leads_empty_when_no_raw(self):
        execute = self.crm.sheets.values.return_value.get.return_value.execute
        execute.side_effect = [
            {"values": [RAW_LEADS_COLUMNS]},
            {"values": []},
        ]
        assert self.crm.read_unenriched_leads() == []

    def test_update_campaign_status_appends_new_email(self):
        self.crm.sheets.values.return_value.get.return_value.execute.return_value = {
            "values": [CAMPAIGN_TRACKER_COLUMNS]
        }
        self.crm.update_campaign_status("new@co.com", {"status": "sent"})
        self.crm.sheets.values.return_value.append.assert_called_once()

    def test_update_campaign_status_updates_existing_row(self):
        existing_rows = [
            CAMPAIGN_TRACKER_COLUMNS,
            ["existing@co.com"] + [""] * (len(CAMPAIGN_TRACKER_COLUMNS) - 1),
        ]
        self.crm.sheets.values.return_value.get.return_value.execute.return_value = {
            "values": existing_rows
        }
        self.crm.update_campaign_status("existing@co.com", {"status": "replied"})
        self.crm.sheets.values.return_value.update.assert_called_once()
