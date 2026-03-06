"""Tests for src/crm/sheets_crm.py"""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_config
from src.crm.sheets_crm import (
    SheetsCRM, RAW_LEADS_COLUMNS, ENRICHED_LEADS_COLUMNS, CAMPAIGN_TRACKER_COLUMNS
)


@pytest.fixture
def crm():
    """Create a SheetsCRM with all Google API calls mocked out."""
    instance = SheetsCRM.__new__(SheetsCRM)
    instance.cfg = make_config()
    instance.spreadsheet_id = "spreadsheet-123"
    instance.sheets = MagicMock()
    return instance


def _setup_get_responses(crm, responses: dict):
    """Wire crm.sheets.values().get() to return different mocks by range."""
    def get_mock(spreadsheetId, range):
        result = MagicMock()
        result.execute.return_value = responses.get(range, {"values": []})
        return result

    crm.sheets.values.return_value.get.side_effect = get_mock


def _setup_append(crm):
    crm.sheets.values.return_value.append.return_value.execute.return_value = {}


def _setup_update(crm):
    crm.sheets.values.return_value.update.return_value.execute.return_value = {}


# ---------------------------------------------------------------------------
# append_raw_leads — no mutation
# ---------------------------------------------------------------------------

class TestAppendRawLeads:
    def test_does_not_add_keys_to_input_dict(self, crm):
        _setup_append(crm)
        lead = {"email": "a@a.com", "business_name": "A"}
        original_keys = set(lead.keys())
        crm.append_raw_leads([lead])
        assert set(lead.keys()) == original_keys
        assert "scraped_date" not in lead
        assert "source" not in lead

    def test_returns_number_of_rows_appended(self, crm):
        _setup_append(crm)
        leads = [{"email": "a@a.com"}, {"email": "b@b.com"}]
        assert crm.append_raw_leads(leads) == 2

    def test_calls_sheets_api_once(self, crm):
        _setup_append(crm)
        crm.append_raw_leads([{"email": "a@a.com"}])
        crm.sheets.values.return_value.append.assert_called_once()

    def test_empty_list_appends_nothing(self, crm):
        _setup_append(crm)
        assert crm.append_raw_leads([]) == 0


# ---------------------------------------------------------------------------
# append_enriched_leads — no mutation
# ---------------------------------------------------------------------------

class TestAppendEnrichedLeads:
    def test_does_not_add_enriched_date_to_input_dict(self, crm):
        _setup_append(crm)
        lead = {"email": "a@a.com", "email_verified": True}
        original_keys = set(lead.keys())
        crm.append_enriched_leads([lead])
        assert set(lead.keys()) == original_keys
        assert "enriched_date" not in lead

    def test_returns_number_of_rows_appended(self, crm):
        _setup_append(crm)
        leads = [{"email": f"{i}@x.com"} for i in range(3)]
        assert crm.append_enriched_leads(leads) == 3

    def test_enriched_date_written_to_sheet_not_to_input(self, crm):
        _setup_append(crm)
        lead = {"email": "a@a.com"}
        crm.append_enriched_leads([lead])
        # The row passed to the API should contain the date
        call_body = crm.sheets.values.return_value.append.call_args[1]["body"]
        row = call_body["values"][0]
        date_col_idx = ENRICHED_LEADS_COLUMNS.index("enriched_date")
        assert row[date_col_idx] != ""  # date was filled in
        # But the input dict should not have it
        assert "enriched_date" not in lead


# ---------------------------------------------------------------------------
# read_unenriched_leads — filtering logic
# ---------------------------------------------------------------------------

class TestReadUnenrichedLeads:
    def test_skips_already_enriched_emails(self, crm):
        _setup_get_responses(crm, {
            "Raw Leads!A:J": {"values": [
                RAW_LEADS_COLUMNS,        # header
                ["Shop A", "a@a.com"] + [""] * 8,
                ["Shop B", "b@b.com"] + [""] * 8,
            ]},
            "Enriched Leads!B:B": {"values": [["email"], ["a@a.com"]]},
        })
        leads = crm.read_unenriched_leads()
        assert len(leads) == 1
        assert leads[0]["email"] == "b@b.com"

    def test_empty_email_cell_in_enriched_tab_does_not_block_leads(self, crm):
        """An empty-string email row in Enriched tab must not be added to the set."""
        _setup_get_responses(crm, {
            "Raw Leads!A:J": {"values": [
                RAW_LEADS_COLUMNS,
                ["Shop A", "a@a.com"] + [""] * 8,
            ]},
            # Enriched tab has a row with an empty email cell
            "Enriched Leads!B:B": {"values": [["email"], [""]]},
        })
        leads = crm.read_unenriched_leads()
        # Shop A is NOT in the enriched set (empty string was filtered), so it must appear
        assert any(l["email"] == "a@a.com" for l in leads)

    def test_case_insensitive_matching(self, crm):
        _setup_get_responses(crm, {
            "Raw Leads!A:J": {"values": [
                RAW_LEADS_COLUMNS,
                ["Shop A", "A@A.COM"] + [""] * 8,
            ]},
            "Enriched Leads!B:B": {"values": [["email"], ["a@a.com"]]},
        })
        leads = crm.read_unenriched_leads()
        assert len(leads) == 0  # A@A.COM should match enriched a@a.com

    def test_returns_empty_if_only_header_row(self, crm):
        _setup_get_responses(crm, {
            "Raw Leads!A:J": {"values": [RAW_LEADS_COLUMNS]},
            "Enriched Leads!B:B": {"values": [["email"]]},
        })
        assert crm.read_unenriched_leads() == []

    def test_respects_limit(self, crm):
        raw_data = [RAW_LEADS_COLUMNS] + [[f"Biz{i}", f"biz{i}@x.com"] + [""] * 8 for i in range(20)]
        _setup_get_responses(crm, {
            "Raw Leads!A:J": {"values": raw_data},
            "Enriched Leads!B:B": {"values": [["email"]]},
        })
        leads = crm.read_unenriched_leads(limit=5)
        assert len(leads) == 5


# ---------------------------------------------------------------------------
# update_campaign_status
# ---------------------------------------------------------------------------

class TestUpdateCampaignStatus:
    def test_appends_new_row_when_email_not_found(self, crm):
        _setup_get_responses(crm, {
            "Campaign Tracker!A:I": {"values": [CAMPAIGN_TRACKER_COLUMNS]},
        })
        _setup_append(crm)
        crm.update_campaign_status("new@b.com", {"status": "sent"})
        crm.sheets.values.return_value.append.assert_called_once()

    def test_updates_existing_row_when_email_found(self, crm):
        _setup_get_responses(crm, {
            "Campaign Tracker!A:I": {"values": [
                CAMPAIGN_TRACKER_COLUMNS,
                ["existing@b.com"] + [""] * 8,
            ]},
        })
        _setup_update(crm)
        crm.update_campaign_status("existing@b.com", {"status": "opened"})
        crm.sheets.values.return_value.update.assert_called_once()

    def test_email_matching_is_case_insensitive(self, crm):
        _setup_get_responses(crm, {
            "Campaign Tracker!A:I": {"values": [
                CAMPAIGN_TRACKER_COLUMNS,
                ["Owner@Shop.COM"] + [""] * 8,
            ]},
        })
        _setup_update(crm)
        crm.update_campaign_status("owner@shop.com", {"status": "replied"})
        crm.sheets.values.return_value.update.assert_called_once()
