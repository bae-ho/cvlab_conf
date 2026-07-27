# parsers/text_utils.py
import re
import pytz
from datetime import datetime

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(pytz.utc).isoformat()
