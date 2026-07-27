# parsers/deadline_parser.py
import re

MONTHS = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)

# 예: "May 25, 2026", "May 25 2026", "May 25-31, 2026"
DEADLINE_DATE_RE = re.compile(
    rf"\b({MONTHS})\s+\d{{1,2}}(?:-\d{{1,2}})?,?\s+\d{{4}}\b",
    re.I
)

def extract_deadline_date_from_cells(cells: list[str]) -> str | None:
    """
    cells 전체에서 데드라인 '날짜'만 찾아 반환.
    없으면 None.
    """
    text = " | ".join(cells)
    m = DEADLINE_DATE_RE.search(text)
    return m.group(0) if m else None