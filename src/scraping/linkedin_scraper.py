"""LinkedIn contact finder — uses Google to surface LinkedIn profiles.

LinkedIn blocks direct scraping, but Google indexes public LinkedIn
pages.  We exploit that: search Google for
  site:linkedin.com/in "<title>" "<company or location>"
then parse the SERP snippets to extract name, title, and company.

We never touch linkedin.com directly.  From the company name we then
look up the company website and scrape it for a real contact email
(using WebScraper helpers).

No LinkedIn API or paid tools required.
"""

import re
import time
import urllib.parse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.scraping.web_scraper import (
    _fetch,
    _search_duckduckgo,
    _scrape_emails_from_site,
    _HEADERS,
)
from src.utils.logger import setup_logger
from src.utils.rate_limiter import rate_limit

logger = setup_logger(__name__)

# Title patterns that indicate seniority / decision-maker status
_SENIOR_TITLES = re.compile(
    r"(professor|prof\.?|dean|director|head of|chair(man|woman|person)?|"
    r"chief|cio|cto|cfo|ceo|co-founder|founder|president|vice president|"
    r"vp |managing partner|managing director|md |portfolio manager|"
    r"fund manager|investment manager|principal)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Google snippet parser
# ---------------------------------------------------------------------------

def _parse_linkedin_snippets(html: str) -> list[dict]:
    """Extract name / title / company from Google SERP snippets for LinkedIn results."""
    soup = BeautifulSoup(html, "html.parser")
    contacts: list[dict] = []

    for result in soup.find_all("div", class_=re.compile(r"^(g|tF2Cxc|yuRUbf)")):
        # Find the LinkedIn URL in this block
        link = result.find("a", href=re.compile(r"linkedin\.com/in/"))
        if not link:
            continue

        # Title of the result = usually "Full Name - Title - Company | LinkedIn"
        title_tag = result.find(["h3", "h2"])
        raw_title = title_tag.get_text(" ", strip=True) if title_tag else ""

        # Snippet text
        snippet_tag = result.find("div", class_=re.compile(r"(VwiC3b|s3v9rd|st)"))
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""

        contact = _parse_contact_from_title_snippet(raw_title, snippet)
        if contact:
            contacts.append(contact)

    return contacts


def _parse_contact_from_title_snippet(title_str: str, snippet: str) -> Optional[dict]:
    """Extract {first_name, last_name, title, company} from a LinkedIn SERP entry."""
    # Typical Google title format: "John Smith - Portfolio Manager - Alpha Capital | LinkedIn"
    parts = [p.strip() for p in re.split(r"[|\-–—]", title_str)]
    parts = [p for p in parts if p and "linkedin" not in p.lower()]

    if len(parts) < 2:
        return None

    full_name = parts[0]
    job_title = parts[1] if len(parts) > 1 else ""
    company = parts[2] if len(parts) > 2 else ""

    # Must look like a person (2 words, no digits)
    name_parts = full_name.split()
    if len(name_parts) < 2 or any(c.isdigit() for c in full_name):
        return None

    # Only keep decision-makers
    if not _SENIOR_TITLES.search(job_title):
        return None

    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:])

    # Try to extract company from snippet if not in title
    if not company and snippet:
        # Snippet often contains "at <Company>" or "· <Company>"
        m = re.search(r"(?:at|@|·)\s+([A-Z][^\n,·]{2,40})", snippet)
        if m:
            company = m.group(1).strip()

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "title": job_title,
        "business_name": company,
        "email": "",          # filled in later
        "website": "",        # filled in later
        "source": "linkedin",
    }


# ---------------------------------------------------------------------------
# Company website lookup
# ---------------------------------------------------------------------------

@rate_limit(min_interval=3.0)
def _find_company_website(company_name: str) -> str:
    """Google for the company's official website URL."""
    if not company_name:
        return ""
    query = f'"{company_name}" official website'
    params = {"q": query, "num": 3, "hl": "en"}
    url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
    html = _fetch(url, timeout=15)
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if href.startswith("/url?q="):
            actual = href[7:].split("&")[0]
            parsed = urllib.parse.urlparse(actual)
            # Skip Google, LinkedIn, Wikipedia, social media
            skip = {"google.", "linkedin.", "wikipedia.", "facebook.",
                    "twitter.", "instagram.", "youtube."}
            if parsed.netloc and not any(s in parsed.netloc for s in skip):
                return actual
    return ""


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

@rate_limit(min_interval=4.0)
def _search_linkedin_on_google(query: str, num: int = 10) -> list[dict]:
    """Search Google for LinkedIn profiles matching a query, return parsed contacts."""
    full_query = f"site:linkedin.com/in {query}"
    params = {"q": full_query, "num": num, "hl": "en"}
    url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
    html = _fetch(url, timeout=15)
    if not html:
        logger.warning("No response from Google for LinkedIn query: %s", query)
        return []

    soup = BeautifulSoup(html, "html.parser")
    if "unusual traffic" in html.lower() or soup.find("form", id="captcha-form"):
        logger.warning("Google CAPTCHA on LinkedIn search — waiting and skipping.")
        time.sleep(10)
        return []

    contacts = _parse_linkedin_snippets(html)
    logger.info("LinkedIn search '%s' → %d contacts parsed", query, len(contacts))
    return contacts


class LinkedInScraper:
    """Find decision-maker contacts via Google-indexed LinkedIn profiles.

    For each contact found we:
      1. Look up the company website via Google.
      2. Scrape the website for a real contact email.
      3. Fall back to guessing common patterns (info@, contact@, firstname@).
    """

    def __init__(self, delay_between_lookups: float = 3.0):
        self.delay = delay_between_lookups

    def scrape(
        self,
        queries: list[str],
        results_per_query: int = 8,
    ) -> list[dict]:
        """Run LinkedIn-via-Google searches and enrich with emails.

        Args:
            queries: Natural-language queries, e.g.
                     ['"Head of Finance" MBA college India'].
            results_per_query: Max LinkedIn profiles to parse per query.

        Returns:
            List of lead dicts with: first_name, last_name, title,
            business_name, email, website, salutation, source='linkedin'.
        """
        seen_names: set[str] = set()
        seen_emails: set[str] = set()
        leads: list[dict] = []

        for query in queries:
            logger.info("LinkedIn search: %s", query)
            contacts = _search_linkedin_on_google(query, num=results_per_query)

            for contact in contacts:
                name_key = contact["full_name"].lower()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                # Find company website
                website = _find_company_website(contact["business_name"])
                contact["website"] = website
                time.sleep(self.delay)

                # Scrape website for email
                emails = _scrape_emails_from_site(website) if website else []

                # Filter: prefer emails that contain the person's name or common contact prefixes
                best_email = _pick_best_email(emails, contact["first_name"], contact["last_name"])
                if not best_email:
                    # Guess common patterns
                    best_email = _guess_email(contact["first_name"], contact["last_name"], website)

                if not best_email:
                    logger.debug("No email found for %s at %s", contact["full_name"], contact["business_name"])
                    time.sleep(self.delay)
                    continue

                if best_email in seen_emails:
                    time.sleep(self.delay)
                    continue
                seen_emails.add(best_email)

                contact["email"] = best_email
                contact["salutation"] = build_salutation(contact["title"], contact["first_name"], contact["last_name"])
                leads.append(contact)
                logger.info("Lead: %s <%s> [%s]", contact["full_name"], best_email, contact["title"])
                time.sleep(self.delay)

        logger.info("LinkedIn scrape complete — %d leads with emails.", len(leads))
        return leads


# ---------------------------------------------------------------------------
# Email selection helpers
# ---------------------------------------------------------------------------

def _pick_best_email(emails: list[str], first: str, last: str) -> str:
    """Prefer email containing person's name; fall back to first found."""
    first = first.lower()
    last = last.lower()
    for e in emails:
        local = e.split("@")[0].lower()
        if first in local or last in local:
            return e
    # Prefer common contact prefixes over completely random ones
    preferred = {"info", "contact", "hello", "finance", "director", "dean", "research"}
    for e in emails:
        if e.split("@")[0].lower() in preferred:
            return e
    return emails[0] if emails else ""


def _guess_email(first: str, last: str, website: str) -> str:
    """Guess likely email patterns and return the first that looks valid."""
    if not website or not first or not last:
        return ""
    parsed = urllib.parse.urlparse(website)
    domain = parsed.netloc.replace("www.", "")
    if not domain:
        return ""

    first = first.lower()
    last = last.lower()
    candidates = [
        f"{first}.{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}@{domain}",
        f"info@{domain}",
        f"contact@{domain}",
    ]

    for candidate in candidates:
        # Simple existence check via SMTP VRFY is blocked most places;
        # we just return the first pattern (firstname.lastname@ is most common)
        logger.debug("Guessing email: %s", candidate)
        return candidate

    return ""


# ---------------------------------------------------------------------------
# Salutation builder (used by both scrapers)
# ---------------------------------------------------------------------------

def build_salutation(title: str, first_name: str, last_name: str) -> str:
    """Return an appropriate salutation based on job title.

    Rules:
      - Professor / Dean / Dr → "Dear Prof. Last" or "Dear Dr. Last"
      - Director / Head / Chair / President → "Dear Mr./Ms. Last"
      - CXO / Fund Manager / Portfolio Manager → "Dear First"
      - Unknown → "Dear First"
    """
    t = title.lower()
    ln = last_name.strip() or first_name.strip()
    fn = first_name.strip()

    if re.search(r"\b(professor|prof\.?)\b", t):
        return f"Dear Prof. {ln}"
    if re.search(r"\bdean\b", t):
        return f"Dear Dean {ln}"
    if re.search(r"\b(dr\.?|phd)\b", t):
        return f"Dear Dr. {ln}"
    if re.search(r"\b(director|head of|chair|president|vice president|principal)\b", t):
        # Use "Dear Mr./Ms." — we don't know gender, so keep it professional
        return f"Dear {fn}" if fn else f"Dear {ln}"
    # For finance roles (CIO, PM, fund manager) → first name is standard in finance
    return f"Dear {fn}" if fn else "Dear Sir/Madam"
