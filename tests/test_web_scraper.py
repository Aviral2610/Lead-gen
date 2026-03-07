"""Tests for src/scraping/web_scraper.py"""

import pytest
from unittest.mock import patch, MagicMock

from src.scraping.web_scraper import (
    _extract_emails,
    _is_valid_email,
    _extract_business_name,
    _domain_from_url,
    WebScraper,
)


# ---------------------------------------------------------------------------
# _is_valid_email
# ---------------------------------------------------------------------------

class TestIsValidEmail:
    def test_normal_email_passes(self):
        assert _is_valid_email("cfo@acme.com")

    def test_noreply_blocked(self):
        assert not _is_valid_email("noreply@acme.com")

    def test_image_filename_blocked(self):
        assert not _is_valid_email("header@2x.png")

    def test_too_long_blocked(self):
        assert not _is_valid_email("a" * 90 + "@example.com")

    def test_admin_blocked(self):
        assert not _is_valid_email("admin@company.org")

    def test_support_blocked(self):
        assert not _is_valid_email("support@company.org")

    def test_real_contact_passes(self):
        assert _is_valid_email("john.smith@hedgefund.io")


# ---------------------------------------------------------------------------
# _extract_emails
# ---------------------------------------------------------------------------

class TestExtractEmails:
    def test_finds_plain_email(self):
        html = "<p>Contact us at info@example.com for more details.</p>"
        result = _extract_emails(html)
        assert "info@example.com" in result

    def test_skips_noreply(self):
        html = "Automated sender: noreply@example.com"
        result = _extract_emails(html)
        assert result == []

    def test_deduplicates(self):
        html = "sales@co.com and sales@co.com again"
        result = _extract_emails(html)
        assert result.count("sales@co.com") == 1

    def test_multiple_emails(self):
        html = "ceo@alpha.com and cto@beta.org and admin@gamma.net"
        result = _extract_emails(html)
        assert "ceo@alpha.com" in result
        assert "cto@beta.org" in result
        assert "admin@gamma.net" not in result  # admin is blocked

    def test_strips_trailing_punctuation(self):
        html = "write to hello@foo.com, please."
        result = _extract_emails(html)
        assert "hello@foo.com" in result

    def test_empty_html_returns_empty(self):
        assert _extract_emails("") == []


# ---------------------------------------------------------------------------
# _domain_from_url / _extract_business_name
# ---------------------------------------------------------------------------

class TestUrlHelpers:
    def test_domain_from_url(self):
        assert _domain_from_url("https://www.acme.com/about") == "https://www.acme.com"

    def test_extract_business_name_strips_www(self):
        name = _extract_business_name("https://www.acme-corp.com/about")
        assert "Www" not in name
        assert "Acme Corp" in name

    def test_extract_business_name_strips_tld(self):
        name = _extract_business_name("https://hedgefund.io/team")
        assert ".io" not in name


# ---------------------------------------------------------------------------
# WebScraper.scrape (mocked network)
# ---------------------------------------------------------------------------

_GOOGLE_HTML = """
<html><body>
<a href="/url?q=https://acmefund.com&sa=U">ACME Fund</a>
<a href="/url?q=https://betacapital.org&sa=U">Beta Capital</a>
</body></html>
"""

_SITE_HTML_WITH_EMAIL = """
<html><body>
<p>Contact: cfo@acmefund.com</p>
</body></html>
"""

_SITE_HTML_NO_EMAIL = "<html><body><p>No contact info here.</p></body></html>"


def _make_fetch_side_effect(url_map: dict):
    """Return a side_effect function that maps URLs to HTML strings."""
    def _fetch(url, timeout=10):
        for key, html in url_map.items():
            if key in url:
                return html
        return None
    return _fetch


class TestWebScraper:
    def test_scrape_returns_leads_with_emails(self):
        scraper = WebScraper()
        url_map = {
            "google.com": _GOOGLE_HTML,
            "acmefund.com": _SITE_HTML_WITH_EMAIL,
            "betacapital.org": _SITE_HTML_NO_EMAIL,
        }
        with patch("src.scraping.web_scraper._fetch", side_effect=_make_fetch_side_effect(url_map)):
            leads = scraper.scrape(queries=["hedge fund"], results_per_query=5, delay_between_sites=0)

        assert len(leads) == 1
        assert leads[0]["email"] == "cfo@acmefund.com"
        assert "acmefund" in leads[0]["website"]

    def test_scrape_deduplicates_emails(self):
        scraper = WebScraper()
        # Both sites return the same email
        html_dup = "<p>cfo@acmefund.com</p>"
        url_map = {
            "google.com": _GOOGLE_HTML,
            "acmefund.com": html_dup,
            "betacapital.org": html_dup,
        }
        with patch("src.scraping.web_scraper._fetch", side_effect=_make_fetch_side_effect(url_map)):
            leads = scraper.scrape(queries=["hedge fund"], results_per_query=5, delay_between_sites=0)

        emails = [l["email"] for l in leads]
        assert emails.count("cfo@acmefund.com") == 1

    def test_scrape_no_results_returns_empty(self):
        scraper = WebScraper()
        with patch("src.scraping.web_scraper._fetch", return_value=None):
            leads = scraper.scrape(queries=["obscure niche xyz"], delay_between_sites=0)
        assert leads == []

    def test_scrape_falls_back_to_duckduckgo_on_captcha(self):
        scraper = WebScraper()
        captcha_html = "<html><body>unusual traffic detected</body></html>"
        ddg_html = '<html><body><a class="result__a" href="https://acmefund.com">ACME</a></body></html>'
        site_html = "<p>cfo@acmefund.com</p>"

        call_count = {"n": 0}

        def smart_fetch(url, timeout=10):
            if "google.com" in url:
                return captcha_html
            if "duckduckgo.com" in url:
                return ddg_html
            return site_html

        with patch("src.scraping.web_scraper._fetch", side_effect=smart_fetch):
            leads = scraper.scrape(queries=["hedge fund"], delay_between_sites=0)

        assert any(l["email"] == "cfo@acmefund.com" for l in leads)
