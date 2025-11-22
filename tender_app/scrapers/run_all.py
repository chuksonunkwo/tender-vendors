# tender_app/scrapers/run_all.py

from typing import Optional

from ..db import get_supabase_client  # adjust to your actual helper
from .nipex import run_nipex_scraper


def run_all_scrapers(supabase=None) -> int:
    """
    Run all available scrapers and return the total number of tenders affected.
    """
    if supabase is None:
        supabase = get_supabase_client()  # must exist in your project

    total = 0
    total += run_nipex_scraper(supabase)

    # Later:
    # from .angola import run_angola_scraper
    # total += run_angola_scraper(supabase)

    return total


if __name__ == "__main__":
    # Allow running from CLI: python -m tender_app.scrapers.run_all
    from ..db import get_supabase_client

    supabase = get_supabase_client()
    count = run_all_scrapers(supabase)
    print(f"Scrapers finished. Upserted {count} tenders.")
