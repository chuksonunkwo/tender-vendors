import requests
from bs4 import BeautifulSoup
from .base import normalize_tender

# NipeX public "Current Opportunities" (WordPress site)
BASE_LIST_URL = "https://nipexmain2.nipex-ng.com/Opportunity/"
SOURCE_NAME = "NipeX"


def _fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[scraper:nipex] error fetching {url}: {e}")
        return None


def _parse_list_page(html: str) -> list[dict]:
    """
    Parse one NipeX 'Opportunity' list page and return a list of normalized tenders.
    We only use the listing page (title + link + published date); closing date
    will be added later when we start parsing detail pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    tenders: list[dict] = []

    # Typical WordPress pattern: each post is an <article>
    for article in soup.select("article"):
        title_link = article.select_one("h2 a")
        if not title_link:
            continue

        title = (title_link.get_text() or "").strip()
        href = title_link.get("href") or BASE_LIST_URL
        if not title:
            continue

        # Try to get the published date (not the closing date)
        pub_date = None
        time_tag = article.select_one("time")
        if time_tag:
            # WordPress usually stores ISO date in datetime attribute
            dt_attr = time_tag.get("datetime") or ""
            text = (time_tag.get_text() or "").strip()
            # Prefer the machine-readable datetime attribute if present
            if dt_attr:
                pub_date = dt_attr[:10]  # 'YYYY-MM-DD'
            elif text:
                pub_date = text  # fallback, free-text date

        # Optional short description if available
        desc_tag = article.select_one(".entry-summary, .entry-content p")
        description = (desc_tag.get_text() or "").strip() if desc_tag else None

        # Build tender item; operator / closing_date will often be unknown from list page
        tender = normalize_tender(
            title=title,
            country="Nigeria",
            source=SOURCE_NAME,
            link=href,
            description=description,
            operator=None,
            closing_date=None,
            external_id=href,  # use full URL as unique id for de-duplication
        )
        # we can optionally stash publication date in description or extend schema later
        tender["publication_date"] = pub_date

        tenders.append(tender)

    return tenders


def scrape_nipex(max_pages: int = 3) -> list[dict]:
    """
    Scrape NipeX 'Current Opportunities' from the first `max_pages` of the
    WordPress listing.

    max_pages=3 means:
      - https://nipexmain2.nipex-ng.com/Opportunity/
      - https://nipexmain2.nipex-ng.com/Opportunity/page/2/
      - https://nipexmain2.nipex-ng.com/Opportunity/page/3/
    """
    all_tenders: list[dict] = []

    # Page 1 has no "page/1" in the URL
    first_html = _fetch_html(BASE_LIST_URL)
    if first_html:
        all_tenders.extend(_parse_list_page(first_html))

    # Remaining pages
    for page in range(2, max_pages + 1):
        url = f"{BASE_LIST_URL}page/{page}/"
        html = _fetch_html(url)
        if not html:
            continue
        all_tenders.extend(_parse_list_page(html))

    print(f"[scraper:nipex] collected {len(all_tenders)} items from {max_pages} page(s).")
    return all_tenders
