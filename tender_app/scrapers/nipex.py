# tender_app/scrapers/nipex.py

import datetime as dt
import re
from typing import Dict, List

import requests
from bs4 import BeautifulSoup  # pip install beautifulsoup4


NipexTender = Dict[str, object]

NIPEX_URL = (
    "https://nipexmain2.nipex-ng.com/supplier-notice/current-opportunities/"
)


def fetch_nipex_html() -> str:
    """
    Download the NipeX 'Current Opportunities' page HTML.
    """
    resp = requests.get(NIPEX_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_deadline_text(text: str) -> dt.date | None:
    """
    Convert text like 'Deadline Date :  November 27th, 2025' into a date.
    Handles 'st', 'nd', 'rd', 'th' suffixes.
    """
    # Extract part after 'Deadline Date :'
    m = re.search(r"Deadline\s*Date\s*:\s*(.+)", text, flags=re.IGNORECASE)
    if not m:
        return None

    raw = m.group(1).strip()
    # Remove ordinal suffixes (st, nd, rd, th)
    raw = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", raw, flags=re.IGNORECASE)
    # Normalize spaces
    raw = re.sub(r"\s+", " ", raw)

    for fmt in ("%B %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    return None


def parse_nipex_tenders(html: str) -> List[NipexTender]:
    """
    Parse the NipeX 'Current Opportunities' page into a list of tender dicts.

    We look for H2/H3 headings that have a following text node containing
    'Deadline Date :'.
    """
    soup = BeautifulSoup(html, "html.parser")
    tenders: List[NipexTender] = []

    # All h2/h3 headings on the page
    headings = soup.find_all(["h2", "h3"])

    for h in headings:
        title = h.get_text(strip=True)
        if not title:
            continue

        # Skip the main page title or unrelated headings
        if "CURRENT OPPORTUNITIES" in title.upper():
            continue

        # Look ahead for a line containing 'Deadline Date'
        deadline_node = h.find_next(string=re.compile("Deadline\\s*Date", re.IGNORECASE))
        if not deadline_node:
            # This heading may not be a tender entry
            continue

        deadline_text = deadline_node.strip()
        closing_date = _parse_deadline_text(deadline_text)

        # Grab link if present (often same <a> as title)
        link_tag = h.find("a")
        link = (
            link_tag.get("href")
            if link_tag and link_tag.has_attr("href")
            else NIPEX_URL
        )

        tender: NipexTender = {
            "title": title,
            "operator": None,  # Operator is not shown per-line on this page
            "country": "Nigeria",
            "source": "NipeX Current Opportunities",
            "closing_date": closing_date.isoformat() if closing_date else None,
            "link": link,
        }
        tenders.append(tender)

    return tenders


def upsert_tenders_to_supabase(supabase, tenders: List[NipexTender]) -> int:
    """
    Insert tenders into the 'tenders' table.

    For now we use plain INSERT (no ON CONFLICT) to avoid needing
    a unique constraint. Running the scraper multiple times may create
    duplicates until you add a proper UNIQUE index and switch to upsert.
    """
    if not tenders:
        return 0

    now = dt.datetime.utcnow().isoformat()
    payload: List[dict] = []

    for t in tenders:
        item = dict(t)
        item["updated_at"] = now
        if "created_at" not in item:
            item["created_at"] = now
        payload.append(item)

    resp = supabase.table("tenders").insert(payload).execute()
    data = getattr(resp, "data", None) or []
    return len(data)


def run_nipex_scraper(supabase) -> int:
    """Run the Nipex scraper end-to-end: fetch page, parse tenders, insert into Supabase."""
    try:
        html = fetch_nipex_html()
    except Exception as e:
        print(f"[nipex] fetch error: {e}")
        return 0

    try:
        tenders = parse_nipex_tenders(html)
    except Exception as e:
        print(f"[nipex] parse error: {e}")
        return 0

    try:
        inserted = upsert_tenders_to_supabase(supabase, tenders)
        print(f"[nipex] upserted {inserted} tenders")
        return inserted
    except Exception as e:
        print(f"[nipex] upsert error: {e}")
        return 0

