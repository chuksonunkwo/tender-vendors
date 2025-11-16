def normalize_tender(
    title,
    country,
    source,
    link,
    description=None,
    operator=None,
    closing_date=None,
    external_id=None,
):
    return {
        "title": title,
        "country": country,
        "source": source,
        "link": link,
        "description": description,
        "operator": operator,
        "closing_date": closing_date,
        "external_id": external_id,
    }
