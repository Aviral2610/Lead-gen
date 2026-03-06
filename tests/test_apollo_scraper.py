"""Tests for src/scraping/apollo_scraper.py"""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_config
from src.scraping.apollo_scraper import ApolloScraper


@pytest.fixture
def scraper():
    return ApolloScraper(api_key="test-api-key", config=make_config())


def _make_person(email, first="John", org_name="Acme"):
    return {
        "first_name": first,
        "last_name": "Doe",
        "email": email,
        "title": "CEO",
        "phone_number": "555-0001",
        "city": "Austin",
        "organization": {
            "name": org_name,
            "website_url": "https://acme.com",
            "industry": "SaaS",
            "estimated_num_employees": 50,
        },
    }


# ---------------------------------------------------------------------------
# _clean
# ---------------------------------------------------------------------------

class TestClean:
    def test_maps_all_fields(self, scraper):
        person = _make_person("jane@acme.com", first="Jane")
        lead = scraper._clean(person)
        assert lead["first_name"] == "Jane"
        assert lead["email"] == "jane@acme.com"
        assert lead["business_name"] == "Acme"
        assert lead["category"] == "SaaS"
        assert lead["employee_count"] == 50

    def test_null_organization_gives_empty_fields(self, scraper):
        person = {"first_name": "Bob", "organization": None}
        lead = scraper._clean(person)
        assert lead["business_name"] == ""
        assert lead["website"] == ""
        assert lead["category"] == ""

    def test_missing_organization_key(self, scraper):
        person = {"first_name": "Alice"}
        lead = scraper._clean(person)
        assert lead["business_name"] == ""


# ---------------------------------------------------------------------------
# scrape — pagination, filtering, dedup
# ---------------------------------------------------------------------------

class TestScrape:
    def test_stops_early_on_partial_last_page(self, scraper):
        """If a page returns fewer results than per_page, it's the last page."""
        page1 = [scraper._clean(_make_person(f"p1_{i}@x.com")) for i in range(25)]
        page2 = [scraper._clean(_make_person(f"p2_{i}@x.com")) for i in range(10)]

        call_count = [0]

        def fake_search(**kwargs):
            call_count[0] += 1
            return page1 if kwargs.get("page") == 1 else page2

        with patch.object(scraper, "search_people", side_effect=fake_search):
            leads = scraper.scrape(titles=["CEO"], per_page=25, max_pages=5)

        assert call_count[0] == 2
        assert len(leads) == 35

    def test_filters_invalid_emails(self, scraper):
        people = [
            scraper._clean(_make_person("valid@x.com")),
            scraper._clean(_make_person("no-at-sign")),
            scraper._clean(_make_person("")),
        ]
        with patch.object(scraper, "search_people", return_value=people):
            leads = scraper.scrape(titles=["CEO"])
        assert len(leads) == 1
        assert leads[0]["email"] == "valid@x.com"

    def test_deduplicates_by_email_case_insensitive(self, scraper):
        people = [
            scraper._clean(_make_person("dup@x.com")),
            scraper._clean(_make_person("DUP@X.COM")),
        ]
        with patch.object(scraper, "search_people", return_value=people):
            leads = scraper.scrape(titles=["CEO"])
        assert len(leads) == 1

    def test_respects_max_pages(self, scraper):
        page = [scraper._clean(_make_person(f"lead{i}@x.com")) for i in range(25)]
        call_count = [0]

        def fake_search(**kwargs):
            call_count[0] += 1
            return page

        with patch.object(scraper, "search_people", side_effect=fake_search):
            scraper.scrape(titles=["CEO"], per_page=25, max_pages=3)

        assert call_count[0] == 3
