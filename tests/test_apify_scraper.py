"""Tests for src/scraping/apify_google_maps.py"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config
from src.scraping.apify_google_maps import GoogleMapsScraper


@pytest.fixture
def scraper():
    return GoogleMapsScraper(config=make_config())


# ---------------------------------------------------------------------------
# clean_lead
# ---------------------------------------------------------------------------

class TestCleanLead:
    def test_maps_all_fields(self, scraper):
        raw = {
            "title": "Joe's Barber",
            "email": "joe@joes.com",
            "phone": "555-1234",
            "website": "https://joes.com",
            "address": "123 Main St",
            "totalScore": 4.5,
            "reviewsCount": 42,
            "categoryName": "Barber",
            "city": "Toronto",
        }
        lead = scraper.clean_lead(raw)
        assert lead["business_name"] == "Joe's Barber"
        assert lead["email"] == "joe@joes.com"
        assert lead["phone"] == "555-1234"
        assert lead["rating"] == 4.5
        assert lead["review_count"] == 42
        assert lead["category"] == "Barber"

    def test_email_from_contact_info_when_top_level_empty(self, scraper):
        raw = {"title": "Acme", "email": "", "contactInfo": {"email": "info@acme.com"}}
        assert scraper.clean_lead(raw)["email"] == "info@acme.com"

    def test_email_from_contact_info_when_top_level_absent(self, scraper):
        raw = {"title": "Acme", "contactInfo": {"email": "info@acme.com"}}
        assert scraper.clean_lead(raw)["email"] == "info@acme.com"

    def test_top_level_email_stripped(self, scraper):
        raw = {"title": "Spa", "email": "  spa@example.com  "}
        assert scraper.clean_lead(raw)["email"] == "spa@example.com"

    def test_contact_info_email_stripped(self, scraper):
        raw = {"title": "Salon", "email": "", "contactInfo": {"email": "  a@b.com  "}}
        assert scraper.clean_lead(raw)["email"] == "a@b.com"

    def test_no_email_yields_empty_string(self, scraper):
        raw = {"title": "Ghost Corp"}
        assert scraper.clean_lead(raw)["email"] == ""

    def test_contact_info_not_dict_ignored(self, scraper):
        raw = {"title": "X", "email": "", "contactInfo": ["something"]}
        assert scraper.clean_lead(raw)["email"] == ""

    def test_contact_info_none_ignored(self, scraper):
        raw = {"title": "X", "email": "", "contactInfo": None}
        assert scraper.clean_lead(raw)["email"] == ""


# ---------------------------------------------------------------------------
# start_run
# ---------------------------------------------------------------------------

class TestStartRun:
    def test_returns_run_id(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"id": "run-abc123"}}
        with patch("requests.post", return_value=mock_resp):
            assert scraper.start_run(["barbers in Toronto"]) == "run-abc123"

    def test_missing_data_key_raises(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "error"}
        mock_resp.text = '{"status":"error"}'
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="run ID"):
                scraper.start_run(["barbers"])

    def test_data_without_id_raises(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {}}
        mock_resp.text = '{"data":{}}'
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="run ID"):
                scraper.start_run(["barbers"])

    def test_data_none_raises(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": None}
        mock_resp.text = '{"data":null}'
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="run ID"):
                scraper.start_run(["barbers"])


# ---------------------------------------------------------------------------
# wait_for_completion
# ---------------------------------------------------------------------------

class TestWaitForCompletion:
    def test_succeeded_returns_true(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"status": "SUCCEEDED"}}
        with patch("requests.get", return_value=mock_resp), patch("time.sleep"):
            assert scraper.wait_for_completion("run-1", poll_interval=1, max_wait=10) is True

    def test_failed_returns_false(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"status": "FAILED"}}
        with patch("requests.get", return_value=mock_resp), patch("time.sleep"):
            assert scraper.wait_for_completion("run-1", poll_interval=1, max_wait=10) is False

    def test_aborted_returns_false(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"status": "ABORTED"}}
        with patch("requests.get", return_value=mock_resp), patch("time.sleep"):
            assert scraper.wait_for_completion("run-1", poll_interval=1, max_wait=5) is False

    def test_timeout_returns_false(self, scraper):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"status": "RUNNING"}}
        with patch("requests.get", return_value=mock_resp), patch("time.sleep"):
            assert scraper.wait_for_completion("run-1", poll_interval=5, max_wait=5) is False

    def test_transient_network_error_continues_polling(self, scraper):
        """A single failed poll should not abort the wait loop."""
        responses = [
            Exception("network error"),
            MagicMock(**{"json.return_value": {"data": {"status": "SUCCEEDED"}}}),
        ]
        call_idx = [0]

        def side_effect(*args, **kwargs):
            r = responses[call_idx[0]]
            call_idx[0] += 1
            if isinstance(r, Exception):
                raise r
            return r

        with patch("requests.get", side_effect=side_effect), patch("time.sleep"):
            assert scraper.wait_for_completion("run-1", poll_interval=1, max_wait=10) is True


# ---------------------------------------------------------------------------
# scrape (full pipeline via method mocks)
# ---------------------------------------------------------------------------

class TestScrape:
    def test_deduplicates_by_email_case_insensitive(self, scraper):
        raw_items = [
            {"title": "Shop A", "email": "contact@shop.com"},
            {"title": "Shop A Clone", "email": "CONTACT@SHOP.COM"},
        ]
        with patch.object(scraper, "start_run", return_value="run-1"), \
             patch.object(scraper, "wait_for_completion", return_value=True), \
             patch.object(scraper, "fetch_results", return_value=raw_items):
            leads = scraper.scrape(["shops"])
        assert len(leads) == 1

    def test_filters_out_leads_with_no_email(self, scraper):
        raw_items = [
            {"title": "Shop A", "email": "a@a.com"},
            {"title": "Ghost Corp", "email": ""},
        ]
        with patch.object(scraper, "start_run", return_value="run-1"), \
             patch.object(scraper, "wait_for_completion", return_value=True), \
             patch.object(scraper, "fetch_results", return_value=raw_items):
            leads = scraper.scrape(["shops"])
        assert len(leads) == 1
        assert leads[0]["business_name"] == "Shop A"

    def test_returns_empty_if_run_fails(self, scraper):
        with patch.object(scraper, "start_run", return_value="run-1"), \
             patch.object(scraper, "wait_for_completion", return_value=False):
            assert scraper.scrape(["shops"]) == []
