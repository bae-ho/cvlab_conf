# parsers/location_parser.py
import re

COUNTRY_RE = re.compile(r",\s*([A-Za-z\s]+)$")

def extract_location(text: str) -> str | None:
    match = COUNTRY_RE.search(text)
    if not match:
        return None
    return match.group(0).strip(", ")