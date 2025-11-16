import requests
from bs4 import BeautifulSoup
from .base import normalize_tender


NEWS_URL = "https://www.python.org/blogs/"  # TEMP demo; replace with real Nigeria tender URL
SOURCE_NAME = "Nigeria News Demo"


def scrape_nigeria_newspapers():
    """
    Example of a real HTTP-based scraper.
    Currently uses python.org/blogs as a harmless demo.
    Adapt CSS selectors when you point it to a real Nigeria tender page.
    """
    try:
        resp = requests.get(NEWS_URL, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"[scraper:nigeria_news] error fetching {NEWS_URL}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    # Demo: python.org/blogs has posts under .list-recent-posts li
    for li in soup.select(".list-recent-posts li"):
        a = li.find("a")
        if not a:
            continue

        title = (a.get_text() or "").strip()
        href = a.get("href") or NEWS_URL
        if not title:
            continue

        # Build absolute link for demo
        if not href.startswith("http"):
            href = "https://www.python.org" + href

        text = (li.get_text() or "").strip()

        items.append(
            normalize_tender(
                title=title,
                country="Nigeria",             # later: determine based on site
                source=SOURCE_NAME,
                link=href,
                description=text,
                operator=None,                 # unknown for news listing
                closing_date=None,             # parse when you have date on page
                external_id=href,              # use URL as unique key
            )
        )

    return items
