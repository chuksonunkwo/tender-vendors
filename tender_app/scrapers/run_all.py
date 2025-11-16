from supabase import Client
from .nipex import scrape_nipex
from .nigeria_news import scrape_nigeria_newspapers
from .angola import scrape_angola_portal


def upsert_tender(supabase: Client, item: dict) -> bool:
    """
    Insert a tender if it does not already exist (by source + external_id).
    Returns True if inserted, False if skipped.
    """
    source = item.get("source")
    external_id = item.get("external_id")

    # if no external_id, treat as always insert (manual or rare case)
    if not external_id:
        supabase.table("tenders").insert(item).execute()
        return True

    # check if tender exists
    existing = (
        supabase.table("tenders")
        .select("id")
        .eq("source", source)
        .eq("external_id", external_id)
        .limit(1)
        .execute()
        .data
    )

    if existing:
        # already there – skip (or you could update here instead)
        return False

    supabase.table("tenders").insert(item).execute()
    return True


def run_all_scrapers(supabase: Client) -> int:
    """
    Run all country-specific scrapers and insert tenders into Supabase.
    Uses upsert_tender for simple de-duplication.
    """
    all_items = []

    # Collect from each scraper (each returns list[dict])
    all_items += scrape_nipex()
    all_items += scrape_nigeria_newspapers()
    all_items += scrape_angola_portal()

    inserted = 0

    for item in all_items:
        if upsert_tender(supabase, item):
            inserted += 1

    return inserted
