"""Zero-dependency web scraper — finds business emails directly from the web.

Strategy:
  1. Query Google (or DuckDuckGo HTML) for a niche + location to get prospect sites.
  2. For each site, crawl the homepage and common contact pages.
  3. Extract emails via regex; skip role/spam addresses.
  4. Deduplicate and return clean lead dicts.

No paid APIs required — uses only requests + BeautifulSoup.
"""

import re
import time
import urllib.parse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit

logger = setup_logger(__name__)

# Regex: captures emails, ignores image/font filenames
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Skip generic/spam role addresses that nobody reads
_SKIP_PREFIXES = {
    "noreply", "no-reply", "donotreply", "bounce", "mailer-daemon",
    "postmaster", "abuse", "spam", "unsubscribe", "newsletter",
    "notifications", "alert", "alerts", "support", "help",
    "admin", "webmaster", "hostmaster",
}

# Contact-page paths to try for each domain
_CONTACT_PATHS = [
    "/contact", "/contact-us", "/contact_us", "/about", "/about-us",
    "/team", "/reach-us", "/get-in-touch", "/hello",
]

# Common headers to avoid bot detection
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _is_valid_email(email: str) -> bool:
    """Return False for role addresses, image filenames, and very long strings."""
    email = email.lower()
    if len(email) > 100:
        return False
    # Skip common file extensions mistaken for emails
    if re.search(r"\.(png|jpg|jpeg|gif|svg|woff|ttf|eot|css|js)$", email):
        return False
    prefix = email.split("@")[0]
    if prefix in _SKIP_PREFIXES:
        return False
    return True


def _extract_emails(html: str) -> list[str]:
    """Pull all valid email addresses from raw HTML."""
    emails = _EMAIL_RE.findall(html)
    seen: set[str] = set()
    result: list[str] = []
    for e in emails:
        e = e.lower().strip(".,;")
        if e not in seen and _is_valid_email(e):
            seen.add(e)
            result.append(e)
    return result


def _fetch(url: str, timeout: int = 10) -> Optional[str]:
    """GET a URL and return HTML text, or None on failure."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug("Fetch failed for %s: %s", url, e)
    return None


def _domain_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _scrape_emails_from_site(website: str) -> list[str]:
    """Scrape a website's homepage + contact pages for emails."""
    base = _domain_from_url(website)
    all_emails: list[str] = []

    # Homepage
    html = _fetch(website)
    if html:
        all_emails.extend(_extract_emails(html))

    # Contact / about pages
    for path in _CONTACT_PATHS:
        html = _fetch(base + path)
        if html:
            found = _extract_emails(html)
            if found:
                all_emails.extend(found)
                break  # Stop at first contact page that has emails

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for e in all_emails:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique


def _parse_google_results(html: str) -> list[str]:
    """Extract result URLs from a Google SERP HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        # Google wraps URLs in /url?q=...
        if href.startswith("/url?q="):
            raw = href[7:]
            actual = raw.split("&")[0]
            parsed = urllib.parse.urlparse(actual)
            # Skip Google's own domains and common non-prospects
            if parsed.netloc and "google." not in parsed.netloc:
                urls.append(actual)
    return urls


def _parse_duckduckgo_results(html: str) -> list[str]:
    """Extract result URLs from DuckDuckGo HTML SERP."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", class_="result__a", href=True):
        urls.append(a["href"])
    return urls


@rate_limit(min_interval=3.0)
def _search_google(query: str, num_results: int = 10) -> list[str]:
    """Run a Google search and return result URLs.

    Falls back to DuckDuckGo if Google returns a CAPTCHA.
    """
    params = {"q": query, "num": num_results, "hl": "en"}
    url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
    html = _fetch(url, timeout=15)

    if not html:
        logger.warning("Google search failed, trying DuckDuckGo.")
        return _search_duckduckgo(query, num_results)

    soup = BeautifulSoup(html, "html.parser")
    # Detect CAPTCHA / unusual traffic page
    if "unusual traffic" in html.lower() or soup.find("form", id="captcha-form"):
        logger.warning("Google CAPTCHA detected, falling back to DuckDuckGo.")
        return _search_duckduckgo(query, num_results)

    urls = _parse_google_results(html)
    logger.info("Google returned %d URLs for: %s", len(urls), query)
    return urls[:num_results]


@rate_limit(min_interval=3.0)
def _search_duckduckgo(query: str, num_results: int = 10) -> list[str]:
    """Scrape DuckDuckGo HTML results as a fallback search engine."""
    params = {"q": query, "kl": "us-en"}
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(params)
    html = _fetch(url, timeout=15)
    if not html:
        logger.error("DuckDuckGo search also failed for: %s", query)
        return []
    urls = _parse_duckduckgo_results(html)
    logger.info("DuckDuckGo returned %d URLs for: %s", len(urls), query)
    return urls[:num_results]


def _extract_business_name(website: str) -> str:
    """Guess the business name from the domain."""
    netloc = urllib.parse.urlparse(website).netloc
    # Strip www. and TLD
    name = netloc.replace("www.", "")
    name = re.sub(r"\.[a-z]{2,}$", "", name)
    return name.replace("-", " ").replace("_", " ").title()


def _scrape_meta(website: str) -> dict:
    """Pull title / description from a site's homepage."""
    html = _fetch(website)
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    desc = desc_tag.get("content", "").strip() if desc_tag else ""
    return {"page_title": title, "page_description": desc}


class WebScraper:
    """Scrape the web for prospect emails without any paid API.

    Usage:
        scraper = WebScraper()
        leads = scraper.scrape(
            queries=["hedge fund New York", "asset manager London"],
            results_per_query=10,
        )
    """

    def scrape(
        self,
        queries: list[str],
        results_per_query: int = 10,
        delay_between_sites: float = 1.5,
    ) -> list[dict]:
        """Search for prospects and extract their contact emails.

        Args:
            queries: List of search strings, e.g. ["law firm Chicago", "fintech startup"].
            results_per_query: Max websites to check per query.
            delay_between_sites: Seconds to wait between crawling each site.

        Returns:
            List of lead dicts with keys: business_name, email, website, category.
        """
        seen_domains: set[str] = set()
        seen_emails: set[str] = set()
        leads: list[dict] = []

        for query in queries:
            logger.info("Searching: %s", query)
            urls = _search_google(query, num_results=results_per_query)

            for url in urls:
                domain = urllib.parse.urlparse(url).netloc
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                logger.info("Crawling: %s", url)
                emails = _scrape_emails_from_site(url)

                if not emails:
                    logger.debug("No emails found on %s", url)
                    time.sleep(delay_between_sites)
                    continue

                meta = _scrape_meta(url)
                business_name = _extract_business_name(url)

                for email in emails:
                    if email in seen_emails:
                        continue
                    seen_emails.add(email)
                    leads.append({
                        "business_name": business_name,
                        "email": email,
                        "website": url,
                        "category": query,
                        "first_name": "",
                        "last_name": "",
                        "phone": "",
                        "city": "",
                        "page_title": meta.get("page_title", ""),
                        "page_description": meta.get("page_description", ""),
                    })
                    logger.info("Found lead: %s <%s>", business_name, email)

                time.sleep(delay_between_sites)

        logger.info("Total leads scraped: %d", len(leads))
        return leads
