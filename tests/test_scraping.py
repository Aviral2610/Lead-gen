"""Tests for the scraping modules."""

import pytest
from unittest.mock import MagicMock, patch

from src.scraping.apollo_scraper import ApolloScraper
from src.scraping.apify_google_maps import GoogleMapsScraper, _normalize_website


# ---------------------------------------------------------------------------
# ApolloScraper tests
# ---------------------------------------------------------------------------

def _mock_config():
    cfg = MagicMock()
    cfg.max_leads_per_search = 25
    return cfg


class TestApolloScraper:
    def setup_method(self):
        self.scraper = ApolloScraper(api_key="test_key", config=_mock_config())

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_search_people_basic(self, mock_post):
        mock_post.return_value.json.return_value = {
            "people": [
                {
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "email": "alice@acme.com",
                    "title": "CEO",
                    "organization": {
                        "name": "Acme Corp",
                        "website_url": "https://acme.com",
                        "industry": "Software",
                        "estimated_num_employees": 50,
                    },
                    "phone_number": "+1-555-0100",
                    "city": "San Francisco",
                }
            ]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        results = self.scraper.search_people(titles=["CEO"])
        assert len(results) == 1
        lead = results[0]
        assert lead["first_name"] == "Alice"
        assert lead["email"] == "alice@acme.com"
        assert lead["business_name"] == "Acme Corp"
        assert lead["category"] == "Software"

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_search_people_passes_industries(self, mock_post):
        mock_post.return_value.json.return_value = {"people": []}
        mock_post.return_value.raise_for_status = MagicMock()

        self.scraper.search_people(titles=["CEO"], industries=["Software", "SaaS"])

        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["q_organization_keyword_tags"] == ["Software", "SaaS"]

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_search_people_passes_locations_and_ranges(self, mock_post):
        mock_post.return_value.json.return_value = {"people": []}
        mock_post.return_value.raise_for_status = MagicMock()

        self.scraper.search_people(
            titles=["CTO"], locations=["United States"], employee_ranges=["11,50"]
        )

        call_payload = mock_post.call_args.kwargs["json"]
        assert call_payload["person_locations"] == ["United States"]
        assert call_payload["organization_num_employees_ranges"] == ["11,50"]

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_search_people_omits_none_fields(self, mock_post):
        mock_post.return_value.json.return_value = {"people": []}
        mock_post.return_value.raise_for_status = MagicMock()

        self.scraper.search_people(titles=["CEO"])

        call_payload = mock_post.call_args.kwargs["json"]
        assert "person_locations" not in call_payload
        assert "organization_num_employees_ranges" not in call_payload
        assert "q_organization_keyword_tags" not in call_payload

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_clean_handles_missing_organization(self, mock_post):
        mock_post.return_value.json.return_value = {
            "people": [{"first_name": "Bob", "last_name": "Jones", "email": "b@co.com"}]
        }
        mock_post.return_value.raise_for_status = MagicMock()

        results = self.scraper.search_people(titles=["VP"])
        assert results[0]["business_name"] == ""
        assert results[0]["website"] == ""
        assert results[0]["category"] == ""

    @patch("src.scraping.apollo_scraper.requests.post")
    def test_empty_results(self, mock_post):
        mock_post.return_value.json.return_value = {"people": []}
        mock_post.return_value.raise_for_status = MagicMock()
        assert self.scraper.search_people(titles=["CEO"]) == []


# ---------------------------------------------------------------------------
# _normalize_website tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("http://www.example.com/about", "https://example.com"),
    ("https://www.shop.co.uk/", "https://shop.co.uk"),
    ("https://acme.com/", "https://acme.com"),
    ("example.com", "https://example.com"),
    ("", ""),
])
def test_normalize_website(url, expected):
    assert _normalize_website(url) == expected


# ---------------------------------------------------------------------------
# GoogleMapsScraper tests
# ---------------------------------------------------------------------------

class TestGoogleMapsScraper:
    def setup_method(self):
        cfg = MagicMock()
        cfg.apify_token = "test_apify_token"
        cfg.max_leads_per_search = 50
        self.scraper = GoogleMapsScraper(config=cfg)

    def test_clean_lead_normalizes_website(self):
        raw = {
            "title": "The Coffee House",
            "email": "hello@coffee.com",
            "phone": "555-1234",
            "website": "http://www.coffee.com/home",
            "city": "Portland",
            "categoryName": "Cafe",
            "totalScore": 4.5,
            "reviewsCount": 120,
        }
        lead = self.scraper._clean_lead(raw)
        assert lead["website"] == "https://coffee.com"
        assert lead["business_name"] == "The Coffee House"
        assert lead["rating"] == 4.5
        assert lead["review_count"] == 120

    def test_clean_lead_handles_missing_fields(self):
        lead = self.scraper._clean_lead({"title": "Minimal Business"})
        assert lead["email"] == ""
        assert lead["phone"] == ""
        assert lead["website"] == ""
        assert lead["rating"] == 0.0
        assert lead["review_count"] == 0

    def test_clean_lead_falls_back_to_contactinfo(self):
        raw = {"title": "Shop", "contactInfo": {"email": "contact@shop.com"}}
        lead = self.scraper._clean_lead(raw)
        assert lead["email"] == "contact@shop.com"

    def test_deduplicate_removes_same_email(self):
        leads = [
            {"email": "a@b.com", "business_name": "First"},
            {"email": "A@B.COM", "business_name": "Duplicate"},
            {"email": "c@d.com", "business_name": "Different"},
        ]
        result = self.scraper._deduplicate(leads)
        assert len(result) == 2
        assert any(l["email"].lower() == "c@d.com" for l in result)

    def test_deduplicate_keeps_leads_without_email(self):
        leads = [
            {"email": "", "business_name": "No Email A"},
            {"email": "", "business_name": "No Email B"},
        ]
        result = self.scraper._deduplicate(leads)
        assert len(result) == 2

    def test_clean_lead_alias_exists(self):
        raw = {"title": "Test", "email": "t@t.com"}
        assert self.scraper.clean_lead(raw) == self.scraper._clean_lead(raw)
