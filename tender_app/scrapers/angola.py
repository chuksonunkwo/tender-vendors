from .base import normalize_tender

def scrape_angola_portal():
    """
    Placeholder for real Angola procurement portal scraping.
    """
    return [
        normalize_tender(
            title="Angola Oilfield Support Tender",
            country="Angola",
            source="Angola Portal",
            link="https://angola.gov.ao/demo-tender",
            description="Angola tender placeholder",
            external_id="https://angola.gov.ao/demo-tender",
        )
    ]
